"""Configuration registry for the OCR baselines, mirroring `models.vlm_registry`."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from importlib import util as importlib_util
from typing import Any, Dict, List, Optional, Tuple

from src.models.vlm_registry import SHARED_IMAGE_MAX_SIDE, preprocess_image

logger = logging.getLogger(__name__)

# PP-OCR cannot disable its size limit, so "no downscale" needs a large number.
DET_LIMIT_UNBOUNDED: int = 4096


@dataclass(frozen=True)
class OCRSpec:
    key: str
    name: str
    detector: str
    recognizer: str
    lang: str = "vi"
    vietocr_config: str = "vgg_transformer"
    requires: Tuple[str, ...] = ()
    pip_hint: str = ""
    family: str = "ocr"
    # 0.0 means "not published"; latency and VRAM are the comparable columns here.
    params_b: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""


REGISTRY: Dict[str, OCRSpec] = {
    "paddleocr": OCRSpec(
        key="paddleocr",
        name="PaddleOCR PP-OCR (det+rec, lang=vi)",
        detector="ppocr_db",
        recognizer="ppocr_crnn",
        lang="vi",
        requires=("paddleocr",),
        pip_hint="pip install paddlepaddle paddleocr",
        params_b=0.0,
        notes=(
            "Mốc 'OCR đa ngữ generic'. lang='vi' của PaddleOCR ánh xạ sang nhóm model "
            "`latin` dùng chung cho hàng chục ngôn ngữ hệ Latinh, KHÔNG phải model "
            "riêng cho tiếng Việt — bộ từ điển vì thế phủ dấu tiếng Việt không đầy đủ. "
            "Đây là điểm yếu có chủ đích: chênh lệch của nó với pipeline VietOCR đo "
            "trực tiếp phần đóng góp của recognizer chuyên tiếng Việt."
        ),
    ),
    "paddle_vietocr": OCRSpec(
        key="paddle_vietocr",
        name="PP-OCR det + VietOCR rec (vgg_transformer)",
        detector="ppocr_db",
        recognizer="vietocr",
        lang="vi",
        vietocr_config="vgg_transformer",
        requires=("paddleocr", "vietocr"),
        pip_hint="pip install paddlepaddle paddleocr vietocr",
        params_b=0.0,
        notes=(
            "Tổ hợp chuẩn cho tiếng Việt. VietOCR KHÔNG có detector riêng (nó nhận "
            "dạng mức DÒNG: ảnh một dòng chữ đã crop → chuỗi), nên buộc phải mượn "
            "detection của PP-OCR. Dùng CHUNG detector với `paddleocr` là có chủ đích: "
            "giữ nguyên khâu tìm dòng thì chênh lệch giữa 2 baseline quy hết về khâu "
            "nhận dạng."
        ),
    ),
}


def resolve(name: str) -> OCRSpec:
    """Look up an `OCRSpec` by key or by any string containing the pipeline name."""
    if name in REGISTRY:
        return REGISTRY[name]

    lowered = name.lower().replace("\\", "/").replace("-", "_")
    if lowered in REGISTRY:
        return REGISTRY[lowered]
    if "vietocr" in lowered:
        return REGISTRY["paddle_vietocr"]
    if "paddle" in lowered or "ppocr" in lowered:
        return REGISTRY["paddleocr"]

    raise KeyError(
        f"Không suy được pipeline baseline từ '{name}'. Chọn một trong: {sorted(REGISTRY)}."
    )


def check_available(spec: OCRSpec) -> Tuple[bool, str]:
    """Return `(True, "ok")` or `(False, reason)` without loading any weights."""
    missing = [module for module in spec.requires if importlib_util.find_spec(module) is None]
    if missing:
        hint = f" Cài: {spec.pip_hint}" if spec.pip_hint else ""
        return False, f"thiếu module {', '.join(missing)}.{hint}"
    return True, "ok"


def preprocess_for_ocr(image, image_max_side: int = SHARED_IMAGE_MAX_SIDE):
    """Preprocess like the VLM branch; `image_max_side=0` keeps the original size (ablation)."""
    if image_max_side <= 0:
        return image
    if image_max_side == SHARED_IMAGE_MAX_SIDE:
        return preprocess_image(image)

    from PIL import Image as _Image

    image.thumbnail((image_max_side, image_max_side), _Image.Resampling.LANCZOS)
    return image


def build_engine(
    spec: OCRSpec,
    use_gpu: bool = False,
    device: Optional[str] = None,
    min_conf: float = 0.0,
    det_limit_side_len: Optional[int] = None,
    vietocr_weights: Optional[str] = None,
    batch_size: int = 16,
):
    """Build the OCR engine; `det_limit_side_len=None` follows `SHARED_IMAGE_MAX_SIDE`."""
    from src.baselines.ocr_engines import PaddleOCREngine, PaddleVietOCREngine

    ok, reason = check_available(spec)
    if not ok:
        raise RuntimeError(f"Không chạy được baseline '{spec.key}': {reason}")

    # `or` would swallow 0, silently disabling the full-res ablation flag.
    if det_limit_side_len is None:
        limit = SHARED_IMAGE_MAX_SIDE
    elif det_limit_side_len <= 0:
        limit = DET_LIMIT_UNBOUNDED
    else:
        limit = det_limit_side_len
    logger.info(
        "🔧 det_limit_side_len = %d%s",
        limit,
        " (ablation: không thu nhỏ khi detect)" if limit == DET_LIMIT_UNBOUNDED else "",
    )

    if spec.recognizer == "vietocr":
        return PaddleVietOCREngine(
            lang=spec.lang,
            use_gpu=use_gpu,
            det_limit_side_len=limit,
            min_conf=min_conf,
            vietocr_config=spec.vietocr_config,
            vietocr_weights=vietocr_weights,
            device=device,
            batch_size=batch_size,
        )
    return PaddleOCREngine(
        lang=spec.lang, use_gpu=use_gpu, det_limit_side_len=limit, min_conf=min_conf,
        device=device,
    )


def _load_gold(gold_path: str, image_name: str) -> Optional[dict]:
    """Find the ground truth of one image in a JSONL file, matched by file name."""
    from pathlib import Path

    from src.utils.metrics import safe_parse

    target = Path(image_name).name
    with open(gold_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if Path(str(record.get("image", ""))).name == target:
                return safe_parse(record["conversations"][1]["value"])
    return None


def resolve_side(side_arg: Optional[str], image_path: str):
    from src.utils.cccd_schema import CardSide, infer_side_from_filename

    if side_arg:
        return CardSide(side_arg)
    return infer_side_from_filename(image_path)


def _main() -> None:
    """Probe: run one image and print the OCR lines plus the parsed JSON."""
    from PIL import Image

    from src.baselines.field_parser import parse_ocr_lines
    from src.utils.console import force_utf8_output
    from src.utils.metrics import normalize_text

    force_utf8_output()

    parser = argparse.ArgumentParser(description="Probe baseline OCR trên một ảnh CCCD")
    parser.add_argument("--engine", default="paddleocr", help=f"key: {sorted(REGISTRY)}")
    parser.add_argument("--image", required=True)
    parser.add_argument("--side", default=None, choices=["truoc", "sau"],
                        help="Ép mặt thẻ; bỏ trống = suy từ tên file")
    parser.add_argument("--image_max_side", type=int, default=SHARED_IMAGE_MAX_SIDE,
                        help="0 = giữ ảnh gốc (ablation)")
    parser.add_argument("--min_conf", type=float, default=0.0)
    parser.add_argument("--canonicalize", action="store_true",
                        help="Bật luật chuẩn hoá noi_cap/quoc_tich (ablation, mặc định tắt)")
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--gold", default=None,
                        help="JSONL nhãn chuẩn — có thì in luôn so sánh từng trường")
    parser.add_argument("--show_rows", action="store_true", help="In chi tiết từng hàng đã gom")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    spec = resolve(args.engine)
    ok, reason = check_available(spec)
    print(f"\n=== {spec.key} — {spec.name} ===")
    print(f"available   : {ok} ({reason})")
    print(f"detector    : {spec.detector}")
    print(f"recognizer  : {spec.recognizer}")
    if not ok:
        return

    side = resolve_side(args.side, args.image)
    image = Image.open(args.image).convert("RGB")
    original = image.size
    preprocess_for_ocr(image, args.image_max_side)

    # Detection limit follows the preprocessed size so the probe matches eval_baseline.py.
    engine = build_engine(
        spec, use_gpu=args.gpu, min_conf=args.min_conf,
        det_limit_side_len=args.image_max_side,
    )
    lines = engine.read(image)
    parsed, debug = parse_ocr_lines(lines, side, canonicalize=args.canonicalize, return_debug=True)

    print(f"\nảnh         : {original} → {image.size} (side={side.value})")
    print(f"dòng OCR    : {len(lines)}  → gom thành {debug['n_rows']} hàng\n")

    print("--- dòng OCR đọc được ---")
    for line in sorted(lines, key=lambda item: (item.cy, item.box[0])):
        print(f"  [{line.conf:.2f}] {line.text}")

    if args.show_rows:
        print("\n--- hàng → trường ---")
        for row in debug["rows"]:
            tag = row.get("field") or row.get("cont") or row.get("skip") or "?"
            print(f"  ({tag:>22}) {row['text'][:90]}")

    print("\n--- JSON parser trích được ---")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))

    if args.gold:
        gold = _load_gold(args.gold, args.image)
        if gold is None:
            print(f"\n⚠ Không tìm thấy nhãn chuẩn của {args.image} trong {args.gold}")
            return
        print("\n--- so với nhãn chuẩn (chuẩn hoá như metrics.evaluate) ---")
        n_ok = 0
        for name, gold_value in gold.items():
            predicted = normalize_text(parsed.get(name))
            expected = normalize_text(gold_value)
            hit = predicted == expected
            n_ok += hit
            print(f"  {'✓' if hit else '✗'} {name}")
            if not hit:
                print(f"      gold: {expected!r}")
                print(f"      pred: {predicted!r}")
        print(f"\n  Field Accuracy ảnh này: {n_ok}/{len(gold)} = {n_ok / max(len(gold), 1):.2%}")
    print()


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    _main()
