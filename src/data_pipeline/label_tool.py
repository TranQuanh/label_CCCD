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

Cách dùng (local):
  python -m src.data_pipeline.label_tool \
      --jsonl Front_draft.jsonl \
      --front_dir data/Front --back_dir data/Back

Trường 'image' trong draft là path tuyệt đối sinh ra trên Colab; bản local
resolve ảnh theo TÊN FILE trong --front_dir / --back_dir. Ô "Jump to index"
cho gõ SỐ THỨ TỰ ảnh (1-based, khớp "Ảnh N/total" ở ô trạng thái) để nhảy
thẳng tới record thứ N.

Hiệu năng: ảnh gốc có thể nặng vài MB; mỗi lần điều hướng Gradio phải đọc &
serve cả file → chậm. Ta tạo bản thu nhỏ (thumbnail) cache lại để navigation
mượt hơn nhiều mà vẫn đủ nét để đối chiếu OCR.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gradio as gr

from src.utils.cccd_schema import (
    BACK_FIELDS,
    FRONT_FIELDS,
    SIDE_FIELD,
    CardSide,
    infer_side_from_filename,
)

# Union tất cả trường để render cố định 1 bộ Textbox (front + back + mat_the).
ALL_FIELDS: List[str] = FRONT_FIELDS + BACK_FIELDS + [SIDE_FIELD]

# Alias tương thích ngược: draft cũ lưu key "ngay_het_han", nay đổi thành
# "co_gia_tri_den". Khi đọc record cũ, map giá trị sang tên trường mới.
FIELD_ALIASES: Dict[str, str] = {"co_gia_tri_den": "ngay_het_han"}

# Cạnh dài tối đa (px) của thumbnail phục vụ cho Gradio. Card CCCD ở ~1600px
# vẫn đọc rõ chữ nhỏ (đặc điểm nhận dạng) mà file chỉ còn vài trăm KB.
THUMB_MAX_PX: int = 1600


