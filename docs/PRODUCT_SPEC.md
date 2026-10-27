# Định danh SmartID — Đặc tả sản phẩm

> Đặc tả này mô tả **trạng thái code hiện tại** (chạy được, đã kiểm tra trên
> emulator Android), không phải thiết kế ý tưởng. Mọi màn hình, hợp đồng data và
> quy tắc dưới đây đều có thể đối chiếu trực tiếp với `frontend/lib/`.

## 1. Sản phẩm

Ứng dụng di động Flutter cho luồng **e-KYC**: người dùng chọn một biểu mẫu hành
chính, quét 2 mặt CCCD bằng camera, dữ liệu được trích xuất bằng mô hình VLM ở
backend, người dùng đối chiếu/bổ sung, rồi xem trước biểu mẫu hoàn chỉnh, xuất
PDF và lưu hồ sơ trên thiết bị.

Package: `smartid` (org `vn.smartid`), applicationId `vn.smartid.smartid`.

### Hai chế độ chạy

- **Mock** (`ApiConfig.useMock = true`, mặc định): không gọi mạng. Đăng nhập tự
  động vào tài khoản demo `nguyenvana`, `sessionStore` được seed 1 hồ sơ demo.
  Dùng để chạy demo / phát triển UI khi không có server.
- **Thật** (`--dart-define=USE_MOCK=false`): xác thực **thật** với backend qua
  `/api/v1/*` (JWT + refresh token trong Secure Storage). Quét thẻ gọi
  `CccdApiClient` tới `/extract-cccd/`; hồ sơ bắt đầu trống.

## 2. Kiến trúc (quy ước phụ thuộc)

```
features → data → core
```

- `core/` — dùng chung, **không** import `data` hay `features`:
  - `config/api_config.dart` — base URL, endpoint, timeout, cờ USE_MOCK.
  - `theme/app_theme.dart` — AppColors, AppRadius, `buildAppTheme`.
  - `validation/validators.dart` — kiểm tra mức chuỗi + giải mã cấu trúc số CCCD.
  - `widgets/` — `CustomTextField`, `SectionLabel`, `ScannerOverlay`.
- `data/` — model, nguồn dữ liệu, quy tắc nghiệp vụ, **không** import `features`:
  - `models/` — `IdCardData`, `FormType`/`SuppField`, `SubmittedRecord`, `AuthUser`.
  - `api/` — `CccdApiClient` + `AuthApiClient` (hai điểm duy nhất biết HTTP),
    `ApiClient` (wrapper auto-refresh 401), `TokenStore` (Secure Storage),
    `ApiException`.
  - `repositories/extraction_repository.dart` — điểm nối duy nhất tới VLM.
  - `session/session_store.dart` — phiên đăng nhập + danh sách hồ sơ.
  - `validation/card_rules.dart` — quy tắc liên trường trên toàn thẻ.
- `features/` — mỗi thư mục một bước trong luồng.

## 3. Luồng người dùng (theo màn hình)

