"""
metrics.py
==========
Đo chất lượng trích xuất JSON của model so với ground-truth (tập Test).

Ba chỉ số:
  1. Field Accuracy (FA): tỷ lệ trường khớp CHÍNH XÁC (sau chuẩn hóa) trên tổng
     số trường. Phản ánh "đọc đúng nguyên trường" — chỉ số nghiệm thu chính.
  2. Character Error Rate (CER): khoảng cách Levenshtein mức ký tự / độ dài GT,
     trung bình trên các trường. Đo mức độ "sai nhẹ" (lệch 1-2 ký tự) — hữu ích
     vì FA bị phạt nặng dù chỉ sai 1 ký tự.
  3. F1 (micro) trên token: precision/recall mức từ, tổng hợp toàn bộ trường —
     đánh giá tổng thể độ trùng nội dung.

Tất cả so sánh sau khi chuẩn hóa (lower, gộp khoảng trắng, None↔"").
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Chuẩn hóa ───────────────────────────────────────────────────────────────
def normalize_text(value: Optional[object]) -> str:
    """
    Chuẩn hóa 1 giá trị trường để so sánh công bằng.

    - None / "null" / "none" → "".
    - Chuẩn hóa Unicode NFC, bỏ khoảng trắng thừa, hạ chữ thường.

    Args:
        value: Giá trị thô (str/None/số...).

    Returns:
        Chuỗi đã chuẩn hóa.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("null", "none"):
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def levenshtein(a: str, b: str) -> int:
    """
    Khoảng cách Levenshtein mức ký tự giữa 2 chuỗi (DP O(len(a)*len(b))).

    Returns:
        Số phép chèn/xóa/thay tối thiểu để biến a → b.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


# ── Kết quả ─────────────────────────────────────────────────────────────────
@dataclass
class EvalResult:
    """Tổng hợp kết quả đánh giá toàn bộ tập test."""

    field_accuracy: float
    cer: float
    f1: float
    precision: float
    recall: float
    n_samples: int
    n_fields: int
    per_field_accuracy: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        """Xuất ra dict để log/serialize."""
        return {
            "field_accuracy": round(self.field_accuracy, 4),
            "cer": round(self.cer, 4),
            "f1": round(self.f1, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "n_samples": self.n_samples,
            "n_fields": self.n_fields,
            "per_field_accuracy": {k: round(v, 4) for k, v in self.per_field_accuracy.items()},
        }


# ── Tokenize cho F1 ─────────────────────────────────────────────────────────
def _tokens(text: str) -> List[str]:
    """Tách chuỗi đã chuẩn hóa thành token từ (cho F1)."""
    return re.findall(r"\w+", text, flags=re.UNICODE)


def _f1_counts(pred: str, gold: str) -> tuple[int, int, int]:
    """Trả về (true_positive, pred_total, gold_total) ở mức token cho 1 trường."""
    pc, gc = Counter(_tokens(pred)), Counter(_tokens(gold))
    tp = sum((pc & gc).values())
    return tp, sum(pc.values()), sum(gc.values())


# ── Đánh giá ────────────────────────────────────────────────────────────────
def evaluate_pair(pred: dict, gold: dict) -> Dict[str, tuple]:
    """
    So sánh 1 cặp (pred, gold) theo từng trường có trong gold.

    Returns:
        dict {field: (exact_match: 0/1, cer_field: float, tp, p_tot, g_tot)}.
    """
    out: Dict[str, tuple] = {}
    for key, gold_raw in gold.items():
        g = normalize_text(gold_raw)
        p = normalize_text(pred.get(key))
        exact = 1 if p == g else 0
        cer = 0.0 if not g else levenshtein(p, g) / max(len(g), 1)
        tp, p_tot, g_tot = _f1_counts(p, g)
        out[key] = (exact, cer, tp, p_tot, g_tot)
    return out


def evaluate(predictions: List[dict], golds: List[dict]) -> EvalResult:
    """
    Tính FA / CER / F1 trên toàn bộ tập test.

    Args:
        predictions: list dict JSON model dự đoán (đã parse).
        golds: list dict JSON ground-truth, cùng thứ tự & độ dài.

    Returns:
        EvalResult.
    """
    if len(predictions) != len(golds):
        raise ValueError(f"Số lượng lệch: pred={len(predictions)} vs gold={len(golds)}")

    total_fields = 0
    correct_fields = 0
    cer_sum = 0.0
    tp_sum = p_sum = g_sum = 0
    field_correct: Counter = Counter()
    field_total: Counter = Counter()

    for pred, gold in zip(predictions, golds):
        per_field = evaluate_pair(pred or {}, gold or {})
        for key, (exact, cer, tp, p_tot, g_tot) in per_field.items():
            total_fields += 1
            correct_fields += exact
            cer_sum += cer
            tp_sum += tp
            p_sum += p_tot
            g_sum += g_tot
            field_total[key] += 1
            field_correct[key] += exact

    fa = correct_fields / total_fields if total_fields else 0.0
    cer = cer_sum / total_fields if total_fields else 0.0
    precision = tp_sum / p_sum if p_sum else 0.0
    recall = tp_sum / g_sum if g_sum else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    per_field_acc = {k: field_correct[k] / field_total[k] for k in field_total}

    return EvalResult(
        field_accuracy=fa,
        cer=cer,
        f1=f1,
        precision=precision,
        recall=recall,
        n_samples=len(predictions),
        n_fields=total_fields,
        per_field_accuracy=per_field_acc,
    )


def safe_parse(value: object) -> dict:
    """Parse 1 giá trị JSON (str/dict) → dict; lỗi → {} (đếm là sai hết)."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            obj = json.loads(value)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


if __name__ == "__main__":
    # Ví dụ tự kiểm tra nhanh.
    preds = [{"so_cccd": "012345678901", "ho_va_ten": "NGUYEN VAN A"}]
    golds = [{"so_cccd": "012345678901", "ho_va_ten": "NGUYEN VAN AN"}]
    print(json.dumps(evaluate(preds, golds).as_dict(), ensure_ascii=False, indent=2))
