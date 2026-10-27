"""Extraction metrics: Field Accuracy, Character Error Rate, micro-F1."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def normalize_text(value: Optional[object]) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("null", "none"):
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def levenshtein(a: str, b: str) -> int:
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


@dataclass
class EvalResult:
    field_accuracy: float
    cer: float
    f1: float
    precision: float
    recall: float
    n_samples: int
    n_fields: int
    per_field_accuracy: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
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


def _tokens(text: str) -> List[str]:
    return re.findall(r"\w+", text, flags=re.UNICODE)


def _f1_counts(pred: str, gold: str) -> tuple[int, int, int]:
    """Returns (true_positive, pred_total, gold_total) at token level."""
    pc, gc = Counter(_tokens(pred)), Counter(_tokens(gold))
    tp = sum((pc & gc).values())
    return tp, sum(pc.values()), sum(gc.values())


def evaluate_pair(pred: dict, gold: dict) -> Dict[str, tuple]:
    """Per-field {field: (exact_match, cer, tp, pred_total, gold_total)} for one sample."""
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
    """Parse a model answer (str/dict) into a dict; unparseable input becomes {}."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}

    text = value.strip()
    if not text:
        return {}

    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass

    # Markdown fence: ```json\n{...}\n```
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        fenced = "\n".join(lines[1:end]).strip()
        try:
            obj = json.loads(fenced)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            text = fenced or text

    # Prose around the JSON: take the first {...} block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group())
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


if __name__ == "__main__":
    preds = [{"so_cccd": "012345678901", "ho_va_ten": "NGUYEN VAN A"}]
    golds = [{"so_cccd": "012345678901", "ho_va_ten": "NGUYEN VAN AN"}]
    print(json.dumps(evaluate(preds, golds).as_dict(), ensure_ascii=False, indent=2))