| # | Màn hình | File | Chức năng |
|---|----------|------|-----------|
| 1 | Đăng nhập / Đăng ký | `features/auth/auth_screen.dart` | P1: xác thực **thật** với backend `/api/v1/auth/*` (JWT). Đăng nhập: một trường **email hoặc tên đăng nhập** (backend phân biệt qua `@`) + mật khẩu. Đăng ký: tên đăng nhập, họ tên, email, mật khẩu **≥8 ký tự có chữ và số** (khớp `backend/security.py`). Không còn `dob`. Hiển thị lỗi nghiệp vụ từ backend qua `ApiException.userMessage`. |
| 2 | Khung 3 tab | `features/shell/home_shell.dart` | Biểu mẫu · Hồ sơ · Tài khoản (IndexedStack). P2: operator/admin có thêm tab **Duyệt** (hàng đợi duyệt hồ sơ); viewer không thấy tab này. Lịch sử + hàng đợi được nạp lại mỗi khi chuyển tab. |
| 3 | Danh mục biểu mẫu | `features/forms/forms_tab.dart` | P2: danh mục lấy từ `GET /api/v1/forms` (chế độ thật), mỗi thẻ có màu + glyph + trường bổ sung `label/hint` do server cấp; mock vẫn dùng `kFormTypes`. Header chào theo `sessionStore.displayName`. |
| 4 | Hướng dẫn quét | `features/scan/onboarding_screen.dart` | 3 mẹo chụp + nút "Bắt đầu quét mặt trước". |
| 5 | Camera | `features/scan/camera_screen.dart` | Chụp mặt trước rồi mặt sau (camera plugin). Cho chọn ảnh từ thư viện (`image_picker`). Flash toggle. Ảnh lưu vào thư mục tạm. |
| 6 | Đang trích xuất | `features/scan/processing_screen.dart` | Gọi `ExtractionRepository.extract`. Lỗi → màn hình riêng với "Thử lại" (dùng ảnh cũ) và "Chụp lại". Timeout/retry nằm trong client. |
| 7 | Đối chiếu & bổ sung | `features/review/review_screen.dart` | 7 trường mặt trước + 4 trường mặt sau (edit được) + trường bổ sung theo biểu mẫu. Kiểm tra lại từng ký tự gõ bằng `CardRules`. |
| 8 | Xem trước biểu mẫu | `features/output/preview_screen.dart` | Biểu mẫu hoàn chỉnh + mã hồ sơ. P2: nút "Gửi hồ sơ" gọi `POST /api/v1/scan-records`, mã hồ sơ do **server cấp**. Chế độ đọc-only khi xem lại từ tab Hồ sơ / hàng đợi duyệt. Nút "Tải PDF". |
| 9 | Gửi thành công | `features/output/success_screen.dart` | Xác nhận + mã hồ sơ (server) + "Tải lại biểu mẫu PDF" + "Về trang chủ" (về tab Hồ sơ). |
| 10 | Hồ sơ của tôi | `features/records/records_tab.dart` | P2: lịch sử tải từ `GET /api/v1/scan-records` khi mở tab; chip **Chờ duyệt / Đã duyệt**; viewer thấy bản che số CCCD (banner). Tap → preview đọc-only. |
| 11 | Tài khoản | `features/account/account_tab.dart` | Thông tin `AuthUser` từ server (`/api/v1/auth/me`): tên đăng nhập, họ tên, email, **vai trò** (không còn `dob`) + thẻ từ hồ sơ gần nhất (nhãn rõ "chưa được xác thực") + Đổi mật khẩu + mục **Quản trị hệ thống** (chỉ `admin`) + Đăng xuất (thu hồi token qua API + xoá dữ liệu phiên). |
| 12 | Quản trị (admin) | `features/admin/admin_shell.dart`, `users_admin_tab.dart`, `audit_logs_admin_tab.dart` | 2 tab: **Người dùng** (`/api/v1/users` — đổi vai trò, khóa/mở khóa; tự hiển thị thông báo khi backend chặn hạ quyền self / admin cuối cùng) và **Nhật ký** (`/api/v1/audit-logs` — auth.register/login/logout, user.update, record.create/review, auth.change_password…). |
| 13 | Duyệt hồ sơ | `features/review/review_queue_tab.dart` | P2: operator/admin liệt kê hồ sơ `pending` từ `GET /scan-records/review-queue`; tap để xem nội dung đọc-only rồi **Duyệt** (gọi `PATCH /scan-records/{id}/review`). Sau khi duyệt, hồ sơ hiển thị trong lịch sử người dùng và bản che cho viewer. |
| 14 | Đổi mật khẩu | `features/auth/change_password_screen.dart` | P2: một bước — nhập mật khẩu hiện tại + mật khẩu mới (x2) → gọi `POST /api/v1/auth/change-password`. Không còn OTP demo. Kiểm tra cục bộ khớp ràng buộc backend (≥8 ký tự, chữ + số). |

## 4. Hợp đồng dữ liệu (single source of truth)

### 4.1 `IdCardData` (`data/models/id_card.dart`)

11 trường camelCase: `fullName, idNumber, dob, sex, nationality, origin,
residence, issueDate, expiry, issuePlace, features`.

- `displayOrder` — thứ tự + nhãn hiển thị (PDF & biểu mẫu).
- `frontKeyMap` / `backKeyMap` — **duy nhất** ánh xạ snake_case backend →
  camelCase app. **Phải đồng bộ với `FRONT_FIELDS`/`BACK_FIELDS` trong
  `model/src/utils/cccd_schema.py`.**

### 4.2 `FormType` / `SuppField` (`data/models/form_type.dart`)

