import '../../core/validation/validators.dart';
import '../models/id_card.dart';

<<<<<<< HEAD
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
=======
/// Một vấn đề phát hiện trên một trường.
///
/// - `blocks == true`  → trường bắt buộc phải sửa mới cho phép tiếp tục.
/// - `blocks == false` → chỉ cảnh báo, người dùng vẫn có thể bỏ qua.
class FieldIssue {
  final bool blocks;
  final String message;

  const FieldIssue({required this.blocks, required this.message});
}

/// Quy tắc nghiệp vụ trên TOÀN thẻ — nguồn duy nhất của cờ "cần kiểm tra".
///
/// Backend không trả điểm tin cậy, nên các cảnh báo ở đây dựa trên ràng buộc
/// miền dữ liệu CCCD (Thông tư 07/2016/TT-BCA): số 12 chữ số + mã tỉnh 001–096,
/// ngày tháng có thật, giới tính khớp chữ số 4 của số CCCD, hạn thẻ rơi đúng
/// sinh nhật tuổi 25/40/60. `que_quan`, `noi_thuong_tru`, `co_gia_tri_den` được
/// phép trống — một số mẫu thẻ không in hoặc thẻ cấp cho người ≥60 không có hạn.
class CardRules {
  const CardRules._();

  /// Kiểm tra toàn bộ trường của một thẻ.
  ///
  /// Trả về map key-camelCase → danh sách vấn đề. Trường không có vấn đề gì
  /// không xuất hiện trong map.
  static Map<String, List<FieldIssue>> byField(IdCardData card) {
    final issues = <String, List<FieldIssue>>{};

    void add(String key, List<FieldIssue> list) {
      if (list.isNotEmpty) issues[key] = list;
    }

    add('fullName', _fullName(card.fullName));
    add('idNumber', _idNumber(card.idNumber));
    add('dob', _dob(card.dob));
    add('sex', _sex(card.idNumber, card.sex));
    add('nationality', _nationality(card.nationality));
    add('origin', _address('Quê quán', card.origin));
    add('residence', _address('Nơi thường trú', card.residence));
    add('issueDate', _issueDate(card.issueDate));
    add('expiry', _expiry(card.dob, card.expiry));
    add('issuePlace', _address('Nơi cấp', card.issuePlace));
    add('features', _optional('Đặc điểm nhận dạng', card.features));
>>>>>>> 8593503 (add data)

    return issues;
  }

<<<<<<< HEAD
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
=======
  static List<FieldIssue> _fullName(String v) {
    if (!Validators.notEmpty(v)) {
      return const [
        FieldIssue(blocks: true, message: 'Họ và tên không được để trống.'),
      ];
    }
    return const [];
  }

  static List<FieldIssue> _idNumber(String v) {
    if (!Validators.notEmpty(v)) {
      return const [
        FieldIssue(blocks: true, message: 'Số CCCD không được để trống.'),
      ];
    }
    if (!Validators.cccd(v)) {
      return const [
        FieldIssue(
          blocks: true,
          message:
              'Số CCCD phải đủ 12 chữ số và 3 số đầu là mã tỉnh hợp lệ (001–096).',
        ),
      ];
    }
    return const [];
  }

  static List<FieldIssue> _dob(String v) {
    if (!Validators.notEmpty(v)) {
      return const [
        FieldIssue(blocks: true, message: 'Ngày sinh không được để trống.'),
      ];
    }
    if (!Validators.pastDate(v)) {
      return const [
        FieldIssue(
          blocks: true,
          message: 'Ngày sinh phải có thật và nằm trong quá khứ (DD/MM/YYYY).',
        ),
      ];
    }
    return const [];
  }

  static List<FieldIssue> _sex(String idNumber, String sex) {
    if (!Validators.notEmpty(sex)) {
      return const [
        FieldIssue(blocks: true, message: 'Giới tính không được để trống.'),
      ];
    }
    if (!Validators.sex(sex)) {
      return const [
        FieldIssue(blocks: true, message: 'Giới tính chỉ là Nam hoặc Nữ.'),
      ];
    }
    final fromId = Validators.sexFromIdNumber(idNumber);
    if (fromId != null &&
        sex.trim().toLowerCase() != fromId.toLowerCase()) {
      return [
        FieldIssue(
          blocks: false,
          message:
              'Giới tính không khớp với chữ số thứ 4 của số CCCD ($fromId).',
        ),
      ];
    }
    return const [];
  }

  static List<FieldIssue> _nationality(String v) {
    if (!Validators.notEmpty(v)) {
      return const [
        FieldIssue(blocks: false, message: 'Quốc tịch đang trống.'),
      ];
    }
    if (!Validators.nationality(v)) {
      return const [
        FieldIssue(
          blocks: false,
          message: 'Quốc tịch trên CCCD là "Việt Nam".',
        ),
      ];
    }
    return const [];
  }

  /// Địa chỉ (quê quán, thường trú, nơi cấp) được phép trống.
  static List<FieldIssue> _address(String label, String v) {
    if (Validators.notEmpty(v)) return const [];
    return [
      FieldIssue(blocks: false, message: '$label đang trống — kiểm tra lại.'),
    ];
  }

  static List<FieldIssue> _optional(String label, String v) {
    if (Validators.notEmpty(v)) return const [];
    return [
      FieldIssue(blocks: false, message: '$label đang trống — kiểm tra lại.'),
    ];
  }

  static List<FieldIssue> _issueDate(String v) {
    if (!Validators.notEmpty(v)) {
      return const [
        FieldIssue(blocks: false, message: 'Ngày cấp đang trống.'),
      ];
    }
    if (!Validators.pastDate(v)) {
      return const [
        FieldIssue(
          blocks: true,
          message: 'Ngày cấp phải có thật và nằm trong quá khứ (DD/MM/YYYY).',
        ),
      ];
    }
    return const [];
  }

  static List<FieldIssue> _expiry(String dob, String expiry) {
    if (!Validators.notEmpty(expiry)) {
      // Thẻ cấp cho người từ 60 tuổi trở lên không có hạn → để trống là hợp lệ.
      return const [];
    }
    if (!Validators.date(expiry)) {
      return const [
        FieldIssue(
          blocks: true,
          message: 'Hạn thẻ phải là ngày hợp lệ (DD/MM/YYYY).',
        ),
      ];
    }
    final birth = Validators.parseDate(dob);
    final exp = Validators.parseDate(expiry);
    if (birth != null &&
        exp != null &&
        !Validators.expiryMatchesBirthday(birth, exp)) {
      return const [
        FieldIssue(
          blocks: false,
          message:
              'Hạn thẻ thường rơi đúng sinh nhật tuổi 25 / 40 / 60 — kiểm tra lại.',
        ),
      ];
    }
    return const [];
  }
}
>>>>>>> 8593503 (add data)
