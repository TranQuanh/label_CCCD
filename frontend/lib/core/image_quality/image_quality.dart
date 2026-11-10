/// Mô hình cảnh báo chất lượng ảnh CCCD + ngưỡng mặc định.
///
/// Cảnh báo CHỈ để người dùng cân nhắc chụp lại — KHÔNG bao giờ chặn bước
/// tiếp theo. Cùng `code` giữa app (`image_quality_analyzer.dart`) và backend
/// (`backend/image_quality.py`) để màn xem lại gộp trùng (server ghi đè).
library;

/// Mức độ cảnh báo: [warning] = nên để ý, [severe] = nên chụp lại.
enum QualitySeverity { warning, severe }

/// Một cảnh báo chất lượng ảnh.
class QualityIssue {
  /// Mã ổn định (vd `too_dark`, `blurry`, `card_tilted`) — dùng để gộp trùng.
  final String code;
  final QualitySeverity severity;

  /// Thông điệp tiếng Việt kèm gợi ý cách khắc phục.
  final String message;

  const QualityIssue({
    required this.code,
    required this.severity,
    required this.message,
  });

  /// Đọc từ kết quả `/api/v1/quality-check` (`{code, severity, message}`).
  /// Trả null nếu thiếu `code`/`message`; severity lạ → [QualitySeverity.warning].
  static QualityIssue? fromJson(Object? json) {
    if (json is! Map) return null;
    final code = json['code']?.toString() ?? '';
    final message = json['message']?.toString() ?? '';
    if (code.isEmpty || message.isEmpty) return null;
    // Bỏ qua severity 'info' (vd card_not_found trên emulator/ảnh thật không
    // cần thẻ trên nền tương phản).
    final severityStr = json['severity']?.toString();
    if (severityStr == 'info') return null;
    return QualityIssue(
      code: code,
      severity: severityStr == 'severe'
          ? QualitySeverity.severe
          : QualitySeverity.warning,
      message: message,
    );
  }
}

/// Ngưỡng mặc định cho phân tích trên app — gom một chỗ để chỉnh sau.
///
/// Các số đo tính trên ảnh xám đã thu nhỏ cạnh dài về [analysisLongSide] px
/// (riêng độ phân giải tính trên kích thước gốc). Thang độ sáng 0–255.
abstract final class QualityThresholds {
  /// Cạnh dài của ảnh sau khi thu nhỏ để phân tích.
  static const int analysisLongSide = 512;

  /// Độ sáng trung bình: dưới mức này là tối.
  static const double darkWarning = 60;
  static const double darkSevere = 35;

  /// Độ sáng trung bình: trên mức này là quá sáng.
  static const double brightWarning = 210;

  /// Pixel có độ sáng > [glarePixel] được tính là chói / lóa.
  static const int glarePixel = 245;
  static const double glareRatioWarning = 0.08;
  static const double glareRatioSevere = 0.20;

  /// Pixel có độ sáng < [darkPixel] được tính là quá tối; tỉ lệ pixel tối vượt
  /// [darkRatioWarning] cũng cảnh báo `too_dark` (mức warning) dù trung bình
  /// chưa thấp (vd thẻ nằm trong vùng tối, nền sáng).
  static const int darkPixel = 20;
  static const double darkRatioWarning = 0.5;

  /// Phương sai Laplacian 3x3 (ảnh 512px): thấp = nhòe.
  static const double blurWarning = 80;
  static const double blurSevere = 35;

  /// Cạnh ngắn của ảnh GỐC (px): nhỏ = độ phân giải thấp.
  static const int resolutionWarning = 600;
  static const int resolutionSevere = 400;

  /// Nhiễu: trung vị |ảnh − ảnh làm mờ 3x3| (thang 0–255). Chỉ warning vì
  /// hoa văn nền thẻ dễ bị đo nhầm thành nhiễu.
  static const double noiseWarning = 6;
}