P2: chế độ thật lấy từ `GET /api/v1/forms`; `kFormTypes` chỉ còn dùng cho **mock**.
Server trả `required_fields` dạng JSONB `[{key, label, hint}]`, `requires_front/back`,
`is_active`. Client map slug → màu/glyph (dùng cho hiển thị, không phải dữ liệu):

| id | Tiêu đề | Trường bổ sung |
|----|---------|----------------|
| `atm_open` | Đăng ký mở thẻ ATM | `phone` (Số điện thoại liên hệ), `occupation` (Nghề nghiệp hiện tại) |
| `health_declare` | Khai báo y tế | `phone`, `symptoms` (Triệu chứng nếu có) |
| `service_contract` | Hợp đồng dịch vụ | `phone`, `company` (Công ty / đơn vị) |

`formTypeById(id)` fallback về biểu mẫu đầu tiên.

### 4.3 `SubmittedRecord` (`data/models/submitted_record.dart`)

Hồ sơ đã gửi: `code, formId, name, date, card, supp, reviewStatus, id`.
P2: **mã hồ sơ do SERVER cấp** (`POST /api/v1/scan-records` → `code` dạng
`HS<yyyyMMdd>-<6chữsố>`), lịch sử đọc từ PostgreSQL qua `GET /scan-records`
(`fromServer` parse `extracted_data` snake_case + `supp` + `review_status`).
`newCode()` chỉ còn dùng cho mock. Chip trạng thái: `pending` → "Chờ duyệt",
`reviewed` → "Đã duyệt".

### 4.4 `AuthUser` (`data/models/auth_user.dart`)

Thông tin tài khoản từ server: `id, username, fullName, email, role`
(`admin` / `operator` / `viewer`). **Không có `dob`** — bảng `tblUser` không có
cột này. `isAdmin` = `role == 'admin'`. `fromJson` map `user_id` → `id`.

### 4.5 `SessionStore` (`data/session/session_store.dart`)

`ChangeNotifier` singleton (`sessionStore`): `user` (`AuthUser`), `records`
(bất biến), `forms`, `reviewQueue`, `masked`, `latestCard`,
`displayName/email/role/initial`. Các phương thức đều **async**:

- `login({identifier, password})` — một trường nhận cả email lẫn tên đăng nhập;
  gọi `/api/v1/auth/login` (mock: vào tài khoản demo ngay).
- `register({username, email, password, fullName})` — gọi `/api/v1/auth/register`
  (backend tự đăng nhập phiên đầu).
- `logout()` — gọi `/api/v1/auth/logout` thu hồi refresh + blacklist access,
  **xoá token trong Secure Storage** + xoá toàn bộ hồ sơ/danh mục/hàng đợi trong RAM.
- `tryAutoLogin()` — chạy lúc mở app: có refresh token trong Secure Storage thì
  lấy access token mới qua `/auth/refresh` rồi gọi `/auth/me`; thất bại (token
  bị thu hồi) → xoá token, về màn hình Đăng nhập.
- `loadForms()` — nạp danh mục từ `GET /api/v1/forms` (real), fallback `kFormTypes`.
- `submitRecord({formType, card, supp})` — gọi `POST /scan-records`, trả hồ sơ có
  `code` **server cấp** (mock: mã tạm cục bộ).
- `loadRecords()` — tải lịch sử từ `GET /scan-records`.
- `changePassword({currentPassword, newPassword})` — gọi `/auth/change-password`.

`seedDemoRecords` chỉ chạy ở mock.

## 5. Quy tắc nghiệp vụ

### 5.1 `Validators` (`core/validation/validators.dart`) — mức chuỗi

Ràng buộc lấy từ chính miền dữ liệu CCCD (Thông tư 07/2016/TT-BCA):
- `cccd` — 12 chữ số, 3 số đầu = mã tỉnh 001–096.
- `parseDate` — DD/MM/YYYY, so lại từng thành phần sau `DateTime` (tránh 31/02).
- `sexFromIdNumber` — chữ số thứ 4 chẵn = Nam, lẻ = Nữ.
- `birthYearFromIdNumber` — chữ số thứ 4 (thế kỷ) + chữ số 5–6 (năm).
- `expiryMatchesBirthday` — hạn thẻ = đúng sinh nhật tuổi 25 / 40 / 60.
- `normalizeIdNumber`, `normalizeSex` (bỏ qua hoa/thường: model có thể trả `NAM`).

