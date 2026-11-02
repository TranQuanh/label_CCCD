import 'id_card.dart';

/// Một hồ sơ người dùng đã kê khai & gửi.
class SubmittedRecord {
  final String code;
  final String formId;
  final String name;
  final String date;
  final IdCardData card;
  final Map<String, String> supp;

  const SubmittedRecord({
    required this.code,
    required this.formId,
    required this.name,
    required this.date,
    required this.card,
    required this.supp,
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
  }

  Map<String, dynamic> toJson() => {
        'code': code,
        'formId': formId,
        'name': name,
        'date': date,
        'card': card.toJson(),
        'supp': supp,
      };

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