class LabelStore:
    """
    Quản lý đọc/ghi file draft JSONL và state con trỏ ảnh hiện tại.

    Giữ toàn bộ record trong RAM; mỗi lần save ghi đè lại cả file (atomic).
    """

    def __init__(
        self,
        jsonl_path: Path,
        image_root: Path,
        front_dir: Optional[Path] = None,
        back_dir: Optional[Path] = None,
    ) -> None:
        self.jsonl_path = jsonl_path
        self.image_root = image_root
        # Thư mục ảnh local theo mặt thẻ (dùng để resolve ảnh bằng tên file,
        # vì trường "image" trong draft là path tuyệt đối sinh ra trên Colab).
        self.front_dir = front_dir
        self.back_dir = back_dir
        self.records: List[dict] = self._load()
        # Cache thumbnail: key = "path|mtime|size" -> đường dẫn file thu nhỏ.
        self._thumb_cache: Dict[str, str] = {}
        self._thumb_dir = Path(tempfile.mkdtemp(prefix="cccd_label_thumbs_"))

    def goto(self, query: str) -> Optional[int]:
        """
        Nhảy tới ảnh theo SỐ THỨ TỰ (1-based, khớp "Ảnh N/total").

        '17' → record ở vị trí thứ 17. Trả về idx (0-based) hoặc None nếu số
        rỗng / ngoài phạm vi 1..count.
        """
        digits = re.sub(r"\D", "", query or "")
        if not digits:
            return None
        pos = int(digits) - 1
        if 0 <= pos < self.count():
            return pos
        return None

    def _resolve_image(self, img_field: str) -> str:
        """
        Tìm đường dẫn ảnh thực trên máy local theo TÊN FILE.

        Trường 'image' trong draft là path tuyệt đối của Colab nên không
        dùng trực tiếp được; ta lấy basename rồi dò trong data/Front, data/Back.
        """
        name = Path(img_field).name
        side = infer_side_from_filename(name)
        # Ưu tiên thư mục đúng mặt thẻ, sau đó thử nốt mặt còn lại.
        search_dirs: List[Optional[Path]] = []
        if side == CardSide.BACK:
            search_dirs = [self.back_dir, self.front_dir]
        else:
            search_dirs = [self.front_dir, self.back_dir]
        for d in search_dirs:
            if d is not None:
                cand = d / name
                if cand.exists():
                    return str(cand.resolve())
        # Fallback: image_root / image (bố cục giống lúc label), rồi path gốc.
        cand_root = self.image_root / img_field
        if cand_root.exists():
            return str(cand_root.resolve())
        return img_field

    def _thumbnail(self, src: str) -> str:
        """
        Trả về bản thu nhỏ (cache) của ảnh `src` để Gradio serve nhanh.

        Cache theo (path, mtime, size) nên điều hướng qua lại không encode lại.
        Nếu Pillow lỗi / ảnh không tồn tại → trả nguyên `src` (vẫn xem được,
        chỉ chậm như cũ) thay vì làm hỏng UI.
        """
        try:
            st = os.stat(src)
        except OSError:
            return src  # ảnh không có trên local (vd front chưa tải) → để Gradio tự xử
        key = f"{src}|{int(st.st_mtime)}|{st.st_size}"
        cached = self._thumb_cache.get(key)
        if cached and os.path.exists(cached):
            return cached
        try:
            from PIL import Image

            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX))
                out = self._thumb_dir / f"{abs(hash(key))}.jpg"
                im.save(out, "JPEG", quality=85)
            self._thumb_cache[key] = str(out)
            return str(out)
        except Exception:
            return src

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
        """
        Ghi đè toàn bộ file JSONL, GHI THẲNG TẠI CHỖ (in-place).

        KHÔNG dùng temp-file + os.replace: trên Google Drive (Colab drive.mount)
        FUSE không hỗ trợ rename/replace atomic của POSIX → mỗi lần replace bị
        Drive coi là "xóa + tạo file mới", sinh ra hàng loạt bản sao xung đột
        (front_draft (1).jsonl, ...) và file .tmp kẹt lại.

        Thay vào đó: serialize TOÀN BỘ record ra string trong RAM trước (nếu
        json lỗi thì văng ở đây, file gốc còn nguyên), rồi mới mở file gốc và
        ghi một lần. fsync để đẩy dữ liệu xuống Drive ngay.
        """
        payload = "".join(
            json.dumps(rec, ensure_ascii=False) + "\n" for rec in self.records
        )
        with open(self.jsonl_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

    def count(self) -> int:
        """Số record."""
        return len(self.records)

    def num_reviewed(self) -> int:
        """Số record đã được người duyệt đánh dấu reviewed."""
        return sum(1 for r in self.records if r.get("_meta", {}).get("reviewed"))

    def needs_review(self, idx: int) -> bool:
        """Record CHƯA được duyệt (reviewed != True) → vẫn cần xử lý."""
        return not self.records[idx].get("_meta", {}).get("reviewed", False)

    def next_needing(self, idx: int, step: int = 1) -> Optional[int]:
        """
        Tìm record CHƯA duyệt kế tiếp theo hướng `step` (+1 tới / -1 lùi), có
        WRAP vòng quanh để gom nốt ca bỏ sót. Trả None nếu đã duyệt hết.

        Truyền idx = -1, step = +1 để lấy ca chưa duyệt ĐẦU TIÊN (kiểm từ 0).
        """
        n = self.count()
        if n == 0:
            return None
        j = idx
        for _ in range(n):
            j = (j + step) % n
            if self.needs_review(j):
                return j
        return None

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
        # Tương thích ngược: nếu trường mới rỗng nhưng record cũ có key cũ.
        for new_key, old_key in FIELD_ALIASES.items():
            if not fields.get(new_key) and parsed.get(old_key) is not None:
                fields[new_key] = _to_str(parsed.get(old_key))

        img_abs = self._thumbnail(self._resolve_image(rec["image"]))

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
                only_todo = gr.Checkbox(
                    label="🔎 Chỉ duyệt ca CHƯA duyệt (Prev/Skip nhảy trong nhóm chưa duyệt)",
                    value=False,
                )
                with gr.Row():
                    jump_box = gr.Textbox(
                        label="Jump to index",
                        placeholder="Số thứ tự ảnh (1-based), vd: 17 → ảnh thứ 17",
                        scale=3,
                    )
                    jump_btn = gr.Button("🔎 Jump to index", scale=1)

        def render(idx: int, note: str = "") -> list:
            """Đổ dữ liệu record idx ra UI. `note` chèn vào đầu dòng trạng thái."""
            img, fields, status = store.get_fields(idx)
            if note:
                status = f"{note} | {status}"
            return [img, status, idx] + [fields[k] for k in ALL_FIELDS]

        def on_save(idx: int, *values: str) -> list:
            """Ghi đè record hiện tại rồi NHẢY tới ca CHƯA duyệt kế tiếp."""
            edited = dict(zip(ALL_FIELDS, values))
            store.update_record(idx, edited)
            store.save_all()
            nxt = store.next_needing(idx, +1)
            if nxt is None:
                return render(idx, "🎉 Đã duyệt hết toàn bộ")
            return render(nxt)

        def on_nav(idx: int, only_needs: bool, step: int) -> list:
            """
            Điều hướng prev/next không lưu.

            - only_needs=False: dịch ±1 theo vị trí (clamp trong [0, n-1]).
            - only_needs=True : nhảy tới ca CHƯA duyệt gần nhất theo hướng đó.
            """
            if only_needs:
                nxt = store.next_needing(idx, step)
                if nxt is None:
                    return render(idx, "🎉 Không còn ca chưa duyệt")
                return render(nxt)
            new_idx = max(0, min(idx + step, store.count() - 1))
            return render(new_idx)

        def on_jump(idx: int, query: str) -> list:
            """Nhảy tới ảnh theo SỐ THỨ TỰ người dùng gõ (1-based, vd '17')."""
            target = store.goto(query)
            if target is None:
                return render(idx, f"⚠️ Index '{query}' ngoài phạm vi 1..{store.count()}")
            name = Path(store.records[target].get("image", "")).name
            return render(target, f"➡️ Đã tới ảnh #{target + 1} ({name})")

        def on_toggle_filter(idx: int, only_needs: bool) -> list:
            """Bật lọc khi đang đứng ở ca đã duyệt → nhảy ngay tới ca chưa duyệt kế."""
            if only_needs and not store.needs_review(idx):
                nxt = store.next_needing(idx, +1)
                if nxt is not None:
                    return render(nxt)
                return render(idx, "🎉 Đã duyệt hết toàn bộ")
            return render(idx)

        outputs = [image_view, status_box, idx_state] + [field_boxes[k] for k in ALL_FIELDS]

        save_btn.click(
            on_save,
            inputs=[idx_state] + [field_boxes[k] for k in ALL_FIELDS],
            outputs=outputs,
        )
        prev_btn.click(lambda i, f: on_nav(i, f, -1), inputs=[idx_state, only_todo], outputs=outputs)
        next_btn.click(lambda i, f: on_nav(i, f, +1), inputs=[idx_state, only_todo], outputs=outputs)
        jump_btn.click(on_jump, inputs=[idx_state, jump_box], outputs=outputs)
        jump_box.submit(on_jump, inputs=[idx_state, jump_box], outputs=outputs)
        only_todo.change(on_toggle_filter, inputs=[idx_state, only_todo], outputs=outputs)

        # Mở đầu ở ca CHƯA duyệt đầu tiên (tiện resume giữa chừng), không có thì về 0.
        def _initial() -> list:
            start = store.next_needing(-1, +1)
            return render(start if start is not None else 0)

        demo.load(_initial, inputs=None, outputs=outputs)

    return demo


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Gradio CCCD label reviewer")
    parser.add_argument("--jsonl", required=True, help="File draft JSONL cần duyệt")
    parser.add_argument(
        "--image_root", default=".",
        help="Thư mục gốc để resolve trường 'image' trong JSONL (default: .)",
    )
    parser.add_argument(
        "--front_dir", default="data/Front",
        help="Thư mục ảnh MẶT TRƯỚC trên máy local (default: data/Front)",
    )
    parser.add_argument(
        "--back_dir", default="data/Back",
        help="Thư mục ảnh MẶT SAU trên máy local (default: data/Back)",
    )
    parser.add_argument("--share", action="store_true", help="Tạo link public (Colab)")
    parser.add_argument(
        "--server_port", type=int, default=None,
        help="Port cố định. Mặc định None → Gradio tự dò port trống (7860+).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point CLI."""
    args = parse_args()
    store = LabelStore(
        Path(args.jsonl),
        Path(args.image_root),
        front_dir=Path(args.front_dir),
        back_dir=Path(args.back_dir),
    )
    demo = build_ui(store)
    # allowed_paths: cho Gradio phục vụ ảnh nằm ngoài cwd (data/Front, data/Back).
    allowed = [
        str(Path(args.image_root).resolve()),
        str(Path(args.front_dir).resolve()),
        str(Path(args.back_dir).resolve()),
    ]
    demo.launch(
        share=args.share, server_port=args.server_port, allowed_paths=allowed
    )


if __name__ == "__main__":
    main()
