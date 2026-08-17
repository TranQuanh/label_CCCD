# Frontend — Định danh SmartID (Flutter)

Ứng dụng di động cho luồng e-KYC: quét 2 mặt CCCD → gửi ảnh cho backend VLM →
đối chiếu / bổ sung thông tin → xuất biểu mẫu PDF.

## Chạy lần đầu

Thư mục này **chỉ có `lib/` + `pubspec.yaml`**, chưa có scaffold platform, nên
`flutter run` sẽ báo lỗi ngay. Sinh scaffold trước:

```bash
cd frontend
flutter create .          # sinh android/ ios/ (giữ nguyên lib/ và pubspec.yaml)
flutter pub get
```

Sau đó khai quyền — `camera` và `image_picker` không tự thêm:

- `android/app/src/main/AndroidManifest.xml`

  ```xml
  <uses-permission android:name="android.permission.CAMERA"/>
  <uses-permission android:name="android.permission.INTERNET"/>
  ```

  và `minSdkVersion` ≥ 21 trong `android/app/build.gradle`.

- `ios/Runner/Info.plist`

  ```xml
  <key>NSCameraUsageDescription</key>
  <string>Ứng dụng cần camera để quét thẻ CCCD.</string>
  <key>NSPhotoLibraryUsageDescription</key>
  <string>Ứng dụng cần thư viện ảnh để chọn ảnh thẻ có sẵn.</string>
  ```

- Gọi HTTP **không mã hoá** tới máy chủ trong LAN thì Android 9+ chặn mặc định.
  Khi thử nghiệm, thêm `android:usesCleartextTraffic="true"` vào thẻ
  `<application>`; khi triển khai thật thì dùng HTTPS thay vì mở cleartext.

## Chạy với backend thật

Mặc định app chạy **chế độ mock** (dữ liệu mẫu, không gọi mạng). Bật kết nối thật:

```bash
# 1) bật API ở máy có GPU (xem README ở thư mục gốc)
MODEL_KEY=internvl CHECKPOINT_DIR=checkpoints uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 2) chạy app trỏ vào máy đó
flutter run --dart-define=USE_MOCK=false \
            --dart-define=API_BASE_URL=http://192.168.1.10:8000
```

- Android emulator: `API_BASE_URL=http://10.0.2.2:8000` (mặc định sẵn).
- Máy thật: dùng IP LAN, và uvicorn phải nghe `--host 0.0.0.0`.

## Cấu trúc

```
lib/
  main.dart                        điểm vào, theme, seed dữ liệu mock
  core/                            dùng chung, không phụ thuộc màn hình nào
    theme/app_theme.dart           AppColors, AppRadius, kCardAspect, buildAppTheme
    config/api_config.dart         base URL, endpoint, timeout, cờ USE_MOCK
    validation/validators.dart     kiểm tra mức chuỗi + giải mã cấu trúc số CCCD
    widgets/                       CustomTextField · SectionLabel · ScannerOverlay
  data/                            model, nguồn dữ liệu, quy tắc nghiệp vụ
    models/                        IdCardData · FormType · SubmittedRecord
    api/cccd_api_client.dart       HTTP tới POST /extract-cccd/
    api/api_exception.dart         phân loại lỗi + thông điệp cho người dùng
    repositories/extraction_repository.dart   điểm nối DUY NHẤT tới mô hình VLM
    session/session_store.dart     phiên đăng nhập + danh sách hồ sơ
    validation/card_rules.dart     quy tắc liên trường trên toàn thẻ
  features/                        mỗi thư mục là một bước trong luồng
    auth/      đăng nhập · đổi mật khẩu
    shell/     khung 3 tab
    forms/     danh mục biểu mẫu
    scan/      hướng dẫn → camera → đang trích xuất
    review/    đối chiếu & bổ sung
    output/    xem trước · gửi thành công · xuất PDF
    records/   hồ sơ đã tạo
    account/   tài khoản · đăng xuất
```

Quy ước phụ thuộc: `features → data → core`. `core` không được import `data`
hay `features`; `data` không được import `features`.

## Hợp đồng với backend

Chỉ có **một** nơi biết hình dạng API là [lib/data/api/cccd_api_client.dart](lib/data/api/cccd_api_client.dart),
và **một** nơi biết ánh xạ tên trường là `frontKeyMap` / `backKeyMap` trong
[lib/data/models/id_card.dart](lib/data/models/id_card.dart).

```
POST {base}/extract-cccd/?side=truoc     multipart, field tên `file`
POST {base}/extract-cccd/?side=sau

→ {"filename","side","parse_ok","data":{"so_cccd","ho_va_ten",...},"raw",...}
→ {"filename","error":"..."}             ← lỗi cũng trả HTTP 200
```

Bốn điểm bắt buộc phải giữ, mỗi điểm đều từng là một lỗi thật:

1. **Luôn gửi `side` tường minh.** `side=auto` khiến backend suy mặt thẻ từ *tên file*;
   ảnh camera có tên `CAP1234.jpg` nên sẽ ra `unknown` và bị từ chối.
2. **Giải mã UTF-8 thủ công** (`utf8.decode(res.bodyBytes)`). FastAPI không gửi
   charset, `http` mặc định latin1 và làm hỏng toàn bộ dấu tiếng Việt.
3. **Lỗi trả về kèm HTTP 200** — phải kiểm `body['error']` và `parse_ok`, không
   chỉ kiểm `statusCode`.
4. **Backend không trả điểm tin cậy.** Cờ "cần kiểm tra" trong app đến từ
   [card_rules.dart](lib/data/validation/card_rules.dart) — kiểm tra ràng buộc
   nghiệp vụ — chứ không phải confidence của model.

## Còn thiếu trước khi dùng thật

- **Xác thực**: form đăng nhập hiện chỉ kiểm tra cục bộ, không có token/phiên server.
- **OTP**: mã cố định `123456`, so sánh trên máy, còn in ra màn hình.
- **Lưu trữ**: hồ sơ chỉ nằm trong RAM, đóng app là mất. `SubmittedRecord` và
  `IdCardData` đã có `toJson`/`fromJson` nên chỉ cần thêm một lớp persistence.
- **Mã hồ sơ**: `SubmittedRecord.newCode()` chỉ là mã tạm phía client; mã thật
  phải do backend cấp lúc tiếp nhận.
- **Phông PDF**: `PdfGoogleFonts` tải Roboto qua mạng lần đầu. Muốn chạy offline
  thì nhúng `.ttf` vào assets.
