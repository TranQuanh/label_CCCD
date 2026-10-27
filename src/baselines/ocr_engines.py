"""OCR engines behind one interface: `engine.read(PIL.Image) -> List[OcrLine]`."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: Tuple[float, float, float, float]
    conf: float = 1.0
    # Original 4-point polygon from the detector; needed for perspective crops.
    poly: Optional[Tuple[Tuple[float, float], ...]] = None

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2.0

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2.0

    @property
    def height(self) -> float:
        return max(self.box[3] - self.box[1], 1.0)

    @property
    def width(self) -> float:
        return max(self.box[2] - self.box[0], 1.0)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "box": [round(float(v), 2) for v in self.box],
            "conf": round(float(self.conf), 4),
            "poly": [[round(float(x), 2), round(float(y), 2)] for x, y in self.poly]
            if self.poly
            else None,
        }

    @staticmethod
    def from_dict(data: dict) -> "OcrLine":
        poly = data.get("poly")
        return OcrLine(
            text=data.get("text", ""),
            box=tuple(float(v) for v in data.get("box", (0, 0, 0, 0))),  # type: ignore[arg-type]
            conf=float(data.get("conf", 1.0)),
            poly=tuple((float(p[0]), float(p[1])) for p in poly) if poly else None,
        )


class OcrEngine:
    """Common interface; subclasses only implement `read()`."""

    name: str = "ocr"

    def read(self, image) -> List[OcrLine]:  # pragma: no cover - interface
        raise NotImplementedError

    def warmup(self, image) -> None:
        """Run one image first so the initial latency measurement excludes model loading."""
        try:
            self.read(image)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Warmup thất bại (bỏ qua): %s", exc)

    def describe(self) -> Dict[str, Any]:
        return {"engine": self.name}


def _poly_to_box(poly: Sequence[Sequence[float]]) -> Tuple[float, float, float, float]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def _coerce_geometry(
    raw: Any,
) -> Tuple[Tuple[float, float, float, float], Optional[Tuple[Tuple[float, float], ...]]]:
    """Normalize detector geometry to `(box, poly)`, detected by structure not by key name."""
    seq = list(raw)
    if len(seq) == 4 and all(not hasattr(v, "__len__") for v in seq):
        box = (float(seq[0]), float(seq[1]), float(seq[2]), float(seq[3]))
        return box, None
    poly = tuple((float(p[0]), float(p[1])) for p in seq)
    return _poly_to_box(poly), poly


def _order_quad(pts: Sequence[Sequence[float]]):
    """Order 4 corners as TL, TR, BR, BL."""
    import numpy as np

    arr = np.array(pts, dtype="float32")
    ordered = np.zeros((4, 2), dtype="float32")
    s = arr.sum(axis=1)
    d = np.diff(arr, axis=1).ravel()
    ordered[0] = arr[np.argmin(s)]
    ordered[2] = arr[np.argmax(s)]
    ordered[1] = arr[np.argmin(d)]
    ordered[3] = arr[np.argmax(d)]
    return ordered


# VietOCR resizes crops to height 32, so shorter crops decode into noise.
MIN_CROP_HEIGHT: int = 24


def crop_line(image, box, poly=None, pad_ratio: float = 0.06):
    """Crop one text line for the recognizer, de-skewing via `poly` when cv2 is available."""
    from PIL import Image as _Image

    if poly is not None:
        try:
            import cv2
            import numpy as np

            src = _order_quad(poly)
            width = int(
                max(np.linalg.norm(src[2] - src[3]), np.linalg.norm(src[1] - src[0]))
            )
            height = int(
                max(np.linalg.norm(src[1] - src[2]), np.linalg.norm(src[0] - src[3]))
            )
            if width >= 4 and height >= 4:
                dst = np.array(
                    [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
                    dtype="float32",
                )
                matrix = cv2.getPerspectiveTransform(src, dst)
                warped = cv2.warpPerspective(np.array(image), matrix, (width, height))
                crop = _Image.fromarray(warped)
                return _upscale_if_tiny(crop)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Nắn phối cảnh thất bại, lùi về crop chữ nhật: %s", exc)

    x0, y0, x1, y1 = box
    pad = max((y1 - y0) * pad_ratio, 2.0)
    left = max(int(x0 - pad), 0)
    top = max(int(y0 - pad), 0)
    right = min(int(x1 + pad), image.width)
    bottom = min(int(y1 + pad), image.height)
    if right <= left or bottom <= top:
        return _Image.new("RGB", (MIN_CROP_HEIGHT, MIN_CROP_HEIGHT), (255, 255, 255))
    return _upscale_if_tiny(image.crop((left, top, right, bottom)))


def _upscale_if_tiny(crop):
    from PIL import Image as _Image

    if crop.height >= MIN_CROP_HEIGHT or crop.height <= 0:
        return crop
    scale = MIN_CROP_HEIGHT / crop.height
    return crop.resize(
        (max(int(crop.width * scale), 1), MIN_CROP_HEIGHT), _Image.Resampling.LANCZOS
    )


def _pil_to_bgr(image):
    import numpy as np

    return np.array(image.convert("RGB"))[:, :, ::-1].copy()


def _seq(value: Any) -> List[Any]:
    """Coerce a PaddleOCR result field to a list; PP-OCR 3.x returns numpy arrays."""
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _first_seq(data: dict, *keys: str) -> List[Any]:
    for key in keys:
        items = _seq(data.get(key))
        if items:
            return items
    return []


def _as_mapping(obj: Any) -> Optional[dict]:
    """Extract the result dict from a PaddleOCR 3.x `OCRResult`, else None."""
    if isinstance(obj, dict):
        return obj
    for attr in ("json", "res"):
        value = getattr(obj, attr, None)
        if isinstance(value, dict):
            inner = value.get("res")
            return inner if isinstance(inner, dict) else value
    try:
        keys = list(obj.keys())  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        return None
    try:
        return {k: obj[k] for k in keys}  # type: ignore[index]
    except Exception:  # noqa: BLE001
        return None


def _lines_from_mapping(data: dict) -> List[OcrLine]:
    texts = _seq(data.get("rec_texts"))
    if not texts:
        return []
    scores = _seq(data.get("rec_scores"))
    geometry = _first_seq(data, "rec_polys", "dt_polys", "rec_boxes", "dt_boxes")

    lines: List[OcrLine] = []
    for idx, text in enumerate(texts):
        if idx < len(geometry):
            box, poly = _coerce_geometry(geometry[idx])
        else:
            # Keep the text but push it to the end of the reading order.
            box, poly = (0.0, float(idx), 1.0, float(idx) + 1.0), None
        conf = float(scores[idx]) if idx < len(scores) else 1.0
        lines.append(OcrLine(text=str(text).strip(), box=box, conf=conf, poly=poly))
    return lines


def _lines_from_pairs(items: Sequence[Any]) -> List[OcrLine]:
    lines: List[OcrLine] = []
    for item in items:
        if item is None:
            continue
        try:
            geometry, payload = item[0], item[1]
            text, conf = (payload[0], payload[1]) if isinstance(payload, (list, tuple)) else (payload, 1.0)
            box, poly = _coerce_geometry(geometry)
        except Exception:  # noqa: BLE001
            logger.debug("Bỏ qua phần tử PaddleOCR không đọc được: %r", item)
            continue
        lines.append(OcrLine(text=str(text).strip(), box=box, conf=float(conf), poly=poly))
    return lines


def _normalize_paddle_result(result: Any) -> List[OcrLine]:
    """Normalize any PaddleOCR 2.x/3.x output shape to `List[OcrLine]`."""
    if result is None:
        return []
    if isinstance(result, dict):
        return _lines_from_mapping(result)

    items = list(result) if isinstance(result, (list, tuple)) else [result]
    lines: List[OcrLine] = []
    for entry in items:
        if entry is None:
            continue
        mapping = _as_mapping(entry)
        if mapping is not None and "rec_texts" in mapping:
            lines += _lines_from_mapping(mapping)
        elif isinstance(entry, (list, tuple)):
            lines += _lines_from_pairs(entry)
    return lines


def _construct_with_fallback(
    factory, attempts: Sequence[Dict[str, Any]], label: str
) -> Tuple[Any, Dict[str, Any]]:
    """Build with the first accepted kwarg set; returns `(object, kwargs used)`."""
    errors: List[str] = []
    for kwargs in attempts:
        try:
            obj = factory(**kwargs)
            logger.info("%s: khởi tạo với %s", label, kwargs)
            return obj, dict(kwargs)
        except (TypeError, ValueError) as exc:
            errors.append(f"{list(kwargs)} → {type(exc).__name__}: {exc}")
    raise RuntimeError(
        f"Không khởi tạo được {label}. Đã thử:\n  " + "\n  ".join(errors)
    )


# Paddle 3.x crashes in `predictor.run()` with oneDNN on CPU; set
# PADDLE_ENABLE_MKLDNN=1 to re-enable. Disabling it only costs CPU speed.
DISABLE_MKLDNN = os.environ.get("PADDLE_ENABLE_MKLDNN", "0") != "1"


def _mkldnn_variants(attempts: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Insert an `enable_mkldnn=False` variant before each kwarg set, keeping their order."""
    if not DISABLE_MKLDNN:
        return [dict(kwargs) for kwargs in attempts]
    out: List[Dict[str, Any]] = []
    for kwargs in attempts:
        out.append({**kwargs, "enable_mkldnn": False})
        out.append(dict(kwargs))
    return out


