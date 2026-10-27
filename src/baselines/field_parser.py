"""Map raw OCR lines to the CCCD JSON schema using printed-label anchors."""

from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Sequence, Tuple

from src.baselines.ocr_engines import OcrLine, group_rows, row_text
from src.utils.cccd_schema import (
    BACK_FIELDS,
    FRONT_FIELDS,
    SIDE_FIELD,
    CardSide,
)

logger = logging.getLogger(__name__)


def deaccent(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    # `đ/Đ` does not decompose under NFD.
    return stripped.replace("đ", "d").replace("Đ", "D")


def squash(text: str) -> Tuple[str, List[int]]:
    """Fold to accent-free lowercase alphanumerics, plus a map back to original offsets."""
    chars: List[str] = []
    index_map: List[int] = []
    for position, char in enumerate(text):
        for folded in deaccent(char).lower():
            if folded.isalnum():
                chars.append(folded)
                index_map.append(position)
    return "".join(chars), index_map


# Squashed label variants, longest first so the bilingual label wins.
ANCHORS: Dict[str, Tuple[str, ...]] = {
    "so_cccd": ("sodinhdanhcanhan", "socancuoccongdan", "socccdno", "socccd", "sono"),
    "ho_va_ten": ("hovatenfullname", "hovaten", "fullname"),
    "ngay_sinh": ("ngaysinhdateofbirth", "ngaysinh", "dateofbirth"),
    "gioi_tinh": ("gioitinhsex", "gioitinh", "sex"),
    "quoc_tich": ("quoctichnationality", "quoctich", "nationality"),
    "que_quan": ("quequanplaceoforigin", "quequan", "placeoforigin"),
    "noi_thuong_tru": (
        "noithuongtruplaceofresidence",
        "noithuongtru",
        "placeofresidence",
        "noicutru",
        "placeofresident",
    ),
    "co_gia_tri_den": ("cogiatridendateofexpiry", "cogiatriden", "dateofexpiry"),
    "dac_diem_nhan_dang": (
        "dacdiemnhandangpersonalidentification",
        "dacdiemnhandang",
        "personalidentification",
    ),
    "ngay_cap": (
        "ngaythangnamdatemonthyear",
        "ngaythangnam",
        "datemonthyear",
        "dateofissue",
        "ngaycap",
    ),
}

# `noi_cap` has no printed label, so it is scanned separately.
NOI_CAP_TOKENS: Tuple[str, ...] = (
    "cuctruongcuccanhsat",
    "quanlyhanhchinh",
    "trattuxahoi",
    "cuctruong",
    "cuccanhsat",
    "giamdoccongan",
)

HEADER_TOKENS: Tuple[str, ...] = (
    "conghoaxahoichunghiavietnam",
    "socialistrepublicofvietnam",
    "doclaptudohanhphuc",
    "independencefreedomhappiness",
    "cancuoccongdan",
    "citizenidentitycard",
)

# Fuzzy matching short labels only yields false positives.
_MIN_FUZZY_LEN: int = 8
_FUZZY_THRESHOLD: float = 0.82

_DATE_RE = re.compile(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})")
_LEAD_JUNK = re.compile(r"^[\s:;/\\\-.,|>»·•]+")
_TRAIL_JUNK = re.compile(r"[\s:;/\\.,|]+$")


def is_mrz(text: str) -> bool:
    """Detect MRZ lines, which sit right under `dac_diem_nhan_dang`."""
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    if compact.count("<") >= 3:
        return True
    # Digits required so the uppercase `noi_cap` block is not filtered out.
    if len(compact) >= 20 and any(ch.isdigit() for ch in compact):
        allowed = sum(1 for ch in compact if ch.isdigit() or ch.isupper() or ch == "<")
        if allowed / len(compact) >= 0.92:
            return True
    return False


def is_header(squashed: str) -> bool:
    return any(token in squashed for token in HEADER_TOKENS)


def _extend_anchor(
    squashed: str, end: int, variants: Sequence[str], threshold: float
) -> int:
    """Absorb a following label variant so a mangled bilingual half is not read as value."""
    while True:
        for variant in variants:
            size = len(variant)
            window = squashed[end : end + size]
            if len(window) < size:
                continue
            if window == variant or (
                size >= _MIN_FUZZY_LEN
                and SequenceMatcher(None, window, variant).ratio() >= threshold
            ):
                end += size
                break
        else:
            return end


