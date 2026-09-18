# CCCD VLM Extraction

Trích xuất thông tin thẻ **Căn cước công dân (CCCD)** tiếng Việt bằng
Vision-Language Model fine-tune **QLoRA 4-bit**, kèm ứng dụng di động e-KYC.
Chạy được trên một GPU nhỏ (Colab T4 15GB / L4 24GB).

## Ba phần

| Thư mục | Vai trò | Ngôn ngữ |
|---|---|---|
| [`frontend/`](frontend/) | App Flutter: đăng nhập (JWT) + quét 2 mặt thẻ → đối chiếu → xuất biểu mẫu PDF + quản trị người dùng (admin) | Dart |
| [`backend/`](backend/) | Service FastAPI: **API `/api/v1/*` (auth + RBAC + audit) + serving `/extract-cccd/*`** (model 4-bit + adapter) | Python |
| [`model/`](model/) | Pipeline ML: gán nhãn → huấn luyện → đánh giá → so sánh kiến trúc | Python |

Thư mục phụ: [`docs/`](docs/) (kiến trúc, kế hoạch so sánh, changelog, phân tích
kết quả), `data/` · `checkpoints/` · `result_*/` (dữ liệu và artifact, không commit).

Ở gốc còn ba thư mục **shim** — `src/`, `app/`, `scripts/` — không chứa mã nguồn,
chỉ trỏ về vị trí thật để mọi lệnh và notebook Colab cũ vẫn chạy nguyên vẹn.
Sửa code ở `model/` và `backend/`, đừng sửa shim.

```
frontend/  lib/{core,data,features}/     ← app Flutter
backend/   main.py                       ← FastAPI (shim: app/)
model/     src/  scripts/  notebooks/    ← pipeline ML (shim: src/, scripts/)
docs/      ARCHITECTURE · CHANGELOG · VLM_COMPARISON_PLAN · Discussion
```

## Vòng đời ML — 4 giai đoạn

| # | Giai đoạn | Notebook | Module chính |
|---|-----------|----------|--------------|
| 1 | Gán nhãn (human-in-the-loop) | `model/notebooks/01_data_labeling.ipynb` | `model/src/data_pipeline/{auto_label,label_tool}.py` |
| 2 | Fine-tune QLoRA | `model/notebooks/02_finetuning.ipynb` | `model/src/data_pipeline/prepare_dataset.py`, `model/src/models/lora_setup.py`, `model/scripts/train.py` |
| 3 | Đánh giá (FA/CER/F1) | `model/notebooks/03_evaluation.ipynb` | `model/src/utils/metrics.py`, `model/scripts/evaluate.py` |
| 4 | Triển khai API | `model/notebooks/04_deployment.ipynb` | `backend/main.py` |
| 5 | So sánh kiến trúc | `model/notebooks/05_model_comparison.ipynb` | `model/scripts/compare_models.py` |

## Cài đặt

```bash
pip install -r requirements.txt
```

> `bitsandbytes` (4-bit) chỉ chạy trên **Linux / Colab / WSL**, không hỗ trợ
> Windows native.

## Khởi động dự án

### 1. Chuẩn bị môi trường Android Emulator
Có một số cách để có được Android Emulator (AVD):

**A. Dùng Android Studio (đơn giản nhất)**
1. Tải và cài Android Studio từ https://developer.android.com/studio.
2. Mở Android Studio → **More Actions** → **Virtual Device Manager** (hoặc qua menu **Tools > AVD Manager**).
3. Nhấn **Create Virtual Device**, chọn loại thiết bị (Phone/Tablet), chọn hệ thống ảnh (ví dụ: Android 13.0 (Google Play) x86_64), sau đó **Finish**.
4. Trong AVD Manager, chọn thiết bị vừa tạo và nhấn ▶️ **Play** để khởi động.

**B. Chỉ cài Android SDK Command‑line tools (nhẹ hơn)**
1. Tải "Command line tools only" từ trang Android Developer và giải nén vào một thư mục, ví dụ `C:\Android\cmdline-tools`.
2. Thêm thư mục `cmdline-tools\bin` vào PATH để có thể chạy `sdkmanager` và `avdmanager`.
3. Cài đặt hệ thống ảnh cần thiết:
   ```bash
   sdkmanager "platforms;android-33" "system-images;android-33;google_apis;x86_64" "emulator"
   ```
4. Tạo AVD:
   ```bash
   avdmanager create avd -n CCCD_x64_D -k "system-images;android-33;google_apis;x86_64"
   ```
