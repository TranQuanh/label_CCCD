"""
vlm_registry.py
===============
Sổ đăng ký cấu hình cho từng họ VLM tham gia so sánh fine-tune (xem
VLM_COMPARISON_PLAN.md). Mục đích duy nhất: **giữ mọi thứ có thể giữ giống nhau**
giữa các model, và cô lập những thứ *buộc phải* khác vì kiến trúc.

Nguyên tắc thiết kế — đọc trước khi thêm model mới:

  1. GIỐNG NHAU TUYỆT ĐỐI (khai báo ở cấp module, không cho override per-model):
     - `SHARED_LORA_TARGETS`: cùng bộ 7 ma trận attn+MLP.
     - `SHARED_IMAGE_MAX_SIDE`: cùng số pixel đầu vào (thumbnail 1024px).
     Mọi model nhìn thấy **đúng cùng một tập pixel**; việc chia tile / resize tiếp
     theo là quyết định của riêng kiến trúc đó, và đó chính là biến ta muốn đo.

  2. KHÁC NHAU DO KIẾN TRÚC ÉP BUỘC (khai báo per-model trong `VLMSpec`):
     - Tên module vision (để đóng băng + chặn LoRA gắn vào).
     - Kwarg riêng của processor (Qwen dùng min/max_pixels, InternVL dùng
       min/max_patches, Llama không có).
     - `max_length`: hệ quả của việc token ảnh có nở vào chuỗi text hay không.
     Những khác biệt này PHẢI được ghi rõ trong báo cáo là "do kiến trúc", không
     phải "do tuning riêng cho model nào".

Vì sao vẫn giữ thumbnail 1024px cho cả 3 model (khác với bản nháp đầu của plan
doc): nó biến một tiểu tiết của Qwen thành **biến kiểm soát dùng chung** — cùng
input pixel cho mọi model — và đồng thời giữ nguyên y hệt đường Qwen đang chạy,
nên kết quả anchor cũ vẫn so sánh được, không bị regression.

Smoke test (chỉ tải processor, KHÔNG tải trọng số — chạy được trên CPU):

    python -m src.models.vlm_registry --model internvl --image data/Front/xxx_front.jpg
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)


# ── Biến kiểm soát dùng chung cho MỌI model ─────────────────────────────────
# Các ma trận linear được gắn LoRA: attention + MLP của phần NGÔN NGỮ.
# Giữ y nguyên bộ này cho mọi model để ngân sách LoRA tương đương nhau.
SHARED_LORA_TARGETS: Tuple[str, ...] = (
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
)

# Cạnh dài nhất của ảnh đầu vào, áp dụng ở CẢ train/eval/serve cho MỌI model.
# Đây là bất biến quan trọng nhất của pipeline: lệch con số này giữa train và
# eval là số token ảnh lệch theo → mask prompt sai.
SHARED_IMAGE_MAX_SIDE: int = 1024

# Siêu tham số QLoRA dùng chung (train.py lấy làm default CLI).
SHARED_LORA_R: int = 16
SHARED_LORA_ALPHA: int = 32
SHARED_LORA_DROPOUT: float = 0.05


@dataclass(frozen=True)
class VLMSpec:
    """Cấu hình của một model trong bộ so sánh."""

    key: str
    model_id: str
    # Tên họ kiến trúc (chỉ để ghi log/report, không dùng để branch logic).
    family: str
    # Tổng số tham số (tỉ) — chỉ để in vào bảng báo cáo. Không đếm từ model vì
    # trọng số 4-bit đã bị đóng gói lại nên `numel()` không phản ánh đúng.
    params_b: float = 0.0
    # Dung lượng snapshot bf16 trên đĩa (GB, xấp xỉ) — dùng để chọn nơi tải về:
    # Drive free chỉ có 15GB, không chứa nổi Llama-11B (~21GB). Xem `resolve_model_dir`.
    weights_gb: float = 0.0
    # Kwarg truyền cho AutoProcessor.from_pretrained. Riêng theo từng họ.
    processor_kwargs: Dict[str, Any] = field(default_factory=dict)
    # Tiền tố tên module của vision tower: dùng để đóng băng VÀ để chặn LoRA.
    vision_prefixes: Tuple[str, ...] = ()
    # Trần độ dài chuỗi text (đã gồm token ảnh nếu kiến trúc nở chúng vào text).
    max_length: int = 1536
    # Token ảnh có nở vào chuỗi input_ids hay không.
    #   True  → Qwen (dynamic resolution), InternVL (tiling): phải nới max_length.
    #   False → Llama-3.2-Vision: ảnh vào qua cross-attention, chuỗi text ngắn.
    image_tokens_in_text: bool = True
    # Processor yêu cầu images dạng lồng [[img], [img], ...] thay vì phẳng.
    nested_images: bool = False
    # Bản transformers tối thiểu.
    min_transformers: str = "4.45.0"
    # Model gated trên HF (phải accept license + huggingface-cli login).
    gated: bool = False
    notes: str = ""

    @property
    def lora_target_regex(self) -> str:
        """Regex target_modules đã chặn sẵn vision tower (xem `build_lora_target_regex`)."""
        return build_lora_target_regex(SHARED_LORA_TARGETS, self.vision_prefixes)


def build_lora_target_regex(
    targets: Sequence[str], vision_prefixes: Sequence[str]
) -> str:
    """
    Dựng regex `target_modules` cho PEFT, loại trừ mọi module thuộc vision tower.

    Vì sao cần regex thay vì list tên trần: cả InternViT lẫn ViT của Llama-3.2 đều
    đặt tên linear là `q_proj/k_proj/v_proj` — trùng y hệt tên trong language model.
    Nếu truyền list tên trần thì PEFT sẽ gắn adapter lên chính các lớp vision đã bị
    đóng băng ở 4-bit. (Qwen2.5-VL không gặp lỗi này chỉ vì ViT của nó đặt tên
    `qkv`/`proj`.) Dùng `exclude_modules` cũng được nhưng chỉ có ở PEFT mới; regex
    chạy trên mọi bản.

    PEFT so khớp target_modules dạng str bằng `re.fullmatch`, nên negative lookahead
    hoạt động bình thường.

    Args:
        targets: tên các linear cần gắn LoRA (không có tiền tố).
        vision_prefixes: tên module vision cần loại trừ.

    Returns:
        Chuỗi regex dùng làm `LoraConfig.target_modules`.
    """
    suffix = "|".join(re.escape(t) for t in targets)
    if not vision_prefixes:
        return rf".*\.(?:{suffix})$"
    blocked = "|".join(re.escape(p) for p in vision_prefixes)
    return rf"^(?!.*\b(?:{blocked})\b).*\.(?:{suffix})$"


# ── Sổ đăng ký ──────────────────────────────────────────────────────────────
REGISTRY: Dict[str, VLMSpec] = {
    "qwen": VLMSpec(
        key="qwen",
        model_id="Qwen/Qwen2.5-VL-3B-Instruct",
        family="qwen2_5_vl",
        params_b=3.7,
        weights_gb=7.5,
        # min/max_pixels khống chế số token ảnh (mỗi token ≈ 28x28 px sau merge 2x2).
        # max_pixels=1280*28*28 → trần 1280 token ảnh.
        processor_kwargs={"min_pixels": 256 * 28 * 28, "max_pixels": 1280 * 28 * 28},
        vision_prefixes=("visual",),
        # Đo thực tế trên dữ liệu CCCD sau thumbnail 1024px (2026-07-26):
        #   mặt sau  (1024x644, 850 token ảnh): full seq max 1460, đáp án 50-60 token
        #   mặt trước(1024x576, 776 token ảnh): full seq max 1454, đáp án 107-162 token
        # Với trần cũ 1536 thì HIỆN TẠI chưa sample nào bị cắt (headroom 82 token).
        # Nhưng headroom phụ thuộc TỈ LỆ ẢNH: cùng văn bản mặt trước mà ghép ảnh tỉ
        # lệ như mặt sau (850 token) thì full seq lên 1527 — chỉ còn 9 token. Ảnh
        # vuông hơn (vd 1024x768 ≈ 1000 token ảnh) là tràn thẳng → cắt mất JSON →
        # loss 0.0. Nâng trần lên 2048 KHÔNG đổi kết quả của sample đã vừa (padding
        # là động, pad tới sample dài nhất trong batch chứ không tới max_length).
        max_length=2048,
        image_tokens_in_text=True,
        min_transformers="4.49.0",
        notes="Anchor — model đang fine-tune. Native dynamic resolution ViT + M-RoPE, early fusion.",
    ),
    "internvl": VLMSpec(
        key="internvl",
        model_id="OpenGVLab/InternVL3_5-2B-HF",
        family="internvl",
        params_b=2.3,
        weights_gb=4.5,
        # Dynamic tiling 448px, ~256 token/tile. max_patches=6 → tối đa 6 tile
        # (+1 tile thumbnail) ≈ 1536-1792 token ảnh, cùng tầm ngân sách token với
        # Qwen (~850-1280). ĐỪNG để mặc định 12: sẽ >3300 token → tràn max_length
        # → cắt mất phần JSON → loss = 0.0.
        processor_kwargs={"crop_to_patches": True, "min_patches": 1, "max_patches": 6},
        vision_prefixes=("vision_tower",),
        max_length=2560,
        image_tokens_in_text=True,
        min_transformers="4.52.1",
        notes="InternViT-300M + Qwen3-2B, dynamic tiling 448px, early fusion.",
    ),
    "llama_vision": VLMSpec(
        key="llama_vision",
        model_id="meta-llama/Llama-3.2-11B-Vision-Instruct",
        family="mllama",
        params_b=10.6,
        # 5 shard safetensors ≈ 21GB — KHÔNG vừa Google Drive free (15GB).
        weights_gb=21.5,
        processor_kwargs={},
        vision_prefixes=("vision_model",),
        # Token ảnh KHÔNG nở vào chuỗi text (vào qua cross-attention) nên chuỗi chỉ
        # ~700 token; để 2048 cho đồng nhất với Qwen, không tốn thêm gì.
        max_length=2048,
        image_tokens_in_text=False,
        nested_images=True,
        min_transformers="4.45.0",
        gated=True,
        notes=(
            "ViT-H tile 560px + cross-attention adapter. LoRA sẽ gắn cả lên "
            "`cross_attn` của language model — đó là giao diện vision→text của kiến "
            "trúc này, tương ứng với việc Qwen self-attend lên token ảnh. Hệ quả: "
            "số tham số trainable nhiều hơn 2 model kia → phải báo cáo cột "
            "trainable_params_pct để minh bạch."
        ),
    ),
}

# Suy ra key từ model_id/đường dẫn checkpoint khi người dùng không truyền key.
_MATCH_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("internvl", (r"internvl",)),
    ("llama_vision", (r"llama.*vision", r"mllama")),
    ("qwen", (r"qwen.*vl",)),
)


def resolve(name: str) -> VLMSpec:
    """
    Tra `VLMSpec` từ key, model_id, hoặc một chuỗi có chứa tên model.

    Args:
        name: "internvl", "OpenGVLab/InternVL3_5-2B-HF", hoặc
              "checkpoints/internvl3_5-2b-cccd-lora".

    Returns:
        VLMSpec khớp.

    Raises:
        KeyError: không suy ra được họ model.
    """
    if name in REGISTRY:
        return REGISTRY[name]

    lowered = name.lower().replace("\\", "/")
    for spec in REGISTRY.values():
        if spec.model_id.lower() == lowered:
            return spec
    for key, patterns in _MATCH_RULES:
        if any(re.search(p, lowered) for p in patterns):
            return REGISTRY[key]

    raise KeyError(
        f"Không suy được họ VLM từ '{name}'. Truyền --model_key một trong: "
        f"{sorted(REGISTRY)}, hoặc thêm entry mới vào REGISTRY."
    )


def check_available(spec: VLMSpec) -> Tuple[bool, str]:
    """
    Kiểm tra điều kiện chạy được của một model (không tải trọng số).

    Trả về (True, "ok") hoặc (False, lý do) — để caller bỏ qua êm một model thiếu
    điều kiện thay vì làm chết cả run.
    """
    try:
        import transformers
    except ImportError:
        return False, "chưa cài transformers"

    current = transformers.__version__
    try:
        from packaging.version import Version

        if Version(current) < Version(spec.min_transformers):
            return False, f"cần transformers>={spec.min_transformers}, đang có {current}"
    except ImportError:  # pragma: no cover - packaging luôn có cùng transformers
        logger.warning("Không có `packaging` → bỏ qua kiểm tra version transformers")

    if spec.gated:
        logger.info(
            "%s là model gated: cần accept license trên HF + `huggingface-cli login`",
            spec.model_id,
        )
    return True, "ok"


# ── Snapshot trọng số cục bộ ────────────────────────────────────────────────
# File không phải trọng số cần cho inference: bản .pth gốc của Meta (nặng gấp đôi
# safetensors), bản lượng tử hoá GGUF, và checkpoint TF/Flax.
SNAPSHOT_IGNORE: Tuple[str, ...] = ("*.pth", "original/*", "*.gguf", "*.msgpack", "*.h5")

# Nơi tải model khi Drive không đủ chỗ: SSD của máy Colab (~100GB, mất khi ngắt phiên).
COLAB_SSD_MODELS: str = "/content/models"

# Hệ số dự phòng khi so dung lượng còn trống với kích thước snapshot.
_DISK_HEADROOM: float = 1.15


def snapshot_complete(model_dir: Union[str, "Path"]) -> Tuple[bool, str]:
    """
    Kiểm tra một thư mục model tải về đã ĐỦ trọng số chưa (chỉ đọc metadata, rất rẻ).

    Vì sao cần: `snapshot_download` tải file nhỏ (config, index, tokenizer) TRƯỚC rồi
    mới tới các shard nặng. Nếu bị đứt giữa chừng — hết dung lượng Drive, Colab
    disconnect — thì `config.json` vẫn nằm đó. Guard kiểu `if not
    (dir/'config.json').exists()` sẽ kết luận nhầm là "đã có sẵn", bỏ qua việc tải
    tiếp, và lỗi chỉ nổ ra rất muộn ở `from_pretrained`:

        FileNotFoundError: ... /model-00001-of-00005.safetensors

    Hàm này đối chiếu với `model.safetensors.index.json` nên bắt được cả trường hợp
    thiếu shard lẫn shard bị ghi dở (tổng dung lượng nhỏ hơn `metadata.total_size`).

    Args:
        model_dir: thư mục snapshot cục bộ.

    Returns:
        (True, "ok") hoặc (False, lý do đọc được).
    """
    directory = Path(model_dir)
    if not (directory / "config.json").is_file():
        return False, "chưa có config.json"

    index_path = directory / "model.safetensors.index.json"
    if not index_path.is_file():
        # Model 1 shard: không có file index.
        for single in ("model.safetensors", "pytorch_model.bin"):
            if (directory / single).is_file():
                return True, "ok"
        return False, "không có file trọng số nào"

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        shards = sorted(set(index["weight_map"].values()))
    except (ValueError, KeyError, OSError) as exc:
        return False, f"index shard hỏng ({exc})"

    missing = [s for s in shards if not (directory / s).is_file()]
    if missing:
        return False, f"thiếu {len(missing)}/{len(shards)} shard (vd {missing[0]})"

    # Header safetensors nằm ngoài `total_size`, nên tổng file thật luôn PHẢI lớn hơn.
    # Nhỏ hơn ⇒ có shard bị ghi dở (thường do hết chỗ giữa chừng).
    total_size = index.get("metadata", {}).get("total_size")
    if total_size:
        on_disk = sum((directory / s).stat().st_size for s in shards)
        if on_disk < total_size:
            return False, (
                f"shard ghi dở: {on_disk / 2**30:.1f}GB trên đĩa < "
                f"{total_size / 2**30:.1f}GB theo index"
            )
    return True, "ok"


def free_gb(path: Union[str, "Path"]) -> Optional[float]:
    """Dung lượng trống (GB) của ổ chứa `path`; dò ngược lên thư mục cha đã tồn tại."""
    directory = Path(path).resolve()
    for candidate in (directory, *directory.parents):
        if candidate.exists():
            try:
                return shutil.disk_usage(str(candidate)).free / 2**30
            except OSError:
                return None
    return None


def resolve_model_dir(
    spec_or_id: Union[VLMSpec, str],
    drive_models_dir: Union[str, "Path"],
    ssd_models_dir: Union[str, "Path"] = COLAB_SSD_MODELS,
    weights_gb: Optional[float] = None,
) -> Path:
    """
    Chọn nơi đặt snapshot base model: Drive (bền) hay SSD Colab (to nhưng tạm).

    Mặc định luôn ưu tiên Drive để model sống sót qua các lần Colab ngắt. Nhưng
    Llama-3.2-11B-Vision nặng ~21GB trong khi Drive free chỉ có 15GB → tải được nửa
    chừng rồi chết, để lại thư mục thiếu shard. Trường hợp đó rơi về SSD `/content`
    (~100GB): trọng số tải lại được, chỉ có checkpoint mới là thứ bắt buộc phải giữ
    trên Drive.

    Thứ tự ưu tiên:
      1. Nơi nào ĐÃ có snapshot đủ file thì dùng nơi đó (không tải lại).
      2. Drive, nếu còn trống >= 1.15 × `weights_gb`.
      3. SSD Colab.

    Args:
        spec_or_id: `VLMSpec`, hoặc model_id dạng chuỗi (khi đó truyền `weights_gb`).
        drive_models_dir: thư mục `models/` trên Drive.
        ssd_models_dir: thư mục models trên SSD của máy Colab.
        weights_gb: kích thước snapshot; mặc định lấy từ spec.

    Returns:
        Đường dẫn thư mục model nên dùng (có thể chưa tồn tại).
    """
    if isinstance(spec_or_id, VLMSpec):
        model_id = spec_or_id.model_id
        size_gb = spec_or_id.weights_gb if weights_gb is None else weights_gb
    else:
        model_id = spec_or_id
        size_gb = weights_gb or 0.0

    name = model_id.split("/")[-1]
    on_drive = Path(drive_models_dir) / name
    on_ssd = Path(ssd_models_dir) / name

    for candidate in (on_drive, on_ssd):
        ok, _ = snapshot_complete(candidate)
        if ok:
            logger.info("Dùng snapshot đã có: %s", candidate)
            return candidate

    if not size_gb:
        return on_drive

    free = free_gb(on_drive)
    needed = size_gb * _DISK_HEADROOM
    if free is None or free >= needed:
        return on_drive

    logger.warning(
        "Drive chỉ còn %.1fGB, cần ~%.1fGB cho %s → tải xuống SSD Colab %s "
        "(mất khi ngắt phiên, phải tải lại ở notebook sau; checkpoint vẫn nằm trên Drive)",
        free, needed, name, on_ssd,
    )
    return on_ssd


def ensure_snapshot(
    spec_or_id: Union[VLMSpec, str],
    model_dir: Union[str, "Path"],
    hf_token: Optional[str] = None,
) -> Path:
    """
    Đảm bảo `model_dir` có đủ trọng số; thiếu thì tải (resume được) rồi kiểm tra lại.

    Thay cho guard `if not config.json.exists()` — xem `snapshot_complete` để biết
    guard đó sai ở đâu. `snapshot_download` tự bỏ qua file đã tải xong nên gọi lại
    sau khi đứt mạng là tải tiếp, không tải lại từ đầu.

    Raises:
        RuntimeError: tải xong mà vẫn thiếu file (thường là hết dung lượng đĩa).
    """
    from huggingface_hub import snapshot_download

    model_id = spec_or_id.model_id if isinstance(spec_or_id, VLMSpec) else spec_or_id
    directory = Path(model_dir)

    ok, reason = snapshot_complete(directory)
    if ok:
        logger.info("Snapshot đã đủ file: %s", directory)
        return directory

    free = free_gb(directory)
    logger.info(
        "Tải %s → %s (%s%s)", model_id, directory, reason,
        f"; đĩa còn {free:.1f}GB" if free is not None else "",
    )
    directory.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=model_id,
        local_dir=str(directory),
        ignore_patterns=list(SNAPSHOT_IGNORE),
        token=hf_token,
    )

    ok, reason = snapshot_complete(directory)
    if not ok:
        free = free_gb(directory)
        disk = f" Đĩa còn {free:.1f}GB." if free is not None else ""
        raise RuntimeError(
            f"Tải xong nhưng snapshot vẫn thiếu file tại {directory}: {reason}.{disk} "
            f"Thường là hết dung lượng đĩa — xoá bớt trên Drive, hoặc đặt "
            f"ssd_models_dir='{COLAB_SSD_MODELS}' để tải xuống SSD Colab."
        )
    logger.info("✓ Snapshot đủ file: %s", directory)
    return directory


# ── Tiền xử lý ảnh (dùng chung train/eval/serve) ────────────────────────────
def preprocess_image(image, spec: Optional[VLMSpec] = None):
    """
    Chuẩn hóa ảnh đầu vào — **hàm duy nhất** được cả train/eval/serve gọi.

    Thu nhỏ về `SHARED_IMAGE_MAX_SIDE` (giữ tỉ lệ) để:
      - mọi model nhận cùng một lượng pixel → so sánh công bằng;
      - token ảnh không phình tràn `max_length` nuốt mất phần JSON (từng gây loss=0.0);
      - tránh OOM với ảnh gốc độ phân giải cao.

    `spec` hiện chưa dùng nhưng giữ trong chữ ký để nếu sau này có model buộc phải
    resize khác thì chỉ sửa ở đây, không phải sửa 3 call site.

    Args:
        image: PIL.Image (bị sửa in-place, giống hành vi cũ của collator).
        spec: VLMSpec (tùy chọn).

    Returns:
        Chính ảnh đó sau khi thu nhỏ.
    """
    from PIL import Image as _Image

    image.thumbnail((SHARED_IMAGE_MAX_SIDE, SHARED_IMAGE_MAX_SIDE), _Image.Resampling.LANCZOS)
    return image


def images_arg(images: List[Any], spec: VLMSpec) -> List[Any]:
    """Bọc list ảnh theo đúng dạng processor của từng họ mong đợi."""
    if spec.nested_images:
        return [[img] for img in images]
    return images


# ── Tham số sinh (dùng chung eval/serve/notebook) ───────────────────────────
def build_gen_kwargs(max_new_tokens: int = 512) -> Dict[str, Any]:
    """
    Tham số sinh DÙNG CHUNG cho mọi model và mọi chế độ (zero-shot / fine-tuned).

    Bắt buộc ép greedy tường minh: `generation_config.json` của mỗi model có mặc
    định sampling khác nhau. Qwen2.5-VL-3B-Instruct chẳng hạn mặc định
    `do_sample=True, temperature=1e-06, top_k=50, repetition_penalty=1.05`.
    Nếu để mặc định thì mỗi model được sinh bằng một chiến lược decode khác nhau và
    kết quả so sánh mất ý nghĩa — chưa kể không tái lập được.

    `repetition_penalty` phải ép về 1.0 vì cùng lý do (mỗi model một mặc định), và
    vì phạt lặp là có hại cho đầu ra JSON — JSON vốn lặp lại `", "`, `": "`, dấu
    ngoặc kép và tên trường theo đúng cấu trúc.
    """
    return {
        "max_new_tokens": max_new_tokens,
        "do_sample": False,
        "num_beams": 1,
        "temperature": None,
        "top_p": None,
        "top_k": None,
        "repetition_penalty": 1.0,
    }


# ── Processor ───────────────────────────────────────────────────────────────
def load_processor(source: str, spec: VLMSpec):
    """
    Tải AutoProcessor và áp `spec.processor_kwargs`.

    Thử truyền kwargs ngay vào `from_pretrained` (đường đã biết là chạy đúng với
    Qwen). Nếu bản transformers hiện tại không nhận kwarg đó thì tải trơn rồi gán
    thuộc tính lên `processor.image_processor` — cách nào thành công cũng được log
    rõ, vì đây là tham số quyết định ngân sách token ảnh.

    Args:
        source: model_id trên HF, hoặc thư mục adapter (đã lưu processor).
        spec: VLMSpec.

    Returns:
        AutoProcessor đã cấu hình.
    """
    from transformers import AutoProcessor

    kwargs = dict(spec.processor_kwargs)
    try:
        processor = AutoProcessor.from_pretrained(source, trust_remote_code=True, **kwargs)
        if kwargs:
            logger.info("Processor %s: áp kwargs qua from_pretrained %s", spec.key, kwargs)
        return processor
    except (TypeError, ValueError) as exc:
        logger.warning(
            "from_pretrained không nhận %s (%s) → tải trơn rồi gán thuộc tính",
            list(kwargs), exc,
        )

    processor = AutoProcessor.from_pretrained(source, trust_remote_code=True)
    image_processor = getattr(processor, "image_processor", None)
    for name, value in kwargs.items():
        target = image_processor if hasattr(image_processor, name) else None
        if target is None:
            logger.warning(
                "Processor %s không có thuộc tính '%s' → BỎ QUA. Ngân sách token ảnh "
                "có thể lệch so với các model khác, chạy `python -m "
                "src.models.vlm_registry --model %s --image <ảnh>` để kiểm tra.",
                spec.key, name, spec.key,
            )
            continue
        setattr(target, name, value)
        logger.info("Processor %s: đặt image_processor.%s = %r", spec.key, name, value)
    return processor


# ── Kiểm tra sau khi gắn LoRA ───────────────────────────────────────────────
def assert_no_vision_lora(model, spec: VLMSpec) -> None:
    """
    Chốt an toàn: không tham số nào thuộc vision tower được phép trainable.

    Bắt đúng lỗi mô tả ở mục 5.1 của plan doc — LoRA gắn nhầm vào vision tower vì
    trùng tên `q_proj/k_proj/v_proj`.

    Raises:
        RuntimeError: nếu có param trainable nằm trong vision tower.
    """
    if not spec.vision_prefixes:
        return
    leaked = [
        name
        for name, param in model.named_parameters()
        if param.requires_grad and any(p in name for p in spec.vision_prefixes)
    ]
    if leaked:
        raise RuntimeError(
            f"LoRA/gradient đã lọt vào vision tower của {spec.key} "
            f"({len(leaked)} param, vd: {leaked[:3]}). "
            f"Kiểm tra vision_prefixes={spec.vision_prefixes} và lora_target_regex."
        )
    logger.info("✓ Vision tower %s đã đóng băng hoàn toàn", spec.vision_prefixes)


# ── Probe ngân sách token ảnh ───────────────────────────────────────────────
def probe_image_tokens(processor, spec: VLMSpec, image, prompt_text: str) -> Dict[str, int]:
    """
    Đo số token ảnh mà processor thực sự sinh ra cho 1 ảnh — KHÔNG cần tải model.

    Cách đo không phụ thuộc kiến trúc: so độ dài chuỗi khi có ảnh với độ dài khi
    chỉ tokenize text. Chênh lệch chính là phần token ảnh nở ra.

    Dùng để xác nhận các model có ngân sách token ảnh tương đương nhau — điều kiện
    cần cho việc so sánh công bằng.

    Returns:
        dict gồm `seq_len`, `text_only_len`, `image_tokens`, `max_length`, `headroom`.
    """
    batch = processor(
        text=[prompt_text],
        images=images_arg([image], spec),
        return_tensors="pt",
    )
    seq_len = int(batch["input_ids"].shape[1])
    text_only_len = len(processor.tokenizer(prompt_text)["input_ids"])
    return {
        "seq_len": seq_len,
        "text_only_len": text_only_len,
        "image_tokens": seq_len - text_only_len,
        "max_length": spec.max_length,
        "headroom": spec.max_length - seq_len,
    }


def _main() -> None:
    """Smoke test: tải processor (không tải trọng số) và in ngân sách token ảnh."""
    from PIL import Image

    from src.utils.cccd_schema import (
        SYSTEM_PROMPT,
        CardSide,
        build_user_prompt,
        infer_side_from_filename,
    )

    parser = argparse.ArgumentParser(description="Probe ngân sách token ảnh của một VLM")
    parser.add_argument("--model", default="qwen", help=f"key hoặc model_id; key: {sorted(REGISTRY)}")
    parser.add_argument("--image", help="Đường dẫn 1 ảnh CCCD thật (bắt buộc khi probe token)")
    parser.add_argument(
        "--check_dir",
        help="Chỉ kiểm tra thư mục snapshot đã tải đủ trọng số chưa rồi thoát "
             "(không cần transformers, không cần ảnh)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    spec = resolve(args.model)

    if args.check_dir:
        ok, reason = snapshot_complete(args.check_dir)
        free = free_gb(args.check_dir)
        print(f"\n=== snapshot {args.check_dir} ===")
        print(f"đủ file       : {ok} ({reason})")
        print(f"cần khoảng    : {spec.weights_gb:.1f} GB cho {spec.model_id}")
        if free is not None:
            print(f"đĩa còn trống : {free:.1f} GB")
        if not ok:
            print("\n→ Chạy lại cell tải model (snapshot_download resume được), "
                  "hoặc dùng ensure_snapshot(spec, dir).")
        print()
        return

    if not args.image:
        parser.error("cần --image để probe token ảnh (hoặc --check_dir để kiểm tra snapshot)")
    ok, reason = check_available(spec)
    print(f"\n=== {spec.key} — {spec.model_id} ===")
    print(f"available     : {ok} ({reason})")
    print(f"family        : {spec.family}")
    print(f"vision_prefix : {spec.vision_prefixes}")
    print(f"lora_regex    : {spec.lora_target_regex}")
    if not ok:
        return

    processor = load_processor(spec.model_id, spec)
    if getattr(processor.tokenizer, "padding_side", "right") != "right":
        print(f"⚠ padding_side = {processor.tokenizer.padding_side} (train.py cần 'right')")

    image = Image.open(args.image).convert("RGB")
    original = image.size
    preprocess_image(image, spec)

    side = infer_side_from_filename(args.image)
    messages = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": build_user_prompt(side)},
            ],
        },
    ]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    stats = probe_image_tokens(processor, spec, image, text)
    print(f"\nảnh           : {original} → {image.size} (side={side.value})")
    print(f"seq_len       : {stats['seq_len']}")
    print(f"text_only_len : {stats['text_only_len']}")
    print(f"image_tokens  : {stats['image_tokens']}"
          f"{'  (kiến trúc này không nở token ảnh vào text)' if not spec.image_tokens_in_text else ''}")
    print(f"max_length    : {stats['max_length']}  → headroom {stats['headroom']}")
    if stats["headroom"] < 256:
        print("⚠ headroom < 256 token: phần JSON đáp án có nguy cơ bị truncate. "
              "Hạ max_patches / nâng max_length.")
    print()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    _main()
