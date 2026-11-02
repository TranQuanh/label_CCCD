<<<<<<< HEAD
import 'dart:io';

import '../../core/config/api_config.dart';
import '../api/api_exception.dart';
=======
import 'package:flutter/foundation.dart';

import '../../core/config/api_config.dart';
>>>>>>> 8593503 (add data)
import '../api/cccd_api_client.dart';
import '../models/id_card.dart';
import '../validation/card_rules.dart';

<<<<<<< HEAD
/// Kết quả trích xuất từ 2 mặt thẻ.
class ExtractionResult {
  final IdCardData card;

  /// Trường cần người kiểm tra lại. **Không** phải điểm tin cậy của model —
  /// backend không sinh confidence — mà là kết quả `CardRules` (xem file đó).
  final List<String> needsReview;

  final List<FieldIssue> issues;
  final Duration elapsed;
  final bool fromMock;
=======
/// Bảng ánh xạ key từ JSON snake_case (Backend InternVL) sang camelCase (IdCardData)
const Map<String, String> frontKeyMap = {
  'so_cccd': 'idNumber',
  'so_cmnd': 'idNumber',
  'id': 'idNumber',
  'ho_va_ten': 'fullName',
  'ho_ten': 'fullName',
  'name': 'fullName',
  'ngay_sinh': 'dob',
  'date_of_birth': 'dob',
  'gioi_tinh': 'sex',
  'sex': 'sex',
  'quoc_tich': 'nationality',
  'nationality': 'nationality',
  'que_quan': 'origin',
  'noi_tru_quan': 'origin',
  'noi_thuong_tru': 'residence',
  'noi_dk_hktt': 'residence',
  'co_gia_tri_den': 'expiry',
  'ngay_het_han': 'expiry',
};

const Map<String, String> backKeyMap = {
  'dac_diem_nhan_dang': 'features',
  'ngay_cap': 'issueDate',
  'noi_cap': 'issuePlace',
  'co_quan_cap': 'issuePlace',
};

/// Kết quả trích xuất 2 mặt thẻ, đã được kiểm tra bằng [CardRules].
class ExtractionResult {
  final IdCardData card;

  /// Danh sách key-camelCase của các trường có vấn đề — hiển thị cảnh báo
  /// trên màn hình đối chiếu (một phần của `_issues`, đã gộp tất cả blocks).
  final List<String> needsReview;
  final List<FieldIssue> issues;
>>>>>>> 8593503 (add data)

  const ExtractionResult({
    required this.card,
    required this.needsReview,
    required this.issues,
<<<<<<< HEAD
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
=======
  });
}

/// Nguồn dữ liệu trích xuất cho luồng e-KYC.
///
/// - Chế độ **mock** (`ApiConfig.useMock`): trả thẻ mẫu, không gọi mạng — để
///   demo luồng trên emulator/thiết bị không có backend.
/// - Chế độ **thật**: gọi [CccdApiClient] cho từng mặt (front/sau), merge kết
///   quả rồi chạy [CardRules] để sinh cờ "cần kiểm tra".
class ExtractionRepository {
  final CccdApiClient _api;

  ExtractionRepository({CccdApiClient? api})
      : _api = api ?? CccdApiClient();

  /// Trích xuất dữ liệu từ 2 ảnh thẻ. Một trong hai ảnh có thể null (chỉ chụp
  /// 1 mặt), trường tương ứng sẽ bỏ trống.
  Future<ExtractionResult> extract({
    required String? frontPath,
    required String? backPath,
  }) async {
    final card = ApiConfig.useMock
        ? _mockCard()
        : await _extractFromApi(frontPath, backPath);

    final issues = <FieldIssue>[];
    final needsReview = <String>[];
    CardRules.byField(card).forEach((key, list) {
      if (list.isNotEmpty) {
        needsReview.add(key);
        issues.addAll(list);
      }
    });

    return ExtractionResult(
      card: card,
      needsReview: needsReview,
      issues: issues,
    );
  }

  void dispose() => _api.dispose();

  Future<IdCardData> _extractFromApi(String? frontPath, String? backPath) async {
    final card = IdCardData();

    if (frontPath != null) {
      final res = await _api.extract(frontPath, ApiConfig.sideFront);
      // In log dữ liệu thô mặt trước để debug nếu cần
      debugPrint('👉 RAW FRONT RESPONSE: ${res.data}');
      _mergeInto(card, res.data, frontKeyMap);
    }
    if (backPath != null) {
      final res = await _api.extract(backPath, ApiConfig.sideBack);
      debugPrint('👉 RAW BACK RESPONSE: ${res.data}');
      _mergeInto(card, res.data, backKeyMap);
    }
    return card;
  }

  /// Ghép kết quả một mặt (map snake_case từ backend) vào [card] (camelCase).
  static void _mergeInto(
    IdCardData card,
    Map<String, dynamic>? data,
    Map<String, String> keyMap,
  ) {
    if (data == null) return;
    final camel = <String, String>{};
    for (final e in data.entries) {
      final mapped = keyMap[e.key] ?? e.key;
      final v = e.value;
      camel[mapped] = v == null ? '' : v.toString().trim();
    }
    card.applyMap(camel);
  }

  /// Thẻ mẫu cho chế độ mock — không gọi mạng, phản ánh đúng dữ liệu CCCD thật
  /// (12 chữ số + mã tỉnh 001, hạn thẻ đúng sinh nhật tuổi 30→ trống được phép).
  IdCardData _mockCard() => IdCardData(
        fullName: 'NGUYỄN VĂN A',
        idNumber: '001201123456',
        dob: '01/01/1990',
        sex: 'Nam',
        nationality: 'Việt Nam',
        origin: 'Xã A, Huyện B, TP. Hà Nội',
        residence: 'Số 1, Đường ABC, Phường X, Quận Y, TP. Hà Nội',
        issueDate: '01/01/2016',
        expiry: '01/01/2030',
        issuePlace: 'Cục Cảnh sát quản lý hành chính về trật tự xã hội',
        features: 'Không có',
      );
}
>>>>>>> 8593503 (add data)
