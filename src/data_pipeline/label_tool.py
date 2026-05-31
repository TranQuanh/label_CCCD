"""
label_tool.py
=============
Bước 2 (Human-in-the-loop): Web UI bằng Gradio để CON NGƯỜI duyệt & sửa nhãn
draft do `auto_label.py` sinh ra. Chạy được trực tiếp trên Google Colab
(`launch(share=True)` tạo link public).

Luồng làm việc:
  1. Load file draft JSONL + folder ảnh `data/raw/`.
  2. Hiển thị ảnh CCCD bên trái, các trường JSON dạng Textbox bên phải.
  3. Người duyệt đối chiếu ảnh ↔ text, sửa trực tiếp trường sai.
  4. Nhấn "💾 Save & Next" → GHI ĐÈ (overwrite) record đã sửa vào đúng file
     JSONL gốc, đánh dấu `_meta.reviewed = True`, rồi nhảy sang ảnh kế.

Mỗi lần Save ghi lại TOÀN BỘ file (atomic qua temp) để không mất dữ liệu.

Cách dùng:
  python -m src.data_pipeline.label_tool --jsonl data/draft/raw_draft.jsonl --image_root .
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gradio as gr

from src.utils.cccd_schema import BACK_FIELDS, FRONT_FIELDS, SIDE_FIELD, CardSide

# Union tất cả trường để render cố định 1 bộ Textbox (front + back + mat_the).
ALL_FIELDS: List[str] = FRONT_FIELDS + BACK_FIELDS + [SIDE_FIELD]


class LabelStore:
    """
    Quản lý đọc/ghi file draft JSONL và state con trỏ ảnh hiện tại.

    Giữ toàn bộ record trong RAM; mỗi lần save ghi đè lại cả file (atomic).
    """

    def __init__(self, jsonl_path: Path, image_root: Path) -> None:
        self.jsonl_path = jsonl_path
        self.image_root = image_root
        self.records: List[dict] = self._load()

    def _load(self) -> List[dict]:
        """Đọc toàn bộ JSONL vào list dict."""
        records: List[dict] = []
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        if not records:
            raise ValueError(f"File draft rỗng: {self.jsonl_path}")
        return records

    def save_all(self) -> None:
        """Ghi đè toàn bộ file JSONL một cách an toàn (write temp → replace)."""
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.jsonl_path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for rec in self.records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            os.replace(tmp_path, self.jsonl_path)  # atomic trên cùng filesystem
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def count(self) -> int:
        """Số record."""
        return len(self.records)

    def num_reviewed(self) -> int:
        """Số record đã được người duyệt đánh dấu reviewed."""
        return sum(1 for r in self.records if r.get("_meta", {}).get("reviewed"))

    def get_fields(self, idx: int) -> Tuple[str, Dict[str, str], str]:
        """
        Lấy dữ liệu hiển thị cho record thứ idx.

        Returns:
            (đường dẫn ảnh tuyệt đối, dict {field: value}, text trạng thái).
        """
        rec = self.records[idx]
        gpt_value = rec["conversations"][1]["value"]
        try:
            parsed = json.loads(gpt_value)
        except json.JSONDecodeError:
            parsed = {}  # draft chưa parse được → để trống cho người nhập tay

        fields = {k: _to_str(parsed.get(k)) for k in ALL_FIELDS}

        img_rel = rec["image"]
        img_abs = str((self.image_root / img_rel).resolve())
        if not os.path.exists(img_abs):  # fallback: thử path nguyên gốc
            img_abs = img_rel

        reviewed = rec.get("_meta", {}).get("reviewed", False)
        status = (
            f"Ảnh {idx + 1}/{self.count()} | "
            f"mặt: {rec.get('_meta', {}).get('side', '?')} | "
            f"{'✅ đã duyệt' if reviewed else '⚠️ chưa duyệt'} | "
            f"Tiến độ: {self.num_reviewed()}/{self.count()}"
        )
        return img_abs, fields, status

    def update_record(self, idx: int, edited: Dict[str, str]) -> None:
        """
        Ghi đè record idx từ giá trị người dùng sửa, đánh dấu reviewed=True.

        Chỉ giữ các trường tương ứng với mặt thẻ để JSON gọn & đúng schema.
        """
        rec = self.records[idx]
        side_val = (edited.get(SIDE_FIELD) or "").strip().lower()
        if side_val == CardSide.FRONT.value:
            keep = FRONT_FIELDS + [SIDE_FIELD]
        elif side_val == CardSide.BACK.value:
            keep = BACK_FIELDS + [SIDE_FIELD]
        else:
            keep = ALL_FIELDS

        clean: Dict[str, Optional[str]] = {}
        for k in keep:
            v = (edited.get(k) or "").strip()
            clean[k] = None if v.lower() in ("", "null", "none") else v

        rec["conversations"][1]["value"] = json.dumps(clean, ensure_ascii=False)
        rec.setdefault("_meta", {})["reviewed"] = True
        rec["_meta"]["parse_ok"] = True


def _to_str(value: object) -> str:
    """Chuyển giá trị JSON về string hiển thị (None → '')."""
    if value is None:
        return ""
    return str(value)


def build_ui(store: LabelStore) -> gr.Blocks:
    """
    Dựng giao diện Gradio Blocks.

    Args:
        store: LabelStore đã load dữ liệu.

    Returns:
        gr.Blocks sẵn sàng .launch().
    """
    with gr.Blocks(title="CCCD Label Reviewer") as demo:
        gr.Markdown("## 🪪 CCCD Label Reviewer — duyệt & sửa nhãn draft")
        idx_state = gr.State(0)

        with gr.Row():
            with gr.Column(scale=1):
                image_view = gr.Image(label="Ảnh CCCD", type="filepath", height=420)
                status_box = gr.Textbox(label="Trạng thái", interactive=False)
            with gr.Column(scale=1):
                field_boxes: Dict[str, gr.Textbox] = {
                    k: gr.Textbox(label=k, lines=2 if "noi" in k or "que" in k else 1)
                    for k in ALL_FIELDS
                }
                with gr.Row():
                    prev_btn = gr.Button("⬅️ Prev")
                    save_btn = gr.Button("💾 Save & Next", variant="primary")
                    next_btn = gr.Button("Skip ➡️")

        def render(idx: int) -> list:
            """Đổ dữ liệu record idx ra UI."""
            img, fields, status = store.get_fields(idx)
            return [img, status, idx] + [fields[k] for k in ALL_FIELDS]

        def on_save(idx: int, *values: str) -> list:
            """Ghi đè record hiện tại rồi nhảy sang ảnh kế (clamp ở cuối)."""
            edited = dict(zip(ALL_FIELDS, values))
            store.update_record(idx, edited)
            store.save_all()
            new_idx = min(idx + 1, store.count() - 1)
            return render(new_idx)

        def on_nav(idx: int, step: int) -> list:
            """Điều hướng prev/next không lưu (clamp trong [0, n-1])."""
            new_idx = max(0, min(idx + step, store.count() - 1))
            return render(new_idx)

        outputs = [image_view, status_box, idx_state] + [field_boxes[k] for k in ALL_FIELDS]

        save_btn.click(
            on_save,
            inputs=[idx_state] + [field_boxes[k] for k in ALL_FIELDS],
            outputs=outputs,
        )
        prev_btn.click(lambda i: on_nav(i, -1), inputs=idx_state, outputs=outputs)
        next_btn.click(lambda i: on_nav(i, +1), inputs=idx_state, outputs=outputs)
        demo.load(lambda: render(0), inputs=None, outputs=outputs)

    return demo


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Gradio CCCD label reviewer")
    parser.add_argument("--jsonl", required=True, help="File draft JSONL cần duyệt")
    parser.add_argument(
        "--image_root", default=".",
        help="Thư mục gốc để resolve trường 'image' trong JSONL (default: .)",
    )
    parser.add_argument("--share", action="store_true", help="Tạo link public (Colab)")
    parser.add_argument("--server_port", type=int, default=7860)
    return parser.parse_args()


def main() -> None:
    """Entry point CLI."""
    args = parse_args()
    store = LabelStore(Path(args.jsonl), Path(args.image_root))
    demo = build_ui(store)
    demo.launch(share=args.share, server_port=args.server_port)


if __name__ == "__main__":
    main()
