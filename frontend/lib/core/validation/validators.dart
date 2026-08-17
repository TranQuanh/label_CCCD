/// Kiểm tra dữ liệu ở mức chuỗi — không phụ thuộc model nào.
///
/// Các ràng buộc ở đây lấy từ chính miền dữ liệu CCCD (Thông tư 07/2016/TT-BCA)
/// chứ không phải quy ước tự đặt, nên chúng bắt được cả lỗi model đọc sai lẫn lỗi
/// người nhập tay. Quy tắc liên trường (số CCCD ↔ ngày sinh ↔ giới tính ↔ hạn thẻ)
/// nằm ở `data/validation/card_rules.dart`.
class Validators {
  const Validators._();

  static final _dateShape = RegExp(r'^(\d{2})/(\d{2})/(\d{4})$');
  static final _email = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
  static final _nonDigit = RegExp(r'\D');

  /// Giới tính in trên thẻ chỉ có hai giá trị.
  static const sexValues = <String>['Nam', 'Nữ'];

  /// Quốc tịch trên CCCD luôn là "Việt Nam" (nhãn `Kinh` / `Viet Nam` trong tập
  /// draft là lỗi gán nhãn — xem phụ lục audit).
  static const nationalityValue = 'Việt Nam';

  static bool notEmpty(String v) => v.trim().isNotEmpty;

  static bool email(String v) => _email.hasMatch(v.trim());

  /// Chỉ giữ chữ số — số CCCD hiển thị có thể có khoảng trắng phân nhóm.
  static String digitsOnly(String v) => v.replaceAll(_nonDigit, '');

  /// Chuẩn hoá về đúng 12 chữ số liền nhau như backend trả về.
  static String normalizeIdNumber(String v) => digitsOnly(v);

  /// Parse DD/MM/YYYY và kiểm tra ngày có thật.
  ///
  /// Trả `null` nếu sai định dạng hoặc không tồn tại (`31/02/2020`, `32/13/2020`).
  /// `DateTime(2020, 2, 31)` tự cuộn sang 02/03 nên phải so lại từng thành phần.
  static DateTime? parseDate(String v) {
    final m = _dateShape.firstMatch(v.trim());
    if (m == null) return null;
    final day = int.parse(m.group(1)!);
    final month = int.parse(m.group(2)!);
    final year = int.parse(m.group(3)!);
    if (month < 1 || month > 12) return null;
    if (day < 1 || day > 31) return null;
    if (year < 1900 || year > 2100) return null;
    final dt = DateTime(year, month, day);
    if (dt.year != year || dt.month != month || dt.day != day) return null;
    return dt;
  }

  static String formatDate(DateTime d) =>
      '${_two(d.day)}/${_two(d.month)}/${d.year}';

  static String _two(int n) => n.toString().padLeft(2, '0');

  /// Ngày hợp lệ về mặt lịch (chưa xét quan hệ với trường khác).
  static bool date(String v) => parseDate(v) != null;

  /// Ngày trong quá khứ — dùng cho ngày sinh, ngày cấp.
  static bool pastDate(String v) {
    final d = parseDate(v);
    if (d == null) return false;
    return !d.isAfter(DateTime.now());
  }

  /// Số CCCD phải đủ 12 chữ số và 3 số đầu là mã tỉnh hợp lệ (001–096).
  static bool cccd(String v) {
    final d = digitsOnly(v);
    if (d.length != 12) return false;
    final province = int.tryParse(d.substring(0, 3));
    return province != null && province >= 1 && province <= 96;
  }

  static bool phone(String v) {
    final d = digitsOnly(v);
    return d.length >= 9 && d.length <= 11;
  }

  /// So không phân biệt hoa/thường: model có thể trả `NAM` thay vì `Nam`, chặn
  /// cứng vì lý do đó sẽ khoá người dùng hợp lệ.
  static bool sex(String v) {
    final t = v.trim().toLowerCase();
    return sexValues.any((s) => s.toLowerCase() == t);
  }

  /// Đưa về đúng dạng in trên thẻ (`Nam` / `Nữ`); trả nguyên văn nếu không nhận ra.
  static String normalizeSex(String v) {
    final t = v.trim().toLowerCase();
    for (final s in sexValues) {
      if (s.toLowerCase() == t) return s;
    }
    return v.trim();
  }

  static bool nationality(String v) =>
      v.trim().toLowerCase() == nationalityValue.toLowerCase();

  // ── Giải mã cấu trúc số CCCD ────────────────────────────────────────────
  // 12 số = [3 mã tỉnh][1 thế kỷ+giới tính][2 năm sinh][6 ngẫu nhiên].

  /// Giới tính suy từ chữ số thứ 4 (chẵn = Nam, lẻ = Nữ). `null` nếu số không hợp lệ.
  static String? sexFromIdNumber(String idNumber) {
    final d = digitsOnly(idNumber);
    if (d.length != 12) return null;
    final code = int.tryParse(d[3]);
    if (code == null) return null;
    return code.isEven ? 'Nam' : 'Nữ';
  }

  /// Năm sinh đầy đủ suy từ chữ số thứ 4 (thế kỷ) + chữ số 5–6 (2 số cuối).
  static int? birthYearFromIdNumber(String idNumber) {
    final d = digitsOnly(idNumber);
    if (d.length != 12) return null;
    final centuryCode = int.tryParse(d[3]);
    final yy = int.tryParse(d.substring(4, 6));
    if (centuryCode == null || yy == null) return null;
    return 1900 + (centuryCode ~/ 2) * 100 + yy;
  }

  /// Hạn thẻ hợp lệ = đúng ngày sinh nhật tuổi 25 / 40 / 60.
  ///
  /// Người từ 60 tuổi trở lên khi cấp thì thẻ không có hạn — khi đó `expiry`
  /// để trống là đúng, không phải thiếu dữ liệu.
  static bool expiryMatchesBirthday(DateTime dob, DateTime expiry) {
    for (final age in const [25, 40, 60]) {
      final milestone = DateTime(dob.year + age, dob.month, dob.day);
      if (milestone.year == expiry.year &&
          milestone.month == expiry.month &&
          milestone.day == expiry.day) {
        return true;
      }
    }
    return false;
  }
}
