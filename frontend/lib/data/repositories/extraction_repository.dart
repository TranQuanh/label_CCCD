import 'dart:io';

import '../../core/config/api_config.dart';
import '../api/api_exception.dart';
import '../api/cccd_api_client.dart';
import '../models/id_card.dart';
import '../validation/card_rules.dart';

/// Kết quả trích xuất từ 2 mặt thẻ.
class ExtractionResult {
  final IdCardData card;

  /// Trường cần người kiểm tra lại. **Không** phải điểm tin cậy của model —
  /// backend không sinh confidence — mà là kết quả `CardRules` (xem file đó).
  final List<String> needsReview;

  final List<FieldIssue> issues;
  final Duration elapsed;
  final bool fromMock;

  const ExtractionResult({
    required this.card,
    required this.needsReview,
    required this.issues,
    required this.elapsed,
    required this.fromMock,
  });
}

/// Điểm nối DUY NHẤT giữa app và mô hình VLM.
///
/// Đổi giữa mock và server thật bằng `--dart-define=USE_MOCK=false`; không màn
/// hình nào biết mình đang chạy chế độ nào.
class ExtractionRepository {
  final CccdApiClient _client;
  final bool useMock;

  ExtractionRepository({CccdApiClient? client, bool? useMock})
      : _client = client ?? CccdApiClient(),
        useMock = useMock ?? ApiConfig.useMock;

  Future<ExtractionResult> extract({
    String? frontPath,
    String? backPath,
  }) async {
    final started = DateTime.now();

    if (useMock) {
      await Future<void>.delayed(const Duration(milliseconds: 1200));
      final card = IdCardData.sample();
      return _wrap(card, started, fromMock: true);
    }

    if (frontPath == null || backPath == null) {
      throw const ApiException(
        ApiErrorKind.badResponse,
        'Thiếu ảnh mặt trước hoặc mặt sau.',
      );
    }

    final front = File(frontPath);
    final back = File(backPath);
    if (!front.existsSync() || !back.existsSync()) {
      throw const ApiException(
        ApiErrorKind.badResponse,
        'Không tìm thấy ảnh vừa chụp trên thiết bị.',
      );
    }

    final card = IdCardData();
    // Chạy tuần tự chứ không song song: backend giữ GPU_LOCK nên hai request
    // đồng thời vẫn xếp hàng, mà lại tốn gấp đôi RAM giữ ảnh trong bộ nhớ.
    final frontData = await _client.extractSide(image: front, isFront: true);
    card.applyBackendData(frontData, isFront: true);

    final backData = await _client.extractSide(image: back, isFront: false);
    card.applyBackendData(backData, isFront: false);

    // Chuẩn hoá số CCCD về 12 chữ số liền như backend, tránh lệch khi in PDF.
    card.idNumber = card.idNumber.replaceAll(RegExp(r'\D'), '');

    _deleteQuietly(front);
    _deleteQuietly(back);

    return _wrap(card, started, fromMock: false);
  }

  ExtractionResult _wrap(IdCardData card, DateTime started,
      {required bool fromMock}) {
    final issues = CardRules.check(card);
    return ExtractionResult(
      card: card,
      needsReview: issues.map((e) => e.field).toSet().toList(),
      issues: issues,
      elapsed: DateTime.now().difference(started),
      fromMock: fromMock,
    );
  }

  /// Ảnh CCCD là dữ liệu cá nhân — xoá file tạm ngay khi không cần nữa.
  void _deleteQuietly(File f) {
    try {
      if (f.existsSync()) f.deleteSync();
    } catch (_) {
      // Không chặn luồng người dùng chỉ vì dọn file tạm thất bại.
    }
  }

  void dispose() => _client.close();
}
