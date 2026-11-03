import 'id_card.dart';

/// Một hồ sơ đã gửi — bản ghi được tạo sau khi người dùng xác nhận biểu mẫu.
///
/// P1: chỉ lưu RAM (`sessionStore`). P2: mã hồ sơ do SERVER cấp (qua
/// `POST /api/v1/scan-records`), lịch sử đọc từ PostgreSQL (`GET /scan-records`).
class SubmittedRecord {
  final String code;
  final String formId;
  final String name;
  final String date;
  final IdCardData card;
  final Map<String, String> supp;
  final String? id;

  const SubmittedRecord({
    required this.code,
    required this.formId,
    required this.name,
    required this.date,
    required this.card,
    required this.supp,
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
    return '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year}';
  }

  Map<String, dynamic> toJson() => {
        'code': code,
        'formId': formId,
        'name': name,
        'date': date,
        'card': card.toJson(),
        'supp': supp,
      };

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