def find_anchor(
    squashed: str, variants: Sequence[str], threshold: float = _FUZZY_THRESHOLD
) -> Optional[Tuple[int, int, str, float]]:
    """Find a printed label; returns `(start, end, variant, score)` in squashed indices."""
    candidates: List[Tuple[int, int, str, float]] = []
    for variant in variants:
        position = squashed.find(variant)
        if position >= 0:
            candidates.append((position, position + len(variant), variant, 1.0))

    if not candidates:
        for variant in variants:
            size = len(variant)
            if size < _MIN_FUZZY_LEN or size > len(squashed):
                continue
            for start in range(0, len(squashed) - size + 1):
                score = SequenceMatcher(None, squashed[start : start + size], variant).ratio()
                if score >= threshold:
                    candidates.append((start, start + size, variant, score))

    if not candidates:
        return None

    # Earliest then longest, not best score: scoring picks short variants and cuts mid-label.
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), -item[3]))
    start, end, variant, score = candidates[0]
    return start, _extend_anchor(squashed, end, variants, threshold), variant, score


def clean_value(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = _LEAD_JUNK.sub("", text)
    text = _TRAIL_JUNK.sub("", text)
    return text.strip()


def smart_join(pieces: Sequence[str], mode: str = "comma") -> str:
    """Join lines of one field per `cccd_schema.MULTILINE_RULE`."""
    joined = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if not joined:
            joined = piece
            continue
        if joined.endswith("-"):
            joined = joined[:-1].rstrip() + piece.lstrip()
        elif mode == "space" or joined.endswith((",", ";")):
            joined = f"{joined} {piece}"
        else:
            joined = f"{joined}, {piece}"
    return re.sub(r"\s+", " ", joined).strip()


_SPACE_JOIN_FIELDS = {"dac_diem_nhan_dang", "noi_cap"}


def extract_date(text: str) -> Optional[str]:
    """First date in the string, normalized to `DD/MM/YYYY`."""
    match = _DATE_RE.search(text)
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups())
    if year < 100:
        year += 2000 if year < 50 else 1900
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    return f"{day:02d}/{month:02d}/{year:04d}"


def extract_cccd_number(text: str, strict: bool = False) -> Optional[str]:
    """Pull the 12-digit number; `strict` is required when scanning the whole card."""
    compact = re.sub(r"\s+", "", text)
    match = re.search(r"(?<!\d)\d{12}(?!\d)", compact)
    if match:
        return match.group()
    if strict:
        return None
    # Lenient branch would glue two dates into an invented number on a full-card scan.
    digits = re.sub(r"\D", "", compact)
    return digits[:12] if len(digits) >= 12 else None


def extract_gender(text: str) -> Optional[str]:
    token = deaccent(clean_value(text)).lower().strip()
    if not token:
        return None
    first = re.split(r"[^a-z]+", token)[0] if re.split(r"[^a-z]+", token) else ""
    if first.startswith("nam"):
        return "Nam"
    if first.startswith("nu"):
        return "Nữ"
    return None


CANONICAL_NOI_CAP: str = "CỤC TRƯỞNG CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI"


def _target_fields(side: CardSide) -> List[str]:
    if side == CardSide.FRONT:
        return list(FRONT_FIELDS)
    if side == CardSide.BACK:
        return list(BACK_FIELDS)
    return list(FRONT_FIELDS) + list(BACK_FIELDS)


def _row_hits(squashed: str, index_map: List[int], fields: Sequence[str]) -> List[Tuple[int, int, str, float]]:
    """All labels in one row, overlaps removed, sorted by position."""
    raw_hits: List[Tuple[int, int, str, float]] = []
    for name in fields:
        variants = ANCHORS.get(name)
        if not variants:
            continue
        found = find_anchor(squashed, variants)
        if found:
            start, end, _variant, score = found
            raw_hits.append((start, end, name, score))

    raw_hits.sort(key=lambda hit: (-hit[3], -(hit[1] - hit[0]), hit[0]))
    kept: List[Tuple[int, int, str, float]] = []
    for hit in raw_hits:
        if all(hit[1] <= other[0] or hit[0] >= other[1] for other in kept):
            kept.append(hit)
    kept.sort(key=lambda hit: hit[0])

    # Back to original indices so values keep their accents.
    return [
        (index_map[start], index_map[end - 1] + 1, name, score)
        for start, end, name, score in kept
    ]


