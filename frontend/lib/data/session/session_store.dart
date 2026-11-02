import 'package:flutter/foundation.dart';

import '../models/id_card.dart';
import '../models/submitted_record.dart';

/// Tài khoản đang đăng nhập. Tách hẳn khỏi dữ liệu thẻ CCCD.
@immutable
class AuthUser {
  final String username;
  final String email;
  final String dob;

  const AuthUser({
    required this.username,
    this.email = '',
    this.dob = '',
  });
}

/// State dùng chung — `ChangeNotifier` thuần, nghe bằng `AnimatedBuilder`.
///
/// Hai lỗi của bản cũ (`AppStore`) được sửa ở đây:
///
/// 1. **Danh tính không còn lấy từ hồ sơ.** Bản cũ trả `records.first.card.fullName`
///    làm tên hiển thị, nên đăng nhập tài khoản mới vẫn chào tên của người có hồ sơ
///    gần nhất. Giờ tên hiển thị lấy từ [AuthUser]; thông tin thẻ chỉ được đọc qua
///    [latestCard] và màn hình phải ghi rõ "từ hồ sơ gần nhất".
/// 2. **Đăng xuất xoá sạch state.** Bản cũ chỉ điều hướng về màn đăng nhập trong
///    khi store là singleton toàn cục ⇒ người dùng kế tiếp thấy nguyên hồ sơ CCCD
///    của người trước. Với app e-KYC đó là lộ dữ liệu cá nhân, không chỉ là lỗi state.
class SessionStore extends ChangeNotifier {
  AuthUser? _user;
  final List<SubmittedRecord> _records = <SubmittedRecord>[];

  AuthUser? get user => _user;

  bool get isLoggedIn => _user != null;

  List<SubmittedRecord> get records => List.unmodifiable(_records);

  /// Tên hiển thị = tên tài khoản. Không suy từ hồ sơ.
  String get displayName => _user?.username ?? '';

  String get email => _user?.email ?? '';

  String get dob => _user?.dob ?? '';

  /// Chữ cái đầu cho avatar, an toàn với chuỗi rỗng.
  String get initial {
    final n = displayName.trim();
    return n.isEmpty ? '?' : n.substring(0, 1).toUpperCase();
  }

  /// Thẻ của hồ sơ gần nhất — chỉ để hiển thị tham khảo, KHÔNG phải danh tính
  /// đã xác thực của tài khoản.
  IdCardData? get latestCard =>
      _records.isEmpty ? null : _records.first.card;

  void login(AuthUser u) {
    _user = u;
    notifyListeners();
  }

  /// Xoá toàn bộ dữ liệu phiên. Gọi khi đăng xuất.
  void logout() {
    _user = null;
    _records.clear();
    notifyListeners();
  }

  void addRecord(SubmittedRecord r) {
    _records.insert(0, r);
    notifyListeners();
  }

  /// Nạp hồ sơ mẫu — CHỈ dùng ở chế độ mock để màn "Hồ sơ" không trống trơn.
  /// Không bao giờ gọi ở bản chạy thật: dữ liệu giả trong app e-KYC gây hiểu nhầm
  /// rằng người dùng đã nộp hồ sơ.
  void seedDemoRecords() {
    if (_records.isNotEmpty) return;
    final card = IdCardData.sample();
    _records.addAll([
      SubmittedRecord(
        code: '#SID-2026-40218',
        formId: 'eid',
        name: card.fullName,
        date: '28/06/2026',
        card: card.clone(),
        supp: const {'phone': '0901234567', 'email': 'demo@example.com'},
      ),
      SubmittedRecord(
        code: '#SID-2026-39755',
        formId: 'thuongtru',
        name: card.fullName,
        date: '21/06/2026',
        card: card.clone(),
        supp: const {
          'phone': '0901234567',
          'owner': 'Nguyễn Văn Bình',
          'rel': 'Con',
        },
      ),
    ]);
    notifyListeners();
  }
}

/// Instance dùng chung toàn app.
///
/// Đủ cho quy mô hiện tại; nếu sau này cần nhiều phiên song song hoặc test đơn vị
/// dễ hơn thì bọc bằng `InheritedNotifier` thay vì biến toàn cục — mọi màn hình
/// đều chỉ chạm vào đúng một tên này nên đổi là gọn.
final SessionStore sessionStore = SessionStore();
