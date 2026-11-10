"""
image_quality.py
================
Kiểm tra chất lượng ảnh CCCD + phát hiện khung thẻ bằng OpenCV — CHỈ để cảnh
báo (lệch / nhỏ / chụp xiên / mất góc / sáng / tối / chói / nhòe / nhiễu).
KHÔNG crop, KHÔNG nắn thẳng: ảnh gốc vẫn gửi nguyên cho /extract-cccd như cũ.

Thiếu opencv-python-headless / numpy → AVAILABLE = False, import module này
vẫn không lỗi (backend khởi động bình thường, endpoint trả available=false).
Cài: pip install -r backend/requirements-quality.txt

Mã cảnh báo (code) trùng với app Flutter (lib/core/image_quality/) để màn xem
lại gộp trùng — kết quả server ghi đè kết quả app khi cùng code.
Không ghi ảnh ra đĩa, không log dữ liệu ảnh.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:  # Thư viện tuỳ chọn — thiếu thì tắt tính năng, không làm sập backend.
    import cv2
    import numpy as np

    AVAILABLE = True
except Exception:  # ImportError, hoặc lỗi nạp DLL của OpenCV trên Windows
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    AVAILABLE = False

# ── Ngưỡng mặc định (gom một chỗ để chỉnh sau) ─────────────────────────────
# Các chỉ số sáng/tối/chói/nhòe/nhiễu tính trên ảnh xám thu nhỏ cạnh dài về
# ANALYSIS_LONG_SIDE (512px, INTER_AREA) — CÙNG cỡ ảnh với app nên dùng CÙNG
# ngưỡng (phương sai Laplacian phụ thuộc mạnh vào độ phân giải: tính ở 1000px
# sẽ thấp hơn nhiều so với 512px, phải hạ ngưỡng nếu đổi cỡ).
# Phát hiện khung thẻ tính trên ảnh thu nhỏ cạnh dài về CARD_LONG_SIDE (1000px).
ANALYSIS_LONG_SIDE = 512
CARD_LONG_SIDE = 1000

DARK_WARNING = 60.0           # độ sáng TB (0–255) < → tối (warning)
DARK_SEVERE = 35.0            # < → tối (severe)
BRIGHT_WARNING = 210.0        # > → quá sáng (warning)
DARK_PIXEL = 20               # pixel < → pixel tối
DARK_RATIO_WARNING = 0.50     # tỉ lệ pixel tối > → tối (warning)
GLARE_PIXEL = 245             # pixel > → pixel chói
GLARE_RATIO_WARNING = 0.08    # tỉ lệ pixel chói > → chói (warning)
GLARE_RATIO_SEVERE = 0.20     # > → chói (severe)
BLUR_WARNING = 80.0           # phương sai Laplacian (512px) < → nhòe (warning)
BLUR_SEVERE = 35.0            # < → nhòe (severe)
RESOLUTION_WARNING = 600      # cạnh ngắn ảnh gốc (px) < → độ phân giải thấp
RESOLUTION_SEVERE = 400
NOISE_WARNING = 6.0           # trung vị |ảnh − blur 3x3| > → nhiễu (chỉ warning)

CARD_MIN_AREA_RATIO = 0.04    # contour < 4% ảnh → không coi là thẻ (nới cho emulator)
CARD_SOLIDITY_MIN = 0.75      # dự phòng minAreaRect khi không ra 4 đỉnh (nới cho thẻ ảo)
CARD_SMALL_RATIO = 0.15       # thẻ chiếm < 15% ảnh → quá nhỏ (nới cho emulator)
TILT_WARNING_DEG = 7.0
TILT_SEVERE_DEG = 15.0
CARD_ASPECT = 85.6 / 53.98    # ≈ 1.586 (CCCD chuẩn ISO ID-1)
ASPECT_TOLERANCE = 0.15       # lệch tỉ lệ cạnh > 15% → chụp xiên
EDGE_MARGIN_RATIO = 0.02      # đỉnh cách mép ≤ 2% kích thước → có thể mất góc


def _issue(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def _empty(available: bool) -> dict:
    return {"available": available, "card_found": None, "issues": [], "metrics": {}}


def _resize_long_side(img: Any, target: int) -> Any:
    h, w = img.shape[:2]
    long_side = max(h, w)
    if long_side <= target:
        return img
    scale = target / float(long_side)
    size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)


def _photo_issues(gray_small: Any, orig_short: int, metrics: dict) -> list:
    """Sáng / tối / chói / nhòe / nhiễu / độ phân giải — cùng code với app."""
    issues: list = []
    mean = float(gray_small.mean())
    glare_ratio = float((gray_small > GLARE_PIXEL).mean())
    dark_ratio = float((gray_small < DARK_PIXEL).mean())

    lap_var: Optional[float] = None
    noise: Optional[float] = None
    if gray_small.shape[0] >= 3 and gray_small.shape[1] >= 3:
        g = gray_small.astype(np.float64)
        # Kernel 4 lân cận (ksize=1) — giống app; bỏ viền 1px như app.
        lap = cv2.Laplacian(g, cv2.CV_64F, ksize=1)[1:-1, 1:-1]
        lap_var = float(lap.var())
        box = cv2.blur(g, (3, 3))
        noise = float(np.median(np.abs(g - box)[1:-1, 1:-1]))

    metrics.update({
        "mean_brightness": round(mean, 1),
        "glare_ratio": round(glare_ratio, 4),
        "dark_ratio": round(dark_ratio, 4),
        "laplacian_var": None if lap_var is None else round(lap_var, 1),
        "noise": None if noise is None else round(noise, 2),
        "orig_short_side": orig_short,
    })

    if orig_short < RESOLUTION_SEVERE:
        issues.append(_issue("low_resolution", "severe",
                             "Ảnh có độ phân giải quá thấp — đưa máy lại gần thẻ hoặc chụp bằng camera sau"))
    elif orig_short < RESOLUTION_WARNING:
        issues.append(_issue("low_resolution", "warning",
                             "Ảnh có độ phân giải thấp — đưa máy lại gần thẻ hoặc chụp bằng camera sau"))

    if mean < DARK_SEVERE:
        issues.append(_issue("too_dark", "severe",
                             "Ảnh quá tối — hãy chụp nơi đủ sáng hoặc bật đèn flash"))
    elif mean < DARK_WARNING or dark_ratio > DARK_RATIO_WARNING:
        issues.append(_issue("too_dark", "warning",
                             "Ảnh hơi tối — hãy chụp nơi đủ sáng hoặc bật đèn flash"))
    elif mean > BRIGHT_WARNING:
        issues.append(_issue("too_bright", "warning",
                             "Ảnh quá sáng — tránh nguồn sáng chiếu thẳng hoặc tắt đèn flash"))

    if glare_ratio > GLARE_RATIO_SEVERE:
        issues.append(_issue("glare", "severe",
                             "Ảnh bị chói / lóa sáng — nghiêng thẻ để tránh đèn phản chiếu"))
    elif glare_ratio > GLARE_RATIO_WARNING:
        issues.append(_issue("glare", "warning",
                             "Ảnh có vùng lóa sáng — nghiêng thẻ để tránh đèn phản chiếu"))

    if lap_var is not None:
        if lap_var < BLUR_SEVERE:
            issues.append(_issue("blurry", "severe",
                                 "Ảnh bị nhòe — giữ yên máy và chạm để lấy nét"))
        elif lap_var < BLUR_WARNING:
            issues.append(_issue("blurry", "warning",
                                 "Ảnh hơi nhòe — giữ yên máy và chạm để lấy nét"))

    if noise is not None and noise > NOISE_WARNING:
        issues.append(_issue("noisy", "warning",
                             "Ảnh bị nhiễu (lấm tấm hạt) — chụp nơi đủ sáng hơn"))
    return issues


def _find_card_quad(gray: Any) -> Optional[Any]:
    """Tìm 4 đỉnh khung thẻ (float32 (4,2)) hoặc None."""
    h, w = gray.shape[:2]
    img_area = float(h * w)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    # OpenCV 3.x trả 3 giá trị, 4.x trả 2 → lấy phần tử [-2].
    contours = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(c))
    if area < CARD_MIN_AREA_RATIO * img_area:
        return None

    peri = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.02 * peri, True)
    if len(approx) == 4 and cv2.isContourConvex(approx):
        return approx.reshape(4, 2).astype(np.float32)

    # Không ra đúng 4 đỉnh (góc bo tròn, nhiễu) → hình chữ nhật bao nhỏ nhất,
    # chỉ chấp nhận khi contour "đặc" (gần lồi).
    hull_area = float(cv2.contourArea(cv2.convexHull(c)))
    solidity = area / hull_area if hull_area > 0 else 0.0
    if solidity >= CARD_SOLIDITY_MIN:
        return cv2.boxPoints(cv2.minAreaRect(c)).astype(np.float32)
    return None


def _card_issues(gray: Any, metrics: dict) -> tuple[bool, list]:
    """Phát hiện khung thẻ → (card_found, issues)."""
    h, w = gray.shape[:2]
    quad = _find_card_quad(gray)
    if quad is None:
        metrics["card_found"] = False
        return False, [_issue("card_not_found", "info",
                              "Không nhận ra khung thẻ — đặt thẻ trên nền tương phản, vừa khung hình")]

    issues: list = []
    area_ratio = float(cv2.contourArea(quad)) / float(h * w)

    # Góc nghiêng từ minAreaRect, chuẩn hoá về [-45, 45] (khác nhau giữa các
    # phiên bản OpenCV: [-90,0) hoặc (0,90]).
    angle = float(cv2.minAreaRect(quad)[2])
    while angle > 45.0:
        angle -= 90.0
    while angle < -45.0:
        angle += 90.0
    tilt = abs(angle)

    # Tỉ lệ cạnh: trung bình 2 cặp cạnh đối (đỉnh liên tiếp theo contour).
    sides = [float(np.linalg.norm(quad[i] - quad[(i + 1) % 4])) for i in range(4)]
    pair_a = (sides[0] + sides[2]) / 2.0
    pair_b = (sides[1] + sides[3]) / 2.0
    aspect = max(pair_a, pair_b) / min(pair_a, pair_b) if min(pair_a, pair_b) > 0 else None
    aspect_dev = abs(aspect - CARD_ASPECT) / CARD_ASPECT if aspect is not None else None

    mx, my = EDGE_MARGIN_RATIO * w, EDGE_MARGIN_RATIO * h
    touches_edge = bool(
        (quad[:, 0] <= mx).any() or (quad[:, 0] >= w - 1 - mx).any()
        or (quad[:, 1] <= my).any() or (quad[:, 1] >= h - 1 - my).any()
    )

    metrics.update({
        "card_found": True,
        "card_area_ratio": round(area_ratio, 4),
        "card_tilt_deg": round(tilt, 1),
        "card_aspect": None if aspect is None else round(aspect, 3),
        "card_touches_edge": touches_edge,
    })

    if area_ratio < CARD_SMALL_RATIO:
        issues.append(_issue("card_too_small", "warning",
                             "Thẻ quá nhỏ trong ảnh — đưa thẻ lại gần hơn"))
    if tilt > TILT_SEVERE_DEG:
        issues.append(_issue("card_tilted", "severe",
                             "Thẻ bị nghiêng nhiều — xoay máy cho cạnh thẻ song song với khung"))
    elif tilt > TILT_WARNING_DEG:
        issues.append(_issue("card_tilted", "warning",
                             "Thẻ bị nghiêng — xoay máy cho cạnh thẻ song song với khung"))
    if aspect_dev is not None and aspect_dev > ASPECT_TOLERANCE:
        issues.append(_issue("card_perspective", "warning",
                             "Thẻ bị chụp xiên — giữ máy song song với thẻ"))
    if touches_edge:
        issues.append(_issue("card_cut_off", "warning",
                             "Thẻ có thể bị cắt mất góc — lùi máy ra để thấy đủ 4 góc thẻ"))
    return True, issues


def analyze(image_bytes: bytes) -> dict:
    """
    Phân tích ảnh → {'available', 'card_found', 'issues': [{code, severity,
    message}], 'metrics': {...}} (metrics chỉ là số đo, không chứa PII).
    Mọi lỗi → kết quả rỗng (không ném).
    """
    if not AVAILABLE:
        return _empty(False)
    try:
        if not image_bytes:
            raise ValueError("empty")
        buf = np.frombuffer(image_bytes, dtype=np.uint8)
        # IMREAD_COLOR tự xoay theo EXIF (OpenCV ≥ 3.1) — giống bakeOrientation của app.
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        img = None
    if img is None:
        result = _empty(True)
        result["issues"] = [_issue("decode_failed", "warning",
                                   "Không đọc được ảnh để kiểm tra chất lượng")]
        return result

    try:
        h, w = img.shape[:2]
        metrics: dict = {"width": int(w), "height": int(h)}
        gray_card = cv2.cvtColor(_resize_long_side(img, CARD_LONG_SIDE), cv2.COLOR_BGR2GRAY)
        gray_small = _resize_long_side(gray_card, ANALYSIS_LONG_SIDE)

        issues = _photo_issues(gray_small, int(min(h, w)), metrics)
        card_found, card_issues = _card_issues(gray_card, metrics)
        issues.extend(card_issues)
        return {"available": True, "card_found": card_found, "issues": issues, "metrics": metrics}
    except Exception as exc:
        # Chỉ log loại lỗi — KHÔNG log dữ liệu ảnh.
        logger.warning("⚠️ Lỗi phân tích chất lượng ảnh: %s", type(exc).__name__)
        return _empty(True)