### 5.2 `CardRules` (`data/validation/card_rules.dart`) — mức toàn thẻ

Nguồn **duy nhất** của cờ "cần kiểm tra" (backend không trả confidence). Trả về
`Map<key-camelCase, List<FieldIssue>>`; `FieldIssue{blocks, message}`:

- `blocks == true` → phải sửa mới đi tiếp (Họ tên, Số CCCD, Ngày sinh, Giới tính
  trống/sai, Ngày cấp sai định dạng…).
- `blocks == false` → cảnh báo, có thể bỏ qua (giới tính không khớp số CCCD,
  quốc tịch khác "Việt Nam", hạn thẻ lệch sinh nhật, địa chỉ trống…).

**Được phép trống**: `origin`, `residence`, `issuePlace`, `features`,
`expiry` (thẻ cấp cho người ≥60 không có hạn — để trống là hợp lệ, không phải
thiếu dữ liệu). Màn hình đối chiếu tính lại mỗi lần người dùng gõ.

## 6. Hợp đồng với backend

Có **hai** lớp HTTP riêng biệt, mỗi lớp một nơi duy nhất biết đường dẫn:

### 6.1 Quét thẻ — `data/api/cccd_api_client.dart` (`/extract-cccd/*`)

Bốn điểm bắt buộc (mỗi điểm từng là một lỗi thật):

1. Luôn gửi `?side=truoc|sau` tường minh — `side=auto` suy từ tên file, ảnh
   camera tên `CAP*.jpg` ra `unknown` và bị từ chối.
2. Giải mã UTF-8 thủ công (`utf8.decode(res.bodyBytes)`) — FastAPI không gửi
   charset, `http` mặc định latin1 hỏng dấu tiếng Việt.
3. Lỗi trả về kèm HTTP 200 — phải kiểm `body['error']` và `parse_ok`, không chỉ
   `statusCode`.
4. Backend không trả confidence — cờ cảnh báo đến từ `CardRules`.

Cấu hình (`core/config/api_config.dart`): `POST {base}/extract-cccd/?side=...`,
field multipart tên `file`, timeout 90s (p50 11–20s, p95 ≈21.7s/ảnh), retry 2
lần với backoff 2s (không retry lỗi 4xx). `10.0.2.2:8000` = localhost host nhìn
từ Android emulator; máy thật đổi qua `--dart-define=API_BASE_URL`.

### 6.2 Xác thực, quản trị & hồ sơ — `data/api/auth_api_client.dart` (`/api/v1/*`)

P1+P2: đăng nhập/đăng ký/phiên + quản lý người dùng + nhật ký kiểm toán + danh
mục biểu mẫu + hồ sơ trích xuất + hàng đợi duyệt. Nằm dưới tiền tố `/api/v1`,
khác hẳn lớp quét thẻ `/extract-cccd/*` (endpoint nội bộ của luồng VLM).
Endpoint: `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`,
`/auth/me`, `/auth/change-password`, `/users`, `/users/{id}` (PUT),
`/audit-logs`, `/forms`, `/forms/{slug}` (POST/PUT admin), `/scan-records`
(POST submit, GET history, GET `/review-queue`), `/scan-records/{id}` (GET),
`/scan-records/{id}/review` (PATCH duyệt). Lỗi trả về theo chuẩn FastAPI:
HTTP 4xx/5xx + body `{"detail": "..."}` (hoặc `message`) — khác với quy ước
HTTP 200 ở lớp 6.1.

`AuthApiClient` đi qua `data/api/api_client.dart` — wrapper gắn `Bearer` và **tự
làm mới token**: gặp 401 → gọi `/auth/refresh` một lần bằng refresh token trong
Secure Storage → chơi lại request gốc; refresh thất bại → báo "Phiên đã hết hạn"
và yêu cầu đăng nhập lại. Token nằm trong Secure Storage (`TokenStore`), không
bao giờ lưu dưới dạng văn bản thường.

Khi admin đổi vai trò / khóa tài khoản, backend tăng `token_version` + thu hồi
mọi refresh token → lần tự đăng nhập kế tiếp thất bại, người đó phải đăng nhập
lại (đã kiểm tra trên emulator).

## 7. Xuất PDF (`features/output/pdf_service.dart`)