def parse_ocr_lines(
    lines: Sequence[OcrLine],
    side: CardSide,
    canonicalize: bool = False,
    return_debug: bool = False,
):
    """Extract CCCD fields from the OCR lines of one image."""
    fields = _target_fields(side)
    buckets: Dict[str, List[str]] = {}
    debug_rows: List[dict] = []
    noi_cap_pieces: List[str] = []
    # Also holds rows that matched no field; fallback scans need them.
    card_text: List[str] = []

    rows = group_rows(lines)
    current: Optional[str] = None

    for row in rows:
        text = row_text(row)
        if not text:
            continue
        squashed, index_map = squash(text)
        if not squashed:
            continue

        # MRZ and headings must also break the open field's continuation.
        if is_mrz(text) or is_header(squashed):
            current = None
            debug_rows.append({"text": text, "skip": "mrz/header"})
            continue

        card_text.append(text)

        if any(token in squashed for token in NOI_CAP_TOKENS):
            noi_cap_pieces.append(clean_value(text))
            current = None
            debug_rows.append({"text": text, "field": "noi_cap"})
            continue

        hits = _row_hits(squashed, index_map, fields)

        if not hits:
            if current:
                buckets.setdefault(current, []).append(clean_value(text))
                debug_rows.append({"text": text, "cont": current})
            else:
                debug_rows.append({"text": text, "skip": "không thuộc trường nào"})
            continue

        head = clean_value(text[: hits[0][0]])
        if head and current:
            buckets.setdefault(current, []).append(head)

        for position, (_start, end, name, score) in enumerate(hits):
            stop = hits[position + 1][0] if position + 1 < len(hits) else len(text)
            value = clean_value(text[end:stop])
            buckets.setdefault(name, [])
            if value:
                buckets[name].append(value)
            current = name
            debug_rows.append({"text": text, "field": name, "value": value, "score": round(score, 3)})

    result = _finalize(buckets, noi_cap_pieces, " ".join(card_text), side, fields, canonicalize)
    if return_debug:
        return result, {"rows": debug_rows, "n_lines": len(lines), "n_rows": len(rows)}
    return result


def _finalize(
    buckets: Dict[str, List[str]],
    noi_cap_pieces: List[str],
    card_text: str,
    side: CardSide,
    fields: Sequence[str],
    canonicalize: bool,
) -> Dict[str, Optional[str]]:
    merged: Dict[str, str] = {
        name: smart_join(pieces, "space" if name in _SPACE_JOIN_FIELDS else "comma")
        for name, pieces in buckets.items()
    }
    if noi_cap_pieces:
        merged["noi_cap"] = smart_join(noi_cap_pieces, "space")

    out: Dict[str, Optional[str]] = {}
    for name in fields:
        value = merged.get(name, "")

        if name == "so_cccd":
            # A 12-digit run is a stronger signal than the short "Số / No." label.
            value = extract_cccd_number(value) or extract_cccd_number(card_text, strict=True) or ""
        elif name in ("ngay_sinh", "ngay_cap"):
            value = extract_date(value) or ""
        elif name == "co_gia_tri_den":
            date = extract_date(value)
            if date:
                value = date
            elif "khongthoihan" in squash(value)[0]:
                value = "Không thời hạn"
        elif name == "gioi_tinh":
            value = extract_gender(value) or ""
        elif name == "quoc_tich":
            value = clean_value(value)
            if canonicalize and "vietnam" in squash(value)[0]:
                value = "Việt Nam"
        elif name == "dac_diem_nhan_dang":
            value = clean_value(value)
            # This rule is part of the prompt every VLM receives.
            if _DATE_RE.search(value):
                value = ""
        elif name == "noi_cap":
            value = clean_value(value)
            if canonicalize and "quanlyhanhchinh" in squash(value)[0]:
                value = CANONICAL_NOI_CAP
        else:
            value = clean_value(value)

        out[name] = value or None

    out[SIDE_FIELD] = side.value if side != CardSide.UNKNOWN else None
    return out


def filled_ratio(parsed: Dict[str, Optional[str]]) -> float:
    if not parsed:
        return 0.0
    return sum(1 for value in parsed.values() if value) / len(parsed)


