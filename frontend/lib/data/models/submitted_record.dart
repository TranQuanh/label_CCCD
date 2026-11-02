import 'id_card.dart';

<<<<<<< HEAD
/// Một hồ sơ người dùng đã kê khai & gửi.
=======
/// Một hồ sơ đã gửi — bản ghi được tạo sau khi người dùng xác nhận biểu mẫu.
///
/// P1: chỉ lưu RAM (`sessionStore`). P2: mã hồ sơ do SERVER cấp (qua
/// `POST /api/v1/scan-records`), lịch sử đọc từ PostgreSQL (`GET /scan-records`).
>>>>>>> 8593503 (add data)
class SubmittedRecord {
  final String code;
  final String formId;
  final String name;
  final String date;
  final IdCardData card;
  final Map<String, String> supp;
<<<<<<< HEAD
=======
  final String? id;
>>>>>>> 8593503 (add data)

  const SubmittedRecord({
    required this.code,
    required this.formId,
    required this.name,
    required this.date,
    required this.card,
    required this.supp,
<<<<<<< HEAD
  });

  /// Mã hồ sơ: `#SID-<năm hiện tại>-<5 số>`.
  ///
  /// Bản cũ hardcode `2026` và lấy `millis % 89999` nên vừa sai năm vừa dễ trùng.
  /// Ở đây năm lấy từ đồng hồ máy và phần số gắn với micro-giây + số thứ tự trong
  /// phiên. Đây vẫn chỉ là mã **tạm** phía client: mã hồ sơ thật phải do backend
  /// cấp khi tiếp nhận, nếu không hai máy vẫn có thể sinh trùng.
  static int _seq = 0;

  static String newCode([DateTime? now]) {
    final t = now ?? DateTime.now();
    _seq = (_seq + 1) % 1000;
    final n = (t.microsecondsSinceEpoch ~/ 1000 + _seq) % 100000;
    return '#SID-${t.year}-${n.toString().padLeft(5, '0')}';
=======
    this.id,
  });

  /// Mã hồ sơ tạm chỉ dùng cho chế độ MOCK. Ở chế độ thật mã phải do server
  /// cấp (endpoint lưu hồ sơ).
  static String newCode() {
    final now = DateTime.now();

    String two(int n) => n.toString().padLeft(2, '0');

    final rand = (DateTime.now().microsecondsSinceEpoch % 100000)
        .toString()
        .padLeft(5, '0');
    return 'HS${now.year}${two(now.month)}${two(now.day)}-$rand';
  }

  /// Dựng từ phản hồi `GET /api/v1/scan-records` (extracted_data dạng
  /// snake_case tiếng Việt, supp riêng).
  factory SubmittedRecord.fromServer(Map<String, dynamic> json) {
    final extracted =
        (json['extracted_data'] as Map?)?.cast<String, dynamic>() ?? const {};
    final suppMap =
        (json['supp'] as Map?)?.cast<String, dynamic>() ?? const {};
    return SubmittedRecord(
      id: json['id']?.toString(),
      code: json['code']?.toString() ?? '',
      formId: json['form_id']?.toString() ?? '',
      name: extracted['ho_va_ten']?.toString() ?? '',
      date: _formatDate(json['created_at']?.toString()),
      card: IdCardData.fromServerJson(extracted),
      supp: suppMap.map((k, v) => MapEntry(k, v?.toString() ?? '')),
    );
  }

  static String _formatDate(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    final dt = DateTime.tryParse(iso);
    if (dt == null) return iso;
    // Chuyển UTC → giờ địa phương (FE-007) trước khi format hiển thị.
    final local = dt.toLocal();
    return '${local.day.toString().padLeft(2, '0')}/${local.month.toString().padLeft(2, '0')}/${local.year}';
>>>>>>> 8593503 (add data)
  }

  Map<String, dynamic> toJson() => {
        'code': code,
        'formId': formId,
        'name': name,
        'date': date,
        'card': card.toJson(),
        'supp': supp,
      };

<<<<<<< HEAD
  factory SubmittedRecord.fromJson(Map<String, dynamic> j) => SubmittedRecord(
        code: (j['code'] ?? '').toString(),
        formId: (j['formId'] ?? '').toString(),
        name: (j['name'] ?? '').toString(),
        date: (j['date'] ?? '').toString(),
        card: IdCardData.fromJson(
            Map<String, dynamic>.from(j['card'] as Map? ?? const {})),
        supp: Map<String, String>.from(
            (j['supp'] as Map? ?? const {}).map(
          (k, v) => MapEntry(k.toString(), (v ?? '').toString()),
        )),
      );
}
=======
  factory SubmittedRecord.fromJson(Map<String, dynamic> json) =>
      SubmittedRecord(
        code: json['code'] as String,
        formId: json['formId'] as String,
        name: json['name'] as String,
        date: json['date'] as String,
        card: IdCardData.fromJson(
            (json['card'] as Map?)?.cast<String, dynamic>() ?? const {}),
        supp: (json['supp'] as Map?)?.cast<String, String>() ?? const {},
      );
}
>>>>>>> 8593503 (add data)