def resolve_paddle_device(use_gpu: bool, device: Optional[str] = None) -> str:
    """Map `use_gpu`/`device` to a Paddle device string, accepting torch's `cuda:0`."""
    if device:
        normalized = device.strip().lower()
        if normalized.startswith("cuda"):
            return normalized.replace("cuda", "gpu", 1)
        return normalized
    return "gpu" if use_gpu else "cpu"


def _warn_if_gpu_dropped(won: Dict[str, Any], device: str, label: str) -> str:
    """Return the device actually in use; the winning kwargs may carry no device at all."""
    if device.startswith("cpu"):
        return "cpu"
    if "device" in won or won.get("use_gpu"):
        logger.info("%s: detection chạy trên %s", label, device)
        return device
    logger.warning(
        "⚠ %s: đã xin device=%s nhưng bản paddleocr này không nhận kwarg nào mang "
        "device (bộ dùng được: %s) ⇒ detection đang chạy CPU. Cài paddlepaddle-gpu "
        "khớp CUDA nếu muốn GPU.",
        label, device, list(won),
    )
    return "cpu"


class PaddleOCREngine(OcrEngine):
    """Full PP-OCR pipeline; `lang='vi'` maps to the shared `latin` models."""

    def __init__(
        self,
        lang: str = "vi",
        use_gpu: bool = False,
        det_limit_side_len: int = 1024,
        min_conf: float = 0.0,
        device: Optional[str] = None,
    ) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:  # pragma: no cover - external dependency
            raise RuntimeError(
                "Chưa cài paddleocr. Cài: pip install paddlepaddle paddleocr"
            ) from exc

        self.lang = lang
        self.min_conf = min_conf
        self.det_limit_side_len = det_limit_side_len
        self.name = f"PaddleOCR (det+rec, lang={lang})"

        # Passed explicitly: the default 960 would shrink the 1024px input again.
        wanted = resolve_paddle_device(use_gpu, device)
        base_new = {"lang": lang, "text_det_limit_side_len": det_limit_side_len}
        base_old = {"lang": lang, "det_limit_side_len": det_limit_side_len, "use_gpu": use_gpu}
        # The 3.x set WITH device must come first or the GPU choice is silently dropped.
        new_dev = {**base_new, "device": wanted}
        self._ocr, won = _construct_with_fallback(
            lambda **kw: __import__("paddleocr", fromlist=["PaddleOCR"]).PaddleOCR(**kw),
            _mkldnn_variants([
                {**new_dev, "use_textline_orientation": True},
                new_dev,
                {**base_new, "use_textline_orientation": True},
                base_new,
                {**base_old, "use_angle_cls": True, "show_log": False},
                {**base_old, "use_angle_cls": True},
                {"lang": lang, "use_angle_cls": True},
                {"lang": lang},
            ]),
            label=self.name,
        )
        self.device = _warn_if_gpu_dropped(won, wanted, self.name)

    def read(self, image) -> List[OcrLine]:
        array = _pil_to_bgr(image)
        result = None
        if hasattr(self._ocr, "predict"):
            try:
                result = self._ocr.predict(array)
            except Exception as exc:  # noqa: BLE001
                logger.debug("predict() không dùng được, lùi về ocr(): %s", exc)
        if result is None:
            try:
                result = self._ocr.ocr(array, cls=True)
            except TypeError:
                # 3.x dropped the `cls` kwarg.
                result = self._ocr.ocr(array)

        lines = _normalize_paddle_result(result)
        return [ln for ln in lines if ln.text and ln.conf >= self.min_conf]

    def describe(self) -> Dict[str, Any]:
        return {
            "engine": self.name,
            "detector": "PP-OCR DB",
            "recognizer": f"PP-OCR CRNN (lang={self.lang})",
            "det_limit_side_len": self.det_limit_side_len,
            "device": self.device,
            "min_conf": self.min_conf,
        }