A4, `PdfGoogleFonts` Roboto (cần **mạng lần đầu**; offline → `PdfExportException`
với thông điệp rõ ràng). Bố cục: quốc hiệu → tiêu đề biểu mẫu → mã hồ sơ →
I. THÔNG TIN CÔNG DÂN (11 trường `displayOrder`) → II. THÔNG TIN BỔ SUNG →
ngày tháng + chữ ký + họ tên. Mở hộp thoại in/lưu hệ thống
(`Printing.layoutPdf`).

## 8. Kiểm tra trên thiết bị

Đã chạy thật trên **Android emulator** (Flutter 3.47.0, Android SDK 36 x86_64,
AVD `Medium_Phone_64`):

- **Mock** (`USE_MOCK=true`): luồng đầy đủ đăng nhập → chọn "Đăng ký mở thẻ ATM"
  → quét 2 mặt (camera plugin + permission dialog) → đối chiếu (11/11 trường ✓,
  2 trường bổ sung nhập tay) → xem trước (mã hồ sơ `HS20260818-…`) → gửi →
  SuccessScreen → tab Hồ sơ hiển thị 2 bản ghi (1 demo + 1 mới) → PreviewScreen
  đọc-only.
- **Thật** (`USE_MOCK=false`, backend lite `SKIP_MODEL_LOAD=1` + PostgreSQL +
  Redis): đăng ký user mới, đăng nhập bằng **email** và bằng **tên đăng nhập**,
  auto-login khi mở lại app (refresh token trong Secure Storage), tab Tài khoản
  hiển thị đúng vai trò từ server, đăng nhập bằng tài khoản `admin` thấy mục
  "Quản trị hệ thống" (danh sách người dùng + nhật ký audit), đổi vai trò qua
  SQL → phiên cũ bị vô hiệu phải đăng nhập lại, logout → token bị thu hồi và
  app về màn hình Đăng nhập. Backend log xác nhận chuỗi auto-refresh thật:
  `401 → POST /auth/refresh 200 → retry thành công`.
- **P2 trên emulator** (`USE_MOCK=false`): danh mục biểu mẫu hiển thị 4 biểu mẫu
  từ server (3 seed + 1 tạo qua `POST /forms` admin); gửi hồ sơ → mã server cấp
  `HS…`; tab Hồ sơ hiển thị hồ sơ mới với chip "Chờ duyệt"; tài khoản `admin`
  thấy tab **Duyệt**, duyệt hồ sơ → hàng đợi rỗng + hồ sơ đổi thành "Đã duyệt";
  tài khoản `viewer` thấy banner "dữ liệu đã được che" + **không** thấy tab Duyệt;
  màn hình Đổi mật khẩu một bước (không OTP) gọi API thật. Backend
  `smoke_test.py`: 72 PASS / 0 FAIL.

Kiểm tra code: `flutter analyze` (0 lỗi). Không có widget-test.

## 9. Giới hạn phạm vi (chưa có trước khi dùng thật)

- **Xác thực**: đã có token/phiên server thật (JWT + refresh). Còn thiếu: đăng ký
  chưa xác minh email (`EMAIL_VERIFICATION_ENABLED=false`), chưa có luồng quên
  mật khẩu.
- **Đổi mật khẩu**: đã gọi API thật, không còn OTP demo. Nhưng thu hồi toàn bộ
  refresh token → các phiên khác phải đăng nhập lại (đúng thiết kế).
- **Ảnh thẻ**: lưu thư mục tạm, chưa bị xoá chủ động sau trích xuất (docstring
  `camera_screen.dart` nói "bị xoá ngay" — hiện chỉ nằm trong bộ nhớ tạm của OS,
  vẫn còn cho tới khi app/OS dọn; cần dọn rõ ràng khi nối backend thật).
- **Hàng đợi duyệt**: chưa có bộ lọc theo form/mặt thẻ trên UI (API đã hỗ trợ
  `form_id`/`card_side`), chưa có khả năng "bỏ qua" riêng (chỉ Duyệt).
- **Dữ liệu thẻ trong tab Tài khoản** vẫn là hồ sơ gần nhất đã lưu, không phải
  danh tính xác thực từ server.
- **Phông PDF**: `PdfGoogleFonts` tải qua mạng lần đầu — offline cần nhúng `.ttf`.
