/// Cấu hình kết nối backend FastAPI (`backend/main.py`).
///
/// Đổi giá trị lúc chạy mà không phải sửa code:
///
///   flutter run --dart-define=USE_MOCK=false \
///               --dart-define=API_BASE_URL=http://192.168.1.10:8000
class ApiConfig {
  const ApiConfig._();

  /// `true` → dùng dữ liệu mẫu, không gọi mạng (demo / chạy không có GPU server).
  static const bool useMock =
      bool.fromEnvironment('USE_MOCK', defaultValue: true);

  /// Mặc định `10.0.2.2` = localhost của máy host nhìn từ Android emulator.
  /// Máy thật: đổi sang IP LAN của máy chạy uvicorn.
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Endpoint thật của backend — KHÔNG phải `/extract-id`.
  /// Xem `backend/main.py`: `@app.post("/extract-cccd/")`.
  static const String extractPath = '/extract-cccd/';
  static const String healthPath = '/health';

  /// Tên field multipart mà FastAPI mong đợi: `file: UploadFile = File(...)`.
  static const String fileField = 'file';

  /// Giá trị hợp lệ của query `?side=` — khớp `CardSide` trong
  /// `model/src/utils/cccd_schema.py` (`FRONT = "truoc"`, `BACK = "sau"`).
  static const String sideFront = 'truoc';
  static const String sideBack = 'sau';

  /// Đo được trên tập test: p50 11–20 s/ảnh ở batch=1, adapter chưa merge.
  /// Timeout phải rộng hơn hẳn p95 (≈21.7 s) cộng thời gian upload ảnh.
  static const Duration requestTimeout = Duration(seconds: 90);

  /// Số lần thử lại khi lỗi mạng tạm thời (không retry lỗi 4xx).
  static const int maxRetries = 2;
  static const Duration retryBackoff = Duration(seconds: 2);
}