class PaddleTextDetector:
    """PP-OCR detection only, returning line polygons."""

    def __init__(
        self,
        lang: str = "vi",
        use_gpu: bool = False,
        det_limit_side_len: int = 1024,
        device: Optional[str] = None,
    ) -> None:
        self.det_limit_side_len = det_limit_side_len
        self._mode = "unknown"
        self._impl: Any = None
        wanted = resolve_paddle_device(use_gpu, device)
        self.device = "cpu"

        try:
            from paddleocr import TextDetection  # type: ignore[attr-defined]

            self._impl, won = _construct_with_fallback(
                TextDetection,
                _mkldnn_variants([
                    {"limit_side_len": det_limit_side_len, "device": wanted},
                    {"limit_side_len": det_limit_side_len},
                    {"device": wanted},
                    {},
                ]),
                label="PP-OCR TextDetection",
            )
            self._mode = "text_detection"
            self.device = _warn_if_gpu_dropped(won, wanted, "PP-OCR TextDetection")
            return
        except (ImportError, RuntimeError) as exc:
            logger.debug("Không dùng được TextDetection riêng: %s", exc)

        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:  # pragma: no cover - external dependency
            raise RuntimeError(
                "Chưa cài paddleocr. Cài: pip install paddlepaddle paddleocr"
            ) from exc

        self._impl, won = _construct_with_fallback(
            PaddleOCR,
            _mkldnn_variants([
                {"lang": lang, "text_det_limit_side_len": det_limit_side_len, "device": wanted},
                {"lang": lang, "text_det_limit_side_len": det_limit_side_len},
                {"lang": lang, "det_limit_side_len": det_limit_side_len, "use_gpu": use_gpu, "show_log": False},
                {"lang": lang, "det_limit_side_len": det_limit_side_len},
                {"lang": lang},
            ]),
            label="PP-OCR (detection qua PaddleOCR)",
        )
        self._mode = "paddleocr"
        self.device = _warn_if_gpu_dropped(won, wanted, "PP-OCR (detection qua PaddleOCR)")

    def detect(self, image) -> List[Tuple[Tuple[float, float, float, float], Optional[Tuple[Tuple[float, float], ...]]]]:
        array = _pil_to_bgr(image)

        if self._mode == "text_detection":
            result = self._impl.predict(array)
            out = []
            for entry in result if isinstance(result, (list, tuple)) else [result]:
                mapping = _as_mapping(entry) or {}
                for geometry in _first_seq(mapping, "dt_polys", "dt_boxes"):
                    out.append(_coerce_geometry(geometry))
            return out

        # 2.x path: ask for detection only.
        try:
            result = self._impl.ocr(array, det=True, rec=False)
            out = []
            for entry in result if isinstance(result, (list, tuple)) else [result]:
                if entry is None:
                    continue
                for geometry in entry:
                    out.append(_coerce_geometry(geometry))
            if out:
                return out
        except (TypeError, ValueError) as exc:
            logger.debug("ocr(det=True, rec=False) không dùng được: %s", exc)

        # Last resort: run full OCR and keep only the geometry.
        lines = _normalize_paddle_result(
            self._impl.predict(array) if hasattr(self._impl, "predict") else self._impl.ocr(array)
        )
        return [(ln.box, ln.poly) for ln in lines]


