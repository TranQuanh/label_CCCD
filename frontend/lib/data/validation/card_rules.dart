import '../../core/validation/validators.dart';
import '../models/id_card.dart';

enum IssueLevel {
  /// Chặn không cho đi tiếp — dữ liệu chắc chắn sai.
  blocking,

  /// Chỉ cảnh báo (viền cam) — đáng ngờ nhưng vẫn có thể đúng.
  warning,
}

class FieldIssue {
  final String field;
  final String message;
  final IssueLevel level;

  const FieldIssue(this.field, this.message, this.level);

  bool get blocks => level == IssueLevel.blocking;
}

/// Bộ quy tắc nghiệp vụ trên toàn thẻ.
///
/// Thay cho `lowConfidence` mà backend **không** trả về: model chỉ greedy decode,
/// không sinh điểm tin cậy nào. Cờ "cần kiểm tra" ở đây là kết quả kiểm tra ràng
/// buộc miền dữ liệu — chính xác hơn một điểm tin cậy giả, và giải thích được cho
/// người dùng vì sao trường đó bị đánh dấu.
///
/// Hai trường `que_quan` / `noi_thuong_tru` và `co_gia_tri_den` **được phép rỗng**:
/// có một mẫu thẻ không in các mục này (13,2% ảnh trong tập test), và người từ 60
/// tuổi khi cấp thì thẻ không có hạn. Đánh chúng là lỗi chặn sẽ khoá cứng người
/// dùng hợp lệ.
class CardRules {
  const CardRules._();

  static List<FieldIssue> check(IdCardData c) {
    final issues = <FieldIssue>[];

    void add(String f, String m, IssueLevel l) => issues.add(FieldIssue(f, m, l));

    // ── Trường bắt buộc, kiểm tra độc lập ────────────────────────────────
    if (!Validators.notEmpty(c.fullName)) {
      add('fullName', 'Họ và tên không được để trống.', IssueLevel.blocking);
    }

    if (!Validators.cccd(c.idNumber)) {
      add('idNumber', 'Số CCCD phải đủ 12 chữ số, 3 số đầu là mã tỉnh (001–096).',
          IssueLevel.blocking);
    }

    final dob = Validators.parseDate(c.dob);
    if (dob == null) {
      add('dob', 'Ngày sinh sai định dạng DD/MM/YYYY hoặc không có thật.',
          IssueLevel.blocking);
    } else if (dob.isAfter(DateTime.now())) {
      add('dob', 'Ngày sinh không thể ở tương lai.', IssueLevel.blocking);
    }

    if (!Validators.sex(c.sex)) {
      add('sex', 'Giới tính chỉ nhận "Nam" hoặc "Nữ".', IssueLevel.blocking);
    }

    if (!Validators.nationality(c.nationality)) {
      add('nationality', 'Quốc tịch trên CCCD luôn là "Việt Nam".',
          IssueLevel.blocking);
    }

    final issue = Validators.parseDate(c.issueDate);
    if (issue == null) {
      add('issueDate', 'Ngày cấp sai định dạng DD/MM/YYYY hoặc không có thật.',
          IssueLevel.blocking);
    } else if (issue.isAfter(DateTime.now())) {
      add('issueDate', 'Ngày cấp không thể ở tương lai.', IssueLevel.blocking);
    }

    // ── Trường được phép rỗng ────────────────────────────────────────────
    if (!Validators.notEmpty(c.origin)) {
      add('origin', 'Quê quán đang trống — kiểm tra lại nếu thẻ có in mục này.',
          IssueLevel.warning);
    }
    if (!Validators.notEmpty(c.residence)) {
      add('residence',
          'Nơi thường trú đang trống — kiểm tra lại nếu thẻ có in mục này.',
          IssueLevel.warning);
    }
    if (!Validators.notEmpty(c.issuePlace)) {
      add('issuePlace', 'Nơi cấp đang trống.', IssueLevel.warning);
    }

    DateTime? expiry;
    if (Validators.notEmpty(c.expiry)) {
      expiry = Validators.parseDate(c.expiry);
      if (expiry == null) {
        add('expiry', 'Có giá trị đến sai định dạng DD/MM/YYYY.',
            IssueLevel.blocking);
      }
    }

    // ── Quy tắc liên trường ──────────────────────────────────────────────
    final idSex = Validators.sexFromIdNumber(c.idNumber);
    if (idSex != null &&
        Validators.sex(c.sex) &&
        idSex != Validators.normalizeSex(c.sex)) {
      add('sex', 'Giới tính không khớp chữ số thứ 4 của số CCCD (suy ra: $idSex).',
          IssueLevel.warning);
    }

    final idYear = Validators.birthYearFromIdNumber(c.idNumber);
    if (idYear != null && dob != null && idYear != dob.year) {
      add('dob', 'Năm sinh không khớp số CCCD (số CCCD mã hoá năm $idYear).',
          IssueLevel.warning);
    }

    if (expiry != null && issue != null && !expiry.isAfter(issue)) {
      add('expiry', 'Hạn thẻ phải sau ngày cấp.', IssueLevel.blocking);
    }

    if (expiry != null && dob != null &&
        !Validators.expiryMatchesBirthday(dob, expiry)) {
      add('expiry',
          'Hạn thẻ thường rơi đúng sinh nhật tuổi 25 / 40 / 60 — kiểm tra lại.',
          IssueLevel.warning);
    }

    return issues;
  }

  /// Gom theo tên trường để màn đối chiếu tra nhanh.
  static Map<String, List<FieldIssue>> byField(IdCardData c) {
    final out = <String, List<FieldIssue>>{};
    for (final i in check(c)) {
      out.putIfAbsent(i.field, () => <FieldIssue>[]).add(i);
    }
    return out;
  }

  /// Trường nào cần người kiểm tra lại (mọi mức) — thay cho `lowConfidence` cũ.
  static List<String> fieldsNeedingReview(IdCardData c) =>
      byField(c).keys.toList();
}
