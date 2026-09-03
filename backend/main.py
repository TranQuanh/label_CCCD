"""
main.py (FastAPI)
=================
API phục vụ model CCCD đã fine-tune: nhận ảnh upload → trả JSON trích xuất.

Phục vụ được **cả 3 kiến trúc** trong bộ so sánh (qwen / internvl / llama_vision),
mỗi lần chạy một model — chọn bằng env `MODEL_KEY`. Muốn đo cả 3 thì bật lần lượt,
hoặc dùng `scripts/benchmark.py --mode local --models qwen,internvl,llama_vision`
(nạp tuần tự trong 1 process, không cần bật server).

**Hai adapter trên MỘT base.** Mỗi model được fine-tune riêng cho mặt trước và mặt
sau (`{model_key}-cccd-lora-{front,back}`). Base 4-bit chỉ nạp MỘT lần rồi gắn cả
hai adapter bằng PEFT multi-adapter; mỗi request chỉ `set_adapter()` theo mặt thẻ
của ảnh — thao tác này chỉ bật/tắt lớp LoRA đang active, không copy trọng số. Nạp
2 process cho 2 mặt là tốn gấp đôi VRAM cho cùng một bộ trọng số base.

Tối ưu bộ nhớ khi deploy:
  - Base load 4-bit NF4 (giống hệt lúc train) để vừa GPU nhỏ.
  - Model load 1 lần ở startup (lifespan), tái dùng cho mọi request.

Endpoints:
  GET  /health              → model nào đang phục vụ, có sẵn adapter mặt nào.
  POST /extract-cccd/       → upload 1 ảnh (+ side tùy chọn) → JSON.
  POST /extract-cccd/batch  → upload N ảnh, chạy theo lô → list JSON + thời gian.

Chạy:
  export MODEL_KEY=qwen
  export CHECKPOINT_DIR=checkpoints        # chứa qwen-cccd-lora-{front,back}
  export BASE_MODEL=models/Qwen2.5-VL-3B-Instruct   # bỏ trống = tải từ HF
  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations
import requests
import io
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import torch
from fastapi import FastAPI, File, Query, UploadFile
from PIL import Image

from . import auth, audit, config, db, forms, records, redis_client, users
from src.data_pipeline.auto_label import parse_json_safe
from src.models.vlm_registry import (
    VLMSpec,
    build_gen_kwargs,
    images_arg,
    load_processor,
    preprocess_image,
    resolve,
)
from src.utils.cccd_schema import SYSTEM_PROMPT, CardSide, build_user_prompt
INFERENCE_SERVER_URL = config.INFERENCE_SERVER_URL
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Model đang phục vụ. Bỏ trống thì suy từ vlm_meta.json của adapter / từ BASE_MODEL.
MODEL_KEY = os.getenv("MODEL_KEY") or None
# Thư mục chứa TẤT CẢ checkpoint, đặt tên theo quy ước của notebook 02:
# {model_key}-cccd-lora-{front,back}. Đây là cách khuyến nghị — server tự tìm đủ
# adapter của cả hai mặt.
CHECKPOINT_DIR = os.getenv("CHECKPOINT_DIR", "checkpoints")
# Cách cũ (1 adapter duy nhất). Vẫn hỗ trợ; mặt thẻ suy từ tên thư mục.
ADAPTER_DIR = os.getenv("ADAPTER_DIR") or None
# Đường dẫn snapshot base cục bộ; bỏ trống = dùng model_id trên HF của spec.
BASE_MODEL = os.getenv("BASE_MODEL") or None
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))
# Trần số ảnh chạy chung một lần generate. Lô lớn hơn bị cắt thành nhiều chunk —
# client gửi 50 ảnh không được phép làm OOM cả server. Dò số này bằng
# `python scripts/benchmark.py --mode local` trên đúng GPU sẽ deploy.
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "4"))
# Mặt thẻ dùng khi không suy được từ tên file (side=auto + tên file không có
# token front/back). Bỏ trống = lấy adapter đầu tiên có sẵn.
DEFAULT_SIDE = os.getenv("DEFAULT_SIDE") or None

# Tên thư mục checkpoint dùng 'front'/'back', còn CardSide dùng 'truoc'/'sau'.
SIDE_DIR_TOKEN: Dict[CardSide, str] = {CardSide.FRONT: "front", CardSide.BACK: "back"}

# State toàn cục giữ model/processor/spec sau khi load.
#   adapters: {CardSide: tên adapter đã nạp}   active: adapter đang được set_adapter
STATE: dict = {
    "model": None, "processor": None, "spec": None, "adapters": {}, "active": None,
}

# Chỉ có MỘT GPU và MỘT model dùng chung cho mọi request. Endpoint chạy trong
# threadpool của FastAPI (xem `extract_cccd`) nên nhiều request có thể vào cùng
# lúc; khóa này ép chúng xếp hàng ở đúng chỗ `generate` thay vì cùng nhau tranh
# GPU và OOM. Đo throughput thật thì đây chính là điểm nghẽn cần thấy.
#
# Khóa BẮT BUỘC phải bao cả `set_adapter` lẫn `generate`: `set_adapter` đổi trạng
# thái dùng chung của model, nên nếu chỉ khóa `generate` thì thread A có thể gạt
# adapter sang mặt trước ngay giữa lúc thread B đang sinh cho mặt sau.
GPU_LOCK = threading.Lock()


# ── Tìm adapter ─────────────────────────────────────────────────────────────
def discover_adapters(
    model_key: Optional[str],
    checkpoint_dir: str,
    adapter_dir: Optional[str] = None,
) -> Dict[CardSide, Path]:
    """
    Tìm adapter của từng mặt thẻ cho model đang phục vụ.
    """
    if adapter_dir:
        path = Path(adapter_dir)
        if not path.is_dir():
            logger.warning("Không thấy ADAPTER_DIR '%s'", adapter_dir)
            return {}
        # Suy mặt thẻ từ tên thư mục ('...-lora-back' → sau).
        name = path.name.lower()
        for side, token in SIDE_DIR_TOKEN.items():
            if name.endswith(f"-{token}") or f"-{token}-" in name:
                logger.info("ADAPTER_DIR '%s' → mặt %s", path.name, side.value)
                return {side: path}
        logger.warning(
            "Không suy được mặt thẻ từ tên '%s' → dùng adapter này cho MỌI mặt. "
            "Đặt CHECKPOINT_DIR + MODEL_KEY để server tự tìm đủ 2 mặt.", path.name,
        )
        return {CardSide.FRONT: path, CardSide.BACK: path}

    found: Dict[CardSide, Path] = {}

    # Check if they exist in result_front and result_back as requested by user
    # These are expected to be at the project root level, possibly with front/back subdirectories
    backend_dir = Path(__file__).parent.parent  # Go up two levels: backend/ -> project_root/
    logger.debug("Checking for adapters in project root: %s", backend_dir)
    for side, path_name in [(CardSide.FRONT, "result_front"), (CardSide.BACK, "result_back")]:
        # First check in the front/back subdirectories
        candidate_sub = backend_dir / path_name / SIDE_DIR_TOKEN[side]
        logger.debug("Checking for %s adapter at subdir: %s", side.value, candidate_sub)
        if candidate_sub.is_dir():
            adapter_config = candidate_sub / "adapter_config.json"
            if adapter_config.is_file():
                found[side] = candidate_sub
                logger.info("Found %s adapter at: %s", side.value, candidate_sub)
            else:
                logger.warning("Adapter directory %s exists but missing adapter_config.json", candidate_sub)
        else:
            logger.debug("Adapter subdirectory %s does not exist", candidate_sub)

        # If not found in subdir, check directly in the result_front/result_back directory
        if side not in found:
            candidate_root = backend_dir / path_name
            logger.debug("Checking for %s adapter at root: %s", side.value, candidate_root)
            if candidate_root.is_dir():
                adapter_config = candidate_root / "adapter_config.json"
                if adapter_config.is_file():
                    found[side] = candidate_root
                    logger.info("Found %s adapter at: %s", side.value, candidate_root)
                else:
                    logger.warning("Adapter directory %s exists but missing adapter_config.json", candidate_root)
            else:
                logger.debug("Adapter directory %s does not exist", candidate_root)

    if found:
        logger.info("Tìm thấy adapter trong result_front / result_back: %s", found)
        return found

    if not model_key:
        return {}
    root = Path(checkpoint_dir)
    for side, token in SIDE_DIR_TOKEN.items():
        candidate = root / f"{model_key}-cccd-lora-{token}"
        if (candidate / "adapter_config.json").is_file():
            found[side] = candidate
        elif candidate.is_dir():
            logger.warning("'%s' không có adapter_config.json → bỏ qua", candidate)
    return found


def resolve_spec(
    model_key: Optional[str], base_model: Optional[str], adapters: Dict[CardSide, Path]
) -> VLMSpec:
    """
    Suy `VLMSpec` cho model đang serve, theo thứ tự ưu tiên MODEL_KEY → meta → BASE_MODEL.

    `vlm_meta.json` mà train.py ghi cạnh adapter là nguồn chân lý về base model đã
    dùng lúc fine-tune; đối chiếu với BASE_MODEL để bắt sớm trường hợp gắn adapter
    lên base khác họ (output sẽ vô nghĩa).
    """
    trained_on = None
    for path in adapters.values():
        meta_path = path / "vlm_meta.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            trained_on = meta.get("model_id")
            if not model_key and meta.get("model_key"):
                model_key = meta["model_key"]
            break

    spec = resolve(model_key or base_model or "qwen")
    if trained_on and base_model:
        # So theo họ model chứ không so chuỗi: BASE_MODEL thường là đường dẫn
        # snapshot cục bộ ('models/Qwen2.5-VL-3B-Instruct') còn meta ghi HF id.
        try:
            if resolve(base_model).key != resolve(trained_on).key:
                logger.warning(
                    "⚠ BASE_MODEL='%s' khác họ với base lúc train ('%s') — gắn adapter "
                    "lên base khác họ sẽ cho output vô nghĩa.", base_model, trained_on,
                )
        except KeyError:
            logger.info("Không suy được họ model từ BASE_MODEL='%s' (bỏ qua kiểm tra)", base_model)
    return spec


# ── Nạp model ───────────────────────────────────────────────────────────────
def load_inference_model(
    base_model: Optional[str] = None,
    checkpoint_dir: Optional[str] = None,
    model_key: Optional[str] = None,
    adapter_dir: Optional[str] = None,
) -> Tuple[object, object]:
    """
    Nạp base 4-bit MỘT lần rồi gắn adapter của TẤT CẢ các mặt tìm được.
    """
    # QUAY TRỞ LẠI DÙNG AutoModelForImageTextToText 
    from transformers import AutoModelForImageTextToText, BitsAndBytesConfig

    model_key = model_key or MODEL_KEY
    base_model = base_model or BASE_MODEL
    checkpoint_dir = checkpoint_dir if checkpoint_dir is not None else CHECKPOINT_DIR

    adapters = discover_adapters(model_key, checkpoint_dir, adapter_dir)
    spec = resolve_spec(model_key, base_model, adapters)
    
    base_source = base_model or spec.model_id
    STATE["spec"] = spec

    compute_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
        llm_int8_enable_fp32_cpu_offload=True,
    )

    logger.info("Loading base %s [%s] ở 4-bit...", base_source, spec.key)
    
    # Nạp bằng AutoModelForImageTextToText để giữ lại toàn bộ đầu sinh ngôn ngữ (lm_head)
    model = AutoModelForImageTextToText.from_pretrained(
        base_source,
        quantization_config=bnb,
        device_map="auto",
        offload_folder="offload_cache",
        torch_dtype=compute_dtype,
        trust_remote_code=True,
    )

    processor_src = base_source
    loaded: Dict[CardSide, str] = {}
    if adapters:
        from peft import PeftModel

        for index, (side, path) in enumerate(sorted(adapters.items(), key=lambda kv: kv[0].value)):
            name = side.value
            if index == 0:
                model = PeftModel.from_pretrained(model, str(path), adapter_name=name)
            else:
                model.load_adapter(str(path), adapter_name=name)
            loaded[side] = name
            logger.info("Gắn adapter mặt %s ← %s", side.value, path)
            processor_src = str(path)
        missing = [s.value for s in SIDE_DIR_TOKEN if s not in loaded]
        if missing:
            logger.warning("Chưa có adapter cho mặt: %s", ", ".join(missing))
    else:
        logger.warning("Không tìm thấy adapter nào → chạy base thuần (zero-shot)")

    STATE["adapters"] = loaded
    STATE["active"] = None

    processor = load_processor(processor_src, spec)
    set_left_padding(processor)
    model.eval()
    logger.info("✓ Model %s sẵn sàng phục vụ", spec.key)
    return model, processor


def unload_model() -> None:
    """
    Nhả model khỏi VRAM. Dùng khi bench nhiều model liên tiếp trong một process.

    Không có hàm này thì model thứ hai nạp đè lên model thứ nhất còn nguyên trong
    VRAM → OOM ngay ở Llama-11B.
    """
    import gc

    for key in ("model", "processor"):
        STATE[key] = None
    STATE["adapters"] = {}
    STATE["active"] = None
    STATE["spec"] = None
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def set_left_padding(processor) -> None:
    """
    Ép `padding_side='left'` cho đường INFERENCE (train.py vẫn giữ 'right').

    Bắt buộc khi batch > 1 với model decode-only: right-pad đẩy pad vào GIỮA
    prompt và chỗ model bắt đầu sinh, nên sequence ngắn hơn trong lô sẽ sinh tiếp
    ngay sau token pad → output rác. Left-pad còn làm mọi sequence trong lô có
    cùng độ dài prompt, nhờ đó cắt phần sinh bằng `input_ids.shape[1]` mới đúng
    cho cả lô.

    Batch = 1 thì không có pad nào được thêm nên cờ này vô hại — số liệu 1 ảnh
    vẫn khớp evaluate.py.
    """
    tokenizer = getattr(processor, "tokenizer", None)
    if tokenizer is None:
        logger.warning("Processor không có .tokenizer → không đặt được left padding")
        return
    tokenizer.padding_side = "left"
    if getattr(tokenizer, "pad_token", None) is None:
        tokenizer.pad_token = tokenizer.eos_token
    logger.info("Inference dùng padding_side='left' (train dùng 'right')")


# ── Chọn adapter theo mặt thẻ ───────────────────────────────────────────────
def available_sides() -> List[CardSide]:
    """Các mặt thẻ đang có adapter, thứ tự ổn định."""
    return sorted(STATE["adapters"], key=lambda s: s.value)


def serving_side(side: CardSide) -> Optional[CardSide]:
    """
    Quy mặt thẻ của request về mặt thẻ THỰC SỰ dùng để chạy.

    UNKNOWN (side=auto nhưng tên file không có token front/back) → `DEFAULT_SIDE`,
    hoặc adapter đầu tiên có sẵn. Trả None nếu mặt yêu cầu không có adapter.
    """
    sides = available_sides()
    if not STATE["adapters"]:
        return side  # base thuần: prompt vẫn theo mặt, không cần adapter
    if side in STATE["adapters"]:
        return side
    if side == CardSide.UNKNOWN:
        if DEFAULT_SIDE:
            for candidate in sides:
                if candidate.value == DEFAULT_SIDE:
                    return candidate
        return sides[0] if sides else None
    return None


def select_adapter(side: CardSide) -> None:
    """
    Bật adapter của mặt thẻ này. **Phải gọi khi đang giữ `GPU_LOCK`.**

    Chỉ gọi `set_adapter` khi khác adapter đang active — thao tác này rẻ (đổi cờ
    active của các lớp LoRA, không copy trọng số) nhưng vẫn không nên gọi thừa.
    """
    name = STATE["adapters"].get(side)
    if name is None or STATE["active"] == name:
        return
    STATE["model"].set_adapter(name)
    STATE["active"] = name


def build_messages(image: Image.Image, side: CardSide) -> list:
    """Dựng khung hội thoại cho 1 ảnh — giống hệt evaluate.py và lúc train."""
    return [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": build_user_prompt(side)},
            ],
        },
    ]


# Giữ tên cũ cho code ngoài đang import.
build_batch_messages = build_messages


@torch.no_grad()
def run_inference_batch(
    images: Sequence[Image.Image],
    sides: Sequence[CardSide],
    max_batch: Optional[int] = None,
) -> List[str]:
    """
    Chạy N ảnh theo lô, trả list chuỗi text thô (chưa parse), đúng thứ tự đầu vào.
    """
    if len(images) != len(sides):
        raise ValueError(f"len(images)={len(images)} != len(sides)={len(sides)}")
    if not images:
        return []

    model, processor, spec = STATE["model"], STATE["processor"], STATE["spec"]
    gen_kwargs = build_gen_kwargs(MAX_NEW_TOKENS)
    chunk_size = max_batch or MAX_BATCH_SIZE
    outputs: List[str] = [""] * len(images)

    groups: Dict[CardSide, List[int]] = {}
    for index, side in enumerate(sides):
        groups.setdefault(side, []).append(index)

    for side, indices in groups.items():
        for start in range(0, len(indices), chunk_size):
            slots = indices[start : start + chunk_size]
            chunk_images = [images[i] for i in slots]

            for image in chunk_images:
                preprocess_image(image, spec)

            texts = [
                processor.apply_chat_template(
                    build_messages(img, side), tokenize=False, add_generation_prompt=True
                )
                for img in chunk_images
            ]
            inputs = processor(
                text=texts,
                images=images_arg(chunk_images, spec),
                return_tensors="pt",
                padding=True,
            )
            inputs = {k: v.to(model.device) for k, v in inputs.items()}

            with GPU_LOCK:
                select_adapter(side)

                gen_func = None
                
                # 1. Model thuần có sẵn generate (Qwen, Llama...)
                if hasattr(model, "generate"):
                    gen_func = model.generate
                    
                # 2. InternVL thuần (chưa bọc LoRA)
                elif hasattr(model, "language_model") and hasattr(model.language_model, "generate"):
                    gen_func = model.language_model.generate
                    
                # 3. Model đã bị bọc qua PeftModel (LoRA)
                elif hasattr(model, "base_model"):
                    base = model.base_model
                    # Base model chuẩn
                    if hasattr(base, "generate"):
                        gen_func = base.generate
                    # Base model là InternVL (phiên bản cấu trúc cũ)
                    elif hasattr(base, "language_model") and hasattr(base.language_model, "generate"):
                        gen_func = base.language_model.generate
                    # Base model là InternVL (phiên bản cấu trúc mới bị lồng thêm 1 lớp .model)
                    elif hasattr(base, "model") and hasattr(base.model, "language_model") and hasattr(base.model.language_model, "generate"):
                        gen_func = base.model.language_model.generate

                if gen_func is None:
                    raise AttributeError(
                        f"Không tìm thấy phương thức generate trên model kiểu {type(model)}. "
                        "Cấu trúc phân cấp không khớp với bất kỳ pattern nào đã biết."
                    )

                output_ids = gen_func(**inputs, **gen_kwargs)

            generated = output_ids[:, inputs["input_ids"].shape[1] :]
            decoded = processor.batch_decode(generated, skip_special_tokens=True)
            for slot, text in zip(slots, decoded):
                outputs[slot] = text.strip()

    return outputs


def run_inference(image: Image.Image, side: CardSide) -> str:
    """
    Chạy 1 ảnh qua model, trả chuỗi text sinh ra (chưa parse).

    Args:
        image: Ảnh PIL RGB.
        side: Mặt thẻ (quyết định prompt VÀ adapter).

    Returns:
        Chuỗi output thô của model.
    """
    return run_inference_batch([image], [side])[0]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo DB/Redis và bỏ qua việc nạp model local."""
    db.init_db()
    redis_client.get_redis()

    logger.info(f"🚀 Chạy chế độ Proxy: Chuyển tiếp AI inference lên {INFERENCE_SERVER_URL}")
    
    yield
    
    db.close_db()