VIETOCR_CACHE_ENV = "VIETOCR_CACHE_DIR"

# Fallback when vietocr's `url_config` cannot be imported.
_VIETOCR_YAML_FALLBACK = {
    "vgg_transformer": "vgg-transformer.yml",
    "vgg_seq2seq": "vgg-seq2seq.yml",
}


def _vietocr_yaml_name(config_name: str) -> str:
    try:
        from vietocr.tool.config import url_config  # type: ignore[attr-defined]

        return url_config[config_name]
    except (ImportError, KeyError):
        return _VIETOCR_YAML_FALLBACK.get(config_name, f"{config_name}.yml")


def load_vietocr_config(config_name: str, cache_dir: Optional[str] = None) -> Any:
    """Load a VietOCR config, preferring the local cache: vocr.vn's TLS certificate has expired."""
    from vietocr.tool.config import Cfg

    cache_dir = cache_dir or os.environ.get(VIETOCR_CACHE_ENV) or ""
    if cache_dir:
        import yaml

        root = Path(cache_dir)
        base_path = root / "base.yml"
        name_path = root / _vietocr_yaml_name(config_name)
        if base_path.exists() and name_path.exists():
            merged = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
            merged.update(yaml.safe_load(name_path.read_text(encoding="utf-8")) or {})
            logger.info("VietOCR config đọc từ cache local: %s", root)
            return Cfg(merged)
        logger.warning(
            "%s=%s nhưng thiếu %s hoặc %s ⇒ sẽ thử tải từ vocr.vn (có thể lỗi SSL).",
            VIETOCR_CACHE_ENV, cache_dir, base_path.name, name_path.name,
        )

    try:
        return Cfg.load_config_from_name(config_name)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Không tải được config VietOCR '{config_name}' từ vocr.vn: {exc}\n"
            f"Chứng chỉ TLS của vocr.vn đã hết hạn (lỗi phía server). Tải sẵn "
            f"base.yml + {_vietocr_yaml_name(config_name)} + {config_name}.pth vào "
            f"một thư mục rồi đặt {VIETOCR_CACHE_ENV} trỏ vào đó. "
            f"Xem docs/OCR_BASELINE.md."
        ) from exc


