"""
cccd_schema.py
==============
Nguồn chân lý (single source of truth) cho toàn bộ pipeline CCCD:
  - Danh sách trường thông tin cho MẶT TRƯỚC / MẶT SAU
  - Hàm dựng prompt động theo mặt thẻ (front/back)
  - Hàm suy luận mặt thẻ từ tên file ảnh

Tất cả các module khác (auto_label, label_tool, prepare_dataset, metrics)
đều import từ đây để đảm bảo prompt & schema luôn đồng nhất, tránh lệch
giữa lúc gán nhãn và lúc đánh giá.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List


class CardSide(str, Enum):
    """Mặt của thẻ CCCD."""

    FRONT = "truoc"
    BACK = "sau"
    UNKNOWN = "unknown"


# ── Định nghĩa trường cho từng mặt ──────────────────────────────────────────
# Dùng chung làm "schema" để validate, build prompt và tính metric.
FRONT_FIELDS: List[str] = [
    "so_cccd",
    "ho_va_ten",
    "ngay_sinh",
    "gioi_tinh",
    "quoc_tich",
    "que_quan",
    "noi_thuong_tru",
    "co_gia_tri_den",
]

BACK_FIELDS: List[str] = [
    "dac_diem_nhan_dang",
    "ngay_cap",
    "noi_cap",
]

# Trường meta luôn có ở mọi record để biết đây là mặt nào.
SIDE_FIELD = "mat_the"

# Mô tả người-đọc-được cho từng trường (dùng dựng prompt).
FIELD_DESCRIPTIONS: Dict[str, str] = {
    "so_cccd": '"so_cccd": "12 chữ số"',
    "ho_va_ten": '"ho_va_ten": "họ tên viết HOA"',
    "ngay_sinh": '"ngay_sinh": "DD/MM/YYYY"',
    "gioi_tinh": '"gioi_tinh": "Nam hoặc Nữ"',
    "quoc_tich": '"quoc_tich": "Việt Nam"',
    "que_quan": '"que_quan": "địa chỉ quê quán đầy đủ"',
    "noi_thuong_tru": '"noi_thuong_tru": "địa chỉ thường trú đầy đủ"',
    "co_gia_tri_den": (
        '"co_gia_tri_den": "Giá trị của mục \'Có giá trị đến / Date of expiry\'. '
        "Mục này có thể là NGÀY THÁNG hoặc DÒNG CHỮ. "
        "- Nếu là ngày tháng: trả về đúng định dạng DD/MM/YYYY (vd 12/05/2030). "
        "- Nếu trên thẻ ghi chữ KHÔNG THỜI HẠN (thẻ không có ngày hết hạn): "
        'trả về đúng chuỗi "Không thời hạn" (không tự bịa ra ngày). '
        'Chỉ để null khi mục này thật sự trống/không đọc được."'
    ),
    "dac_diem_nhan_dang": (
        '"dac_diem_nhan_dang": "Đặc điểm nhận dạng cá nhân (vd: sẹo, nốt ruồi, '
        "hình xăm, dấu vết...). Đây là DÒNG CHỮ VIẾT nằm ngay dưới tiêu đề in sẵn "
        "'Đặc điểm nhân dạng / Personal identification'. Hãy đọc kỹ, KHÔNG bỏ sót. "
        "TUYỆT ĐỐI KHÔNG điền ngày tháng (vd 22/02/2023) vào đây — ngày là của "
        'trường ngay_cap. Chỉ để null khi dòng này THẬT SỰ trống."'
    ),
    "ngay_cap": (
        '"ngay_cap": "Ngày cấp thẻ, định dạng DD/MM/YYYY. Đây là dòng ngày tháng '
        'nằm cạnh/dưới nơi cấp. Không nhầm với đặc điểm nhận dạng. Để null nếu không đọc được."'
    ),
    "noi_cap": '"noi_cap": "nơi cấp thẻ hoặc null"',
}

SYSTEM_PROMPT: str = (
    "Bạn là hệ thống OCR chuyên đọc Căn cước công dân (CCCD) Việt Nam. "
    "Chỉ trả về JSON thuần túy, không thêm bất kỳ text hay markdown nào khác."
)

# Quy tắc đọc văn bản xuống dòng — áp dụng cho MỌI mặt thẻ (đặc biệt là địa chỉ
# que_quan/noi_thuong_tru và dac_diem_nhan_dang vốn hay tràn sang dòng thứ 2).
MULTILINE_RULE: str = (
    "QUY TẮC XUỐNG DÒNG (áp dụng cho mọi trường):\n"
    "- Nếu nội dung MỘT trường trải trên NHIỀU dòng, đọc HẾT các dòng rồi nối lại "
    "thành một chuỗi, GIỮA các dòng thêm dấu phẩy ', ' "
    "(vd dòng 'Số 1 đường ABC' + dòng 'Phường X, Quận Y' → 'Số 1 đường ABC, Phường X, Quận Y').\n"
    "- NGOẠI LỆ — gạch nối ngắt từ: nếu CUỐI dòng có dấu gạch nối '-' (một từ bị tách "
    "giữa chừng do hết chỗ), BỎ dấu '-' và nối LIỀN với phần đầu dòng kế, "
    "TUYỆT ĐỐI KHÔNG thêm dấu phẩy (vd 'Hồ-' xuống dòng 'Chí Minh' → 'Hồ Chí Minh')."
)


def infer_side_from_filename(filename: str) -> CardSide:
    """
    Suy luận mặt thẻ từ tên file ảnh.

    Quy ước: tên chứa 'front'/'truoc'/'mt' → MẶT TRƯỚC;
             chứa 'back'/'sau'/'ms'        → MẶT SAU.

    Args:
        filename: Tên file (có hoặc không có path/extension).

    Returns:
        CardSide tương ứng, hoặc CardSide.UNKNOWN nếu không xác định được.
    """
    name = filename.lower()
    if any(tok in name for tok in ("front", "truoc", "_mt", "-mt", "mattruoc")):
        return CardSide.FRONT
    if any(tok in name for tok in ("back", "sau", "_ms", "-ms", "matsau")):
        return CardSide.BACK
    return CardSide.UNKNOWN


def fields_for_side(side: CardSide) -> List[str]:
    """Trả về danh sách trường kỳ vọng cho 1 mặt thẻ (gồm cả `mat_the`)."""
    if side == CardSide.FRONT:
        return FRONT_FIELDS + [SIDE_FIELD]
    if side == CardSide.BACK:
        return BACK_FIELDS + [SIDE_FIELD]
    # UNKNOWN → yêu cầu model đọc tất cả những gì có thể.
    return FRONT_FIELDS + BACK_FIELDS + [SIDE_FIELD]


def build_user_prompt(side: CardSide) -> str:
    """
    Dựng prompt người dùng (user turn) theo từng mặt thẻ.

    - FRONT: chỉ yêu cầu các trường mặt trước → giảm hallucination các
      trường chỉ có ở mặt sau (ngay_cap, noi_cap...).
    - BACK : chỉ yêu cầu các trường mặt sau.
    - UNKNOWN: yêu cầu toàn bộ trường (hành vi an toàn mặc định).

    Args:
        side: Mặt thẻ đã suy luận từ tên file.

    Returns:
        Chuỗi prompt hoàn chỉnh để đưa vào user turn.
    """
    if side == CardSide.FRONT:
        header = (
            "Đây là MẶT TRƯỚC của CCCD. Đọc ảnh và trích xuất các trường sau "
            "ra JSON. Nếu trường nào không đọc được thì để null:"
        )
        keys = FRONT_FIELDS
        side_value = '"mat_the": "truoc"'
    elif side == CardSide.BACK:
        header = (
            "Đây là MẶT SAU của CCCD. Hãy ĐỌC THẬT KỸ từng dòng và trích xuất các "
            "trường sau ra JSON. Bỏ qua mọi tiêu đề in sẵn và chữ tiếng Anh. "
            "LƯU Ý QUAN TRỌNG: 'đặc điểm nhận dạng' và 'ngày cấp' là HAI trường KHÁC "
            "NHAU, tuyệt đối đừng nhầm lẫn ngày tháng thành đặc điểm nhận dạng. "
            "Chỉ để null khi trường đó thật sự không đọc được:"
        )
        keys = BACK_FIELDS
        side_value = '"mat_the": "sau"'
    else:
        header = (
            "Đọc ảnh CCCD và trích xuất thông tin ra JSON. Tự xác định đây là "
            "mặt trước hay mặt sau. Trường nào không có thì để null:"
        )
        keys = FRONT_FIELDS + BACK_FIELDS
        side_value = '"mat_the": "truoc hoặc sau"'

    body_lines = [FIELD_DESCRIPTIONS[k] for k in keys] + [side_value]
    body = ",\n  ".join(body_lines)
    return f"{header}\n{MULTILINE_RULE}\n{{\n  {body}\n}}"


def human_value(side: CardSide) -> str:
    """Dựng giá trị `human` (có token <image>) cho record fine-tuning."""
    return f"<image>\n{build_user_prompt(side)}"
