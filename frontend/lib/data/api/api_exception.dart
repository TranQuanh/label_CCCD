/// Lỗi gọi API đã diễn giải sẵn thành thông điệp cho người dùng.
///
/// Backend trả lỗi kèm HTTP 200 (body `{"error": "..."}`), nên ngoài lỗi mạng
/// còn phải phân biệt lỗi nghiệp vụ từ chính body trả về.
class ApiException implements Exception {
  final String userMessage;
  final int? statusCode;

  const ApiException(this.userMessage, {this.statusCode});

  @override
  String toString() => userMessage;
}