def resolve_vietocr_weights(
    config_name: str, explicit: Optional[str] = None, cache_dir: Optional[str] = None
) -> Optional[str]:
    """Pick the weights file: explicit arg, env var, cache, else None (downloads from vocr.vn)."""
    if explicit:
        return explicit
    env = os.environ.get("VIETOCR_WEIGHTS")
    if env:
        return env
    cache_dir = cache_dir or os.environ.get(VIETOCR_CACHE_ENV) or ""
    if cache_dir:
        candidate = Path(cache_dir) / f"{config_name}.pth"
        if candidate.exists():
            logger.info("VietOCR trọng số đọc từ cache local: %s", candidate)
            return str(candidate)
        logger.warning(
            "Không thấy %s ⇒ vietocr sẽ tải trọng số từ vocr.vn và nhiều khả năng "
            "chết vì chứng chỉ hết hạn.", candidate,
        )
    return None


class PaddleVietOCREngine(OcrEngine):
    """PP-OCR detection + VietOCR recognition; VietOCR has no detector of its own."""

    def __init__(
        self,
        lang: str = "vi",
        use_gpu: bool = False,
        det_limit_side_len: int = 1024,
        min_conf: float = 0.0,
        vietocr_config: str = "vgg_transformer",
        vietocr_weights: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: int = 16,
    ) -> None:
        self.min_conf = min_conf
        self.det_limit_side_len = det_limit_side_len
        self.vietocr_config = vietocr_config
        self.batch_size = batch_size
        self.name = f"PP-OCR det + VietOCR {vietocr_config}"

        self._detector = PaddleTextDetector(
            lang=lang, use_gpu=use_gpu, det_limit_side_len=det_limit_side_len
        )

        try:
            from vietocr.tool.predictor import Predictor
        except ImportError as exc:  # pragma: no cover - external dependency
            raise RuntimeError("Chưa cài vietocr. Cài: pip install vietocr") from exc

        config = load_vietocr_config(vietocr_config)
        weights = resolve_vietocr_weights(vietocr_config, vietocr_weights)
        if weights:
            config["weights"] = weights
        if device is None:
            try:
                import torch

                device = "cuda:0" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        config["device"] = device
        config["predictor"]["beamsearch"] = False  # greedy, matching build_gen_kwargs
        self.device = device
        self._recognizer = Predictor(config)

    def read(self, image) -> List[OcrLine]:
        image = image.convert("RGB")
        detections = self._detector.detect(image)
        if not detections:
            return []

        crops = [crop_line(image, box, poly) for box, poly in detections]
        texts, confs = self._recognize(crops)

        lines: List[OcrLine] = []
        for (box, poly), text, conf in zip(detections, texts, confs):
            text = (text or "").strip()
            if text and conf >= self.min_conf:
                lines.append(OcrLine(text=text, box=box, conf=conf, poly=poly))
        return lines

    def _recognize(self, crops: List[Any]) -> Tuple[List[str], List[float]]:
        # `predict_batch` is much faster on GPU but returns no probabilities.
        if hasattr(self._recognizer, "predict_batch") and self.batch_size > 1:
            texts: List[str] = []
            try:
                for start in range(0, len(crops), self.batch_size):
                    chunk = crops[start : start + self.batch_size]
                    texts += list(self._recognizer.predict_batch(chunk))
                return texts, [1.0] * len(texts)
            except Exception as exc:  # noqa: BLE001
                logger.warning("predict_batch lỗi (%s) → đọc từng ảnh một", exc)

        texts, confs = [], []
        for crop in crops:
            try:
                result = self._recognizer.predict(crop, return_prob=True)
                if isinstance(result, (list, tuple)) and len(result) == 2:
                    texts.append(str(result[0]))
                    confs.append(float(result[1]))
                else:
                    texts.append(str(result))
                    confs.append(1.0)
            except Exception as exc:  # noqa: BLE001
                logger.debug("VietOCR đọc lỗi 1 crop: %s", exc)
                texts.append("")
                confs.append(0.0)
        return texts, confs

    def describe(self) -> Dict[str, Any]:
        return {
            "engine": self.name,
            "detector": "PP-OCR DB",
            "recognizer": f"VietOCR {self.vietocr_config}",
            "det_limit_side_len": self.det_limit_side_len,
            # Two runtimes, two devices: VietOCR on torch, detection on Paddle.
            "device": self.device,
            "det_device": self._detector.device,
            "min_conf": self.min_conf,
        }


def group_rows(lines: Sequence[OcrLine], y_tol_ratio: float = 0.6) -> List[List[OcrLine]]:
    """Group boxes on the same horizontal row and sort them in reading order."""
    if not lines:
        return []

    # Tolerance scales with line height so it is resolution independent.
    heights = sorted(ln.height for ln in lines)
    median_h = heights[len(heights) // 2]
    tol = max(median_h * y_tol_ratio, 1.0)

    rows: List[List[OcrLine]] = []
    for line in sorted(lines, key=lambda ln: (ln.cy, ln.box[0])):
        placed = False
        for row in rows:
            row_cy = sum(item.cy for item in row) / len(row)
            if abs(line.cy - row_cy) <= tol:
                row.append(line)
                placed = True
                break
        if not placed:
            rows.append([line])

    for row in rows:
        row.sort(key=lambda ln: ln.box[0])
    rows.sort(key=lambda row: min(item.box[1] for item in row))
    return rows


def row_text(row: Sequence[OcrLine]) -> str:
    return re.sub(r"\s+", " ", " ".join(item.text for item in row)).strip()