5. Khởi động emulator:
   ```bash
   emulator -avd CCCD_x64_D -no-snapshot -gpu angle_indirect -no-boot-anim -camera-back webcam0
   ```

**C. Sử dụng thiết bị Android thực**
- Kết nối điện thoại qua USB, bật **USB debugging** trong Settings → Developer options.
- Thiết bị sẽ xuất hiện trong `flutter devices` và có thể chạy app trực tiếp.

Sau khi emulator hoặc thiết bị thực đang chạy, bạn có thể lấy ID thiết bị bằng lệnh `flutter devices` và dùng trong bước chạy frontend.

### 2. Chạy model trên Google Colab (tùy chọn)
- Mở notebook Colab đã được chuẩn bị (ví dụ: `model/notebooks/deployment.ipynb`) và chạy tất cả các module để khởi động server mô hình tại URL công cộng (ví dụ qua `ngrok` hoặc Colab's own tunnel).
- Lưu ý URL công khai mà backend sẽ gọi đến (ví dụ: `https://xxxxxx.ngrok.io`).

### 3. Chạy backend
```bash
cd <path-to-project-root>
# Thiết lập biến môi trường (ví dụ)
$env:MODEL_KEY="internvl"
$env:BASE_MODEL="OpenGVLab/InternVL3_5-2B-HF"
$env:SKIP_MODEL_LOAD=0
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/cccd"
$env:REDIS_URL="redis://localhost:6379/0"
$env:JWT_SECRET="dev-secret"
$env:PYTHONIOENCODING="utf-8"

uvicorn backend.main:app --port 8000
```
> Lưu ý: Thay đổi các giá trị biến môi trường cho phù hợp với môi trường của bạn (Cơ sở dữ liệu, Redis, v.v.).

### 4. Chạy frontend
```bash
cd <path-to-project-root>\frontend
# Liệt kê thiết bị có sẵn
flutter devices
# Chạy app trên thiết bị emulator (thay <device-id> bằng ID thiết bị như emulator-5556)
flutter run -d <device-id> --dart-define=USE_MOCK=false --dart-define=API_BASE_URL=http://10.0.2.2:8000
```
> Nếu chạy trên emulator Android, IP `10.0.2.2` là địa chỉ aliases của máy host. Nếu backend chạy trên máy khác, thay `10.0.2.2` bằng IP máy host trong LAN.

> **Lưu ý:** Nếu bạn chưa có AVD, hãy tạo nó qua Android AVD Manager trước.

## Điểm thiết kế nổi bật

- **Một nguồn chân lý cho prompt & schema**: `model/src/utils/cccd_schema.py` —
  prompt và danh sách trường phải giống hệt nhau ở lúc gán nhãn, huấn luyện,
  đánh giá và phục vụ.
- **Một nguồn chân lý cho cấu hình đa model**: `model/src/models/vlm_registry.py` —
  tách rõ cái phải **giống nhau** giữa các kiến trúc (LoRA target, ảnh 1024px)
  khỏi cái **bị kiến trúc ép** (max_length, processor kwargs).
- **Xác thực + RBAC thật**: backend `/api/v1/*` (JWT + refresh token, bcrypt,
  lockout, thu hồi token khi đổi quyền, audit log append-only) — xem
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) cho 11 quyết định chốt các mâu
  thuẫn giữa các tài liệu yêu cầu.
- **Vừa một GPU nhỏ**: NF4 + double-quant, đóng băng vision tower, LoRA chỉ trên
  language model; InternVL3.5-2B chạy hết 2.6 GB VRAM.
- **Mọi artifact lưu Google Drive** → Colab ngắt không mất tiến độ.

## Hai điều cần biết trước khi đọc số liệu

- **Split hiện tại chia theo *ảnh*, không theo *thẻ*.** `prepare_dataset.group_key`
  trả về tên file, trong khi 1436 ảnh mặt trước chỉ thuộc 689 thẻ khác nhau ⇒
  77,1% ảnh test có ảnh khác của cùng số CCCD nằm trong tập train. Field Accuracy
  mặt trước vì thế là **ước lượng lạc quan**. Chi tiết và cách khắc phục:
  [docs/Discussion.md](docs/Discussion.md).
- **Nhãn có nhiễu đo được**: 46,3% nhóm ảnh cùng một tấm thẻ được gán nhãn khác
  nhau; phần lỗi còn lại của model tập trung đúng vào những ô đó.

> Khi tài liệu trong `docs/` mâu thuẫn với code, **tin code** — xem mục
> "Docs vs. code drift" trong [CLAUDE.md](CLAUDE.md).
