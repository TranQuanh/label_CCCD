enum ApiErrorKind {
  /// Không kết nối được (sai IP, server chưa bật, mất mạng).
  network,

  /// Quá thời gian chờ.
  timeout,

  /// Server trả mã lỗi HTTP.
  server,

  /// Server trả 200 nhưng thân phản hồi không dùng được.
  badResponse,

  /// Server từ chối có lý do rõ ràng (vd: chưa có adapter cho mặt này).
  rejected,
}

class ApiException implements Exception {
  final ApiErrorKind kind;
  final String message;
  final int? statusCode;

  const ApiException(this.kind, this.message, {this.statusCode});

  /// Có nên thử lại không — lỗi 4xx và lỗi bị từ chối thì thử lại vô ích.
  bool get retryable =>
      kind == ApiErrorKind.network ||
      kind == ApiErrorKind.timeout ||
      (kind == ApiErrorKind.server && (statusCode ?? 500) >= 500);

  /// Thông điệp hiển thị cho người dùng, kèm gợi ý xử lý.
  String get userMessage {
    switch (kind) {
      case ApiErrorKind.network:
        return 'Không kết nối được máy chủ trích xuất.\n'
            'Kiểm tra thiết bị có cùng mạng với server và địa chỉ API đã đúng chưa.';
      case ApiErrorKind.timeout:
        return 'Máy chủ xử lý quá lâu (quá ${_seconds}s).\n'
            'Mô hình VLM cần 11–20 giây mỗi ảnh; thử lại hoặc chụp ảnh nhẹ hơn.';
      case ApiErrorKind.server:
        return 'Máy chủ báo lỗi ${statusCode ?? ''}. $message';
      case ApiErrorKind.badResponse:
        return 'Máy chủ trả về dữ liệu không đọc được.\n$message';
      case ApiErrorKind.rejected:
        return message;
    }
  }

  static const _seconds = 90;

  @override
  String toString() => 'ApiException($kind, $message)';
}