app = FastAPI(title="CCCD Extraction API", version="2.1.0", lifespan=lifespan)

# ── P1: xác thực & quản lý tài khoản — toàn bộ app API gom dưới /api/v1 ─────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(forms.router, prefix="/api/v1")

# ── P2: hồ sơ trích xuất + duyệt (lịch sử từ PostgreSQL) ───────────────────
app.include_router(records.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    """Trạng thái model + DB + Redis + trần batch."""
    spec = STATE["spec"]
    return {
        "status": "ok",
        "model_loaded": STATE["model"] is not None,
        "lite_mode": config.SKIP_MODEL_LOAD,
        "db": db.ping(),
        "redis": redis_client.get_redis() is not None,
        "model_key": spec.key if spec else None,
        "model_id": spec.model_id if spec else None,
        "params_b": spec.params_b if spec else None,
        "sides": [side.value for side in available_sides()],
        "max_batch_size": MAX_BATCH_SIZE,
    }


def decide_side(side: str, filename: Optional[str]) -> CardSide:
    """'truoc'/'sau' để ép mặt thẻ; giá trị khác ('auto') thì suy từ tên file."""
    if side == CardSide.FRONT.value:
        return CardSide.FRONT
    if side == CardSide.BACK.value:
        return CardSide.BACK
    from src.utils.cccd_schema import infer_side_from_filename

    return infer_side_from_filename(filename or "")


def resolve_or_error(side: str, filename: Optional[str]) -> Tuple[Optional[CardSide], Optional[str]]:
    """Quy request về mặt thẻ chạy được, hoặc trả thông báo lỗi rõ ràng."""
    requested = decide_side(side, filename)
    effective = serving_side(requested)
    if effective is None:
        have = [s.value for s in available_sides()] or ["(không có adapter nào)"]
        return None, (
            f"Model '{STATE['spec'].key}' chưa có adapter cho mặt '{requested.value}'. "
            f"Đang có: {', '.join(have)}."
        )
    return effective, None


def decode_upload(file: UploadFile) -> Tuple[Optional[Image.Image], Optional[str]]:
    """Đọc UploadFile → (ảnh RGB, None) hoặc (None, thông báo lỗi)."""
    # Đọc đồng bộ qua `.file` vì endpoint là `def` (chạy trong threadpool), không
    # phải `async def` — ở đây không có event loop để `await`.
    try:
        return Image.open(io.BytesIO(file.file.read())).convert("RGB"), None
    except Exception as exc:  # noqa: BLE001
        return None, f"Không đọc được ảnh: {exc}"


def build_result(filename: Optional[str], card_side: CardSide, raw: str) -> dict:
    """Parse output thô của model → payload trả về cho client."""
    parsed = parse_json_safe(raw)
    if parsed is not None and card_side != CardSide.UNKNOWN:
        parsed.setdefault("mat_the", card_side.value)
    return {
        "filename": filename,
        "side": card_side.value,
        "parse_ok": parsed is not None,
        "data": parsed if parsed is not None else None,
        "raw": raw if parsed is None else None,
    }


# `def` chứ KHÔNG phải `async def`: `run_inference` chặn hoàn toàn (generate trên
# GPU, không await gì). Để `async def` thì nó chạy thẳng trên event loop và chặn
# TOÀN BỘ server trong lúc sinh — request đồng thời xếp hàng vô hình và cả
# /health cũng treo, nên số đo concurrency sẽ sai. Là `def` thì FastAPI đẩy sang
# threadpool: request vào song song, chỉ nghẽn đúng ở GPU_LOCK.
@app.post("/extract-cccd/")
def extract_cccd(
    file: UploadFile = File(..., description="Ảnh CCCD (jpg/png)"),
    side: str = Query("auto", description="truoc | sau | auto (suy từ tên file)"),
) -> dict:
    """
    Proxy endpoint: Tiếp nhận ảnh từ Flutter, gửi sang Colab GPU và in log kiểm tra.
    """
    try:
        # 1. Đọc file upload
        file_bytes = file.file.read()
        files_payload = {"file": (file.filename, file_bytes, file.content_type)}

        # 2. Chuyển tiếp request sang Colab Inference Server
        logger.info(f"🚀 [PROXY REQUEST] Gửi ảnh '{file.filename}' (side={side}) sang Colab...")
        
        response = requests.post(
            f"{INFERENCE_SERVER_URL}/extract-cccd/",
            params={"side": side},
            files=files_payload,
            timeout=120,
        )
        
        result = response.json()

        # 3. 🔍 IN LOG CHI TIẾT KẾT QUẢ TRẢ VỀ TỪ COLAB
        card_side = result.get("side", side)
        logger.info(f"================ COLAB RESPONSE [{card_side}] ================")
        logger.info(f"📁 Filename : {result.get('filename')}")
        logger.info(f"⏱️ Latency  : {result.get('latency_ms')} ms")
        logger.info(f"✅ Parse OK : {result.get('parse_ok')}")
        
        if result.get("data"):
            logger.info("📄 PARSED DATA (JSON từ Model):")
            logger.info(json.dumps(result.get("data"), ensure_ascii=False, indent=2))
        else:
            logger.warning(f"⚠️ RAW OUTPUT (Không parse được JSON): {result.get('raw')}")
            logger.warning(f"⚠️ Lỗi (nếu có): {result.get('error')}")
            
        logger.info("============================================================")

        return result

    except Exception as exc:
        logger.exception("❌ Lỗi kết nối Proxy tới Colab Server")
        return {"filename": file.filename, "error": f"Lỗi Proxy Colab: {str(exc)}"}


@app.post("/extract-cccd/batch")
def extract_cccd_batch(
    files: List[UploadFile] = File(..., description="Nhiều ảnh CCCD (jpg/png)"),
    side: str = Query("auto", description="truoc | sau | auto (suy từ tên từng file)"),
) -> dict:
    try:
        # Gói toàn bộ list files để gửi đi
        files_payload = [("files", (f.filename, f.file, f.content_type)) for f in files]
        
        response = requests.post(
            f"{INFERENCE_SERVER_URL}/extract-cccd/batch",
            params={"side": side},
            files=files_payload,
            timeout=300 # Chờ lô lớn
        )
        return response.json()
    except Exception as exc:
        logger.exception("Lỗi kết nối tới Colab Server (Batch)")
        return {"error": f"Lỗi Proxy Colab: {str(exc)}", "n_images": len(files)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