def _mock_lines(rows: Sequence[Tuple[int, Sequence[Tuple[int, str]]]]) -> List[OcrLine]:
    lines: List[OcrLine] = []
    for top, items in rows:
        for left, text in items:
            width = max(len(text) * 9, 20)
            lines.append(OcrLine(text=text, box=(left, top, left + width, top + 26), conf=0.99))
    return lines


_FRONT_ROWS = [
    (20, [(120, "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")]),
    (50, [(180, "Độc lập - Tự do - Hạnh phúc")]),
    (85, [(150, "CĂN CƯỚC CÔNG DÂN")]),
    (120, [(300, "Số / No.:"), (420, "089203011696")]),
    (155, [(300, "Họ và tên / Full name:")]),
    (185, [(320, "NGUYỄN THƯỜNG QUÂN")]),
    (215, [(300, "Ngày sinh / Date of birth:"), (540, "25/11/2003")]),
    (245, [(300, "Giới tính / Sex:"), (430, "Nam"),
           (500, "Quốc tịch / Nationality:"), (700, "Việt Nam")]),
    (275, [(300, "Quê quán / Place of origin:"), (540, "Phước Hưng, An Phú,")]),
    (305, [(320, "An Giang")]),
    (335, [(300, "Nơi thường trú / Place of residence:"), (600, "Ấp Phước Hòa,")]),
    (365, [(320, "Phước Hưng, An Phú, An Giang")]),
    (410, [(60, "Có giá trị đến / Date of expiry:"), (320, "25/11/2028")]),
]

_BACK_ROWS = [
    (40, [(40, "Đặc điểm nhân dạng /"), (300, "Sẹo chấm C:2cm trên")]),
    (70, [(40, "Personal identification:"), (300, "sau cánh mũi trái")]),
    (125, [(40, "Ngày, tháng, năm / Date, month, year:"), (420, "22/09/2021")]),
    (165, [(350, "CỤC TRƯỞNG CỤC CẢNH SÁT")]),
    (195, [(320, "QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI")]),
    (265, [(20, "IDVNM0700091409096070009140<<2")]),
    (295, [(20, "7001017M3001019VNM<<<<<<<<<<<<<<2")]),
    (325, [(20, "HUU<<UT<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")]),
]

# Taken verbatim from Front_draft.jsonl / Back_draft.jsonl.
_FRONT_GOLD = {
    "so_cccd": "089203011696",
    "ho_va_ten": "NGUYỄN THƯỜNG QUÂN",
    "ngay_sinh": "25/11/2003",
    "gioi_tinh": "Nam",
    "quoc_tich": "Việt Nam",
    "que_quan": "Phước Hưng, An Phú, An Giang",
    "noi_thuong_tru": "Ấp Phước Hòa, Phước Hưng, An Phú, An Giang",
    "co_gia_tri_den": "25/11/2028",
    "mat_the": "truoc",
}
_BACK_GOLD = {
    "dac_diem_nhan_dang": "Sẹo chấm C:2cm trên sau cánh mũi trái",
    "ngay_cap": "22/09/2021",
    "noi_cap": "CỤC TRƯỞNG CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI",
    "mat_the": "sau",
}


def _smoke_test() -> int:
    """Run the parser on mock layouts; needs no paddleocr/vietocr install."""
    from src.utils.metrics import normalize_text

    cases = [
        ("MẶT TRƯỚC", _FRONT_ROWS, CardSide.FRONT, _FRONT_GOLD),
        ("MẶT SAU", _BACK_ROWS, CardSide.BACK, _BACK_GOLD),
    ]
    n_fail = 0
    for title, rows, side, gold in cases:
        parsed = parse_ocr_lines(_mock_lines(rows), side)
        print(f"\n=== {title} ===")
        for name, expected in gold.items():
            got = parsed.get(name)
            hit = normalize_text(got) == normalize_text(expected)
            n_fail += not hit
            print(f"  {'✓' if hit else '✗'} {name}: {got!r}")
            if not hit:
                print(f"      kỳ vọng: {expected!r}")

    print(f"\n{'✅ Tất cả trường khớp' if not n_fail else f'❌ {n_fail} trường sai'}\n")
    return n_fail


if __name__ == "__main__":
    from src.utils.console import force_utf8_output

    force_utf8_output()
    raise SystemExit(1 if _smoke_test() else 0)
