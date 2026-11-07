import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../api/api_exception.dart';
import '../api/auth_api_client.dart';
import '../api/token_store.dart';
import '../models/auth_user.dart';
import '../models/form_type.dart';
import '../models/id_card.dart';
import '../models/submitted_record.dart';
import '../../core/config/api_config.dart';
import '../../core/validation/validators.dart';

/// Lưu trữ phiên đăng nhập + danh mục biểu mẫu + hồ sơ.
///
/// P1: đăng nhập thật gọi backend `/api/v1/auth/*`; token nằm trong Secure
/// Storage ([TokenStore]) và được dùng để **tự đăng nhập lại** khi mở app.
///
/// P2: hồ sơ gửi lên server qua `/api/v1/scan-records` (mã hồ sơ do server
/// cấp), lịch sử tải từ PostgreSQL khi mở tab Hồ sơ; danh mục biểu mẫu lấy từ
/// `GET /api/v1/forms`. Role chỉ có `user` và `admin`.
///
/// Profile CCCD: server `/api/v1/profiles` là nguồn chân lý, Secure Storage
/// chỉ là cache. Các profile ngang hàng, KHÔNG có profile "mặc định".
///
/// Chế độ mock (`ApiConfig.useMock`) vẫn chạy không cần server.
///
/// `logout()` gọi API thu hồi token rồi xoá toàn bộ phiên + hồ sơ trên máy.
class SessionStore extends ChangeNotifier {
  AuthUser? _user;
  final List<SubmittedRecord> _records = [];
  final List<FormType> _forms = [];
  List<IdCardData> _profiles = [];
  // Xoá reviewQueue vì không cần chức năng review
  final AuthApiClient _auth = AuthApiClient();

  // Xoá cờ masked vì không cần che số CCCD
  bool _loadingRecords = false;
  // Lỗi lần tải lịch sử hồ sơ gần nhất (null = không lỗi).
  String? _recordsError;
  bool _loadingForms = false;
  bool _loadingProfiles = false;
  // Lần nạp profile đang chạy dở (tránh nạp/migration chạy 2 lần song song).
  Future<void>? _profilesLoading;
  // Phiên bản danh sách profile — tăng ở mỗi thao tác ghi (thêm/sửa/xoá).
  // Lần nạp thấy phiên bản đổi giữa chừng thì bỏ kết quả nạp, tránh
  // ghi đè profile vừa lưu bằng danh sách cũ.
  int _profilesVersion = 0;
  // Đang xử lý hết phiên (nhiều request 401 cùng lúc chỉ xử lý một lần).
  bool _expiring = false;
  // Thông báo cho UI khi phiên kết thúc KHÔNG do người dùng bấm đăng xuất
  // (hết hạn / đổi mật khẩu). main.dart đọc qua [takeSessionEndMessage].
  String? _sessionEndMessage;

  static const sessionExpiredMsg =
      'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.';

  SessionStore() {
    // Hook dùng chung cho MỌI AuthApiClient (kể cả các tab admin tự tạo
    // instance riêng): refresh thất bại → xoá phiên cục bộ.
    AuthApiClient.onSessionExpired = () {
      expireSession();
    };
  }

  AuthUser? get user => _user;

  String get displayName =>
      (_user?.fullName.isNotEmpty ?? false)
          ? _user!.fullName
          : (_user?.username ?? '');
  String get email => _user?.email ?? '';
  String get role => _user?.role ?? '';
  bool get isLoggedIn => _user != null;
  bool get isAdmin => _user?.role == 'admin';

  /// Ký tự đầu của tên hiển thị — dùng cho avatar tròn.
  String get initial {
    final name = displayName.trim();
    if (name.isEmpty) return '?';
    return name[0].toUpperCase();
  }

  List<SubmittedRecord> get records => List.unmodifiable(_records);
  List<FormType> get forms => List.unmodifiable(_forms);
  // Xoá getter reviewQueue
  // Xoá getter masked
  bool get loadingRecords => _loadingRecords;

  /// Thông báo lỗi lần tải lịch sử hồ sơ gần nhất; null nếu tải thành công.
  String? get recordsError => _recordsError;
  bool get loadingForms => _loadingForms;
  bool get loadingProfiles => _loadingProfiles;

  /// Danh sách profiles CCCD cá nhân của người dùng đã lưu
  List<IdCardData> get profiles => List.unmodifiable(_profiles);

  /// Có tồn tại ít nhất một profile nào đó
  bool get hasProfiles => _profiles.isNotEmpty;

  /// Thẻ của hồ sơ gần đây nhất (dùng cho nút "Dùng cấu hình cũ" ở tab Profile).
  /// `_records` sắp MỚI → CŨ (server ORDER BY created_at DESC, hồ sơ mới
  /// `insert(0, ...)`), nên hồ sơ gần nhất là phần tử ĐẦU, không phải cuối.
  IdCardData? get latestCard =>
      _records.isEmpty ? null : _records.first.card;

  /// Khởi động app: nếu có refresh token trong Secure Storage thì tự đăng nhập
  /// lại (gọi `/auth/me` sau khi có access token). Trả true nếu đã vào phiên.
  Future<bool> tryAutoLogin() async {
    if (ApiConfig.useMock) {
      _loginMock();
      _forms.addAll(kFormTypes);
      seedDemoRecords();
      await loadProfiles();
      return true;
    }
    if (_user != null) return true;
    final refresh = await TokenStore.readRefreshToken();
    if (refresh == null) return false;
    try {
      final access = await _auth.refreshAccessToken();
      if (access == null) {
        // Server từ chối refresh token (401/403) → token chết hẳn, xoá.
        await TokenStore.clear();
        return false;
      }
      final user = await _auth.me();
      _user = user;
      await loadProfiles();
      notifyListeners();
      return true;
    } on ApiException catch (e) {
      // Chỉ xoá token khi server khẳng định phiên không còn hợp lệ.
      if (e.statusCode == 401 || e.statusCode == 403) {
        await TokenStore.clear();
      }
      return false;
    } catch (e) {
      // Lỗi mạng/timeout: GIỮ token — lần mở app sau (có mạng) vẫn tự đăng
      // nhập được; lần này người dùng thấy màn đăng nhập.
      debugPrint('Tự đăng nhập thất bại do lỗi kết nối, giữ token: $e');
      return false;
    }
  }

  /// Đăng nhập bằng email HOẶC tên đăng nhập + mật khẩu.
  Future<AuthUser> login({
    required String identifier,
    required String password,
  }) async {
    if (ApiConfig.useMock) {
      _loginMock();
      _forms.addAll(kFormTypes);
      seedDemoRecords();
      await loadProfiles();
      return _user!;
    }
    final user = await _auth.login(identifier: identifier, password: password);
    _user = user;
    await loadProfiles();
    notifyListeners();
    return user;
  }

  /// Đăng ký tài khoản mới (backend tự đăng nhập phiên đầu).
  Future<AuthUser> register({
    required String username,
    required String email,
    required String password,
    required String fullName,
  }) async {
    if (ApiConfig.useMock) {
      _loginMock();
      _forms.addAll(kFormTypes);
      seedDemoRecords();
      await loadProfiles();
      return _user!;
    }
    final user = await _auth.register(
      username: username,
      email: email,
      password: password,
      fullName: fullName,
    );
    _user = user;
    await loadProfiles();
    notifyListeners();
    return user;
  }

  Future<void> logout() async {
    // Chặn expireSession trong lúc đăng xuất: request nền 401 giữa các await
    // không được đặt thông báo "Phiên đã hết hạn" (gây điều hướng 2 lần).
    _expiring = true;
    try {
      // Lấy id TRƯỚC khi xoá _user — key cache profile theo user.
      final uid = _user?.id;
      if (!ApiConfig.useMock) {
        await _auth.logout(); // thu hồi refresh + blacklist access
        // Thật: server là nguồn chân lý → xoá cache profile của user này trên
        // máy (đăng nhập lại sẽ tải lại từ server).
        await TokenStore.deleteProfiles(uid);
      }
      // Mock: KHÔNG đụng storage — profile chỉ sống ở máy, giữ cho lần sau.
      _profilesVersion++; // lần nạp profile đang dở (nếu có) không ghi đè nữa
      _user = null;
      _profiles = [];
      _records.clear();
      _recordsError = null;
      _forms.clear();
      notifyListeners();
    } finally {
      _expiring = false;
    }
  }

  /// Kết thúc phiên cục bộ khi token đã chết (refresh bị từ chối, đổi mật
  /// khẩu, bị admin khoá/đổi role). KHÔNG gọi API logout — token đã vô hiệu.
  ///
  /// [message]: thông báo hiển thị ở màn đăng nhập (main.dart điều hướng).
  Future<void> expireSession({String message = sessionExpiredMsg}) async {
    // Chưa vào phiên (vd. đang auto-login — tryAutoLogin tự xoá token khi
    // 401/403) hoặc đã xử lý rồi → bỏ qua; tránh request 401 đến muộn xoá
    // token của lần đăng nhập mới.
    if (_expiring || _user == null) return;
    _expiring = true;
    try {
      final uid = _user?.id;
      await TokenStore.clear();
      // Mock: giữ cache profile trên máy như logout().
      if (!ApiConfig.useMock && uid != null) {
        await TokenStore.deleteProfiles(uid);
      }
      _profilesVersion++; // lần nạp profile đang dở (nếu có) không ghi đè nữa
      _user = null;
      _profiles = [];
      _records.clear();
      _recordsError = null;
      _forms.clear();
      _sessionEndMessage = message;
      notifyListeners();
    } finally {
      _expiring = false;
    }
  }

  /// Lấy (và xoá) thông báo kết thúc phiên do hết hạn; null nếu là đăng xuất
  /// thường (màn Tài khoản tự điều hướng).
  String? takeSessionEndMessage() {
    final m = _sessionEndMessage;
    _sessionEndMessage = null;
    return m;
  }

  // ── Profile CCCD người dùng ─────────────────────────────────────────────
  //
  // Thật: server (`/api/v1/profiles`, bảng tblCccdProfile) là nguồn chân lý,
  // SecureStorage chỉ là cache để mở app hiện ngay. Mọi thao tác ghi gọi server
  // TRƯỚC, thành công mới cập nhật state + cache — lỗi 409 trùng CCCD hoặc lỗi
  // mạng được ném [ApiException] cho UI hiển thị, không để lại dữ liệu "ma".
  // Mock: chỉ lưu trên máy như cũ.
  //
  // Các profile ngang hàng (không có profile "mặc định"): khi điền biểu mẫu
  // người dùng tự chọn profile cần dùng.

  static const _duplicateMsg = 'Số CCCD này đã có trong profile khác';
  static const _networkErrorMsg =
      'Không kết nối được máy chủ. Profile chưa được lưu, vui lòng thử lại.';

  bool get _useServer => !ApiConfig.useMock && isLoggedIn;

  /// Ghi cache profile (kèm id server) của user hiện tại.
  Future<void> _persistLocal() async {
    await TokenStore.saveProfiles(
      jsonEncode(_profiles.map((e) => e.toLocalJson()).toList()),
      _user?.id,
    );
  }

  /// Vị trí HIỆN TẠI của một profile trong danh sách (-1 nếu đã bị xoá).
  ///
  /// Màn hình giữ tham chiếu profile thay vì chỉ số cố định: danh sách có thể
  /// được nạp lại từ server/đổi thứ tự trong lúc màn hình đang mở. Tìm theo
  /// tham chiếu trước (sửa profile cập nhật tại chỗ nên tham chiếu không đổi),
  /// rồi theo id server (sau khi nạp lại, đối tượng là bản mới).
  int indexOfProfile(IdCardData profile) {
    final byRef = _profiles.indexWhere((p) => identical(p, profile));
    if (byRef >= 0) return byRef;
    final id = profile.profileId;
    if (id != null) {
      final byId = _profiles.indexWhere((p) => p.profileId == id);
      if (byId >= 0) return byId;
    }
    // Chế độ mock / profile chưa có id server: nạp lại từ cache tạo đối tượng
    // mới không có id → dò theo số CCCD (duy nhất trong danh sách của user).
    final cccd = Validators.normalizeIdNumber(profile.idNumber);
    if (cccd.isEmpty) return -1;
    return _profiles.indexWhere(
        (p) => Validators.normalizeIdNumber(p.idNumber) == cccd);
  }

  /// Chặn trùng số CCCD (chuẩn hoá chỉ còn chữ số) với profile khác.
  void _ensureNoDuplicate(IdCardData card, {int? exceptIndex}) {
    final id = Validators.normalizeIdNumber(card.idNumber);
    if (id.isEmpty) return;
    for (var i = 0; i < _profiles.length; i++) {
      if (i == exceptIndex) continue;
      if (Validators.normalizeIdNumber(_profiles[i].idNumber) == id) {
        throw const ApiException(_duplicateMsg);
      }
    }
  }

  /// Lỗi nghiệp vụ (ApiException, ví dụ 409) giữ nguyên; lỗi mạng/timeout bọc
  /// thành thông báo tiếng Việt rõ ràng.
  Future<T> _guardNetwork<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on ApiException {
      rethrow;
    } catch (e) {
      debugPrint('Lỗi kết nối khi đồng bộ Profile CCCD: $e');
      throw const ApiException(_networkErrorMsg);
    }
  }

  /// 1 profile server `{id, data, ...}` → IdCardData (kèm profileId).
  IdCardData _fromServerProfile(Map<String, dynamic> p) {
    final data = p['data'];
    return IdCardData.fromServerJson(
      data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{},
    )..profileId = p['id']?.toString();
  }

  /// Thay danh sách bằng dữ liệu server.
  void _applyServerList(List<Map<String, dynamic>> list) {
    _profiles = list.map(_fromServerProfile).toList();
  }

  /// Đọc cache profile trên máy; lỗi decode → danh sách rỗng.
  Future<List<IdCardData>> _readLocalProfiles() async {
    final localJson = await TokenStore.readProfiles(_user?.id);
    if (localJson == null || localJson.isEmpty) return [];
    try {
      final decoded = jsonDecode(localJson);
      if (decoded is List) {
        return decoded
            .whereType<Map>()
            .map((e) => IdCardData.fromLocalJson(Map<String, dynamic>.from(e)))
            .toList();
      }
    } catch (e) {
      debugPrint('Cache Profile CCCD hỏng, bỏ qua: $e');
    }
    return [];
  }

  /// Nạp danh sách Profile CCCD: hiện cache trên máy ngay, rồi (chế độ thật)
  /// tải từ server. CHỈ thay dữ liệu khi server trả về thành công; server lỗi
  /// thì giữ cache đang hiển thị.
  Future<void> loadProfiles() {
    // Đang có lần nạp chạy dở (ví dụ login + ProfileTab.initState) → dùng chung.
    return _profilesLoading ??=
        _loadProfiles().whenComplete(() => _profilesLoading = null);
  }

  Future<void> _loadProfiles() async {
    _loadingProfiles = true;
    notifyListeners();
    final startVersion = _profilesVersion;
    try {
      // 1. Cache trên máy
      final cached = await _readLocalProfiles();
      if (_profilesVersion == startVersion) {
        _profiles = cached;
        notifyListeners();
      }

      // 2. Server (nguồn chân lý)
      if (_useServer) {
        try {
          var list = await _auth.listProfiles();

          // Migration: profile trên máy chưa có id server (bản app trước chỉ
          // lưu local, hoặc lần tải lên trước bị lỗi) → tải lên server, BẤT KỂ
          // server đã có profile hay chưa.
          final pending = cached.where((p) => p.profileId == null).toList();
          final failed = <IdCardData>[];
          if (pending.isNotEmpty) {
            final serverIds = list
                .map((p) =>
                    Validators.normalizeIdNumber(_fromServerProfile(p).idNumber))
                .where((id) => id.isNotEmpty)
                .toSet();
            var uploaded = false;
            for (final p in pending) {
              final idNumber = Validators.normalizeIdNumber(p.idNumber);
              // Đã có trên server (cùng số CCCD) → coi như đã chuyển xong.
              if (idNumber.isNotEmpty && serverIds.contains(idNumber)) continue;
              try {
                await _auth.createProfile(p.toServerJson());
                uploaded = true;
                if (idNumber.isNotEmpty) serverIds.add(idNumber);
              } on ApiException catch (e) {
                if (e.statusCode == 409 || e.statusCode == 400) {
                  // 409: đã có trên server; 400: profile rỗng, không có gì
                  // để giữ → coi như xong.
                  debugPrint('Bỏ qua profile cũ khi chuyển lên server: $e');
                } else {
                  failed.add(p);
                  debugPrint('Chưa chuyển được profile cũ lên server: $e');
                }
              } catch (e) {
                // Lỗi mạng/timeout → giữ lại để lần nạp sau thử lại.
                failed.add(p);
                debugPrint('Chưa chuyển được profile cũ lên server: $e');
              }
            }
            // Có profile vừa tải lên → nạp lại để có id từ server.
            if (uploaded) list = await _auth.listProfiles();
          }

          if (_profilesVersion != startVersion) {
            // Có thao tác ghi xen giữa (đã được server xác nhận) → state hiện
            // tại mới hơn kết quả nạp, giữ nguyên.
            debugPrint('Bỏ kết quả nạp Profile CCCD vì danh sách vừa thay đổi');
          } else {
            _applyServerList(list);
            // Profile cũ chưa tải lên được → giữ lại (nối sau danh sách server)
            // trong state + cache để lần nạp sau thử lại, KHÔNG xoá âm thầm.
            _profiles.addAll(failed);
            await _persistLocal();
          }
        } catch (e) {
          // Lỗi GET danh sách (kể cả lần nạp lại sau migration) → giữ cache;
          // profile đã tải lên mà chưa có id sẽ được nhận ra (trùng số CCCD)
          // ở lần nạp sau.
          debugPrint('Không tải được Profile CCCD từ server, dùng cache: $e');
        }
      }
    } catch (e) {
      // Lỗi đọc cache: giữ nguyên những gì đang có để app không đơ.
      debugPrint('Lỗi nạp Profile CCCD: $e');
    } finally {
      _loadingProfiles = false;
      notifyListeners();
    }
  }

  /// Thêm profile mới. Ném [ApiException] nếu trùng số CCCD / lỗi server.
  Future<void> addProfile(IdCardData card) async {
    _ensureNoDuplicate(card);
    final newProfile = card.clone()..profileId = null;

    if (_useServer) {
      final p = await _guardNetwork(
        () => _auth.createProfile(newProfile.toServerJson()),
      );
      _profilesVersion++;
      _profiles.add(_fromServerProfile(p));
    } else {
      _profilesVersion++;
      _profiles.add(newProfile);
    }
    notifyListeners();
    await _persistLocal();
  }

  /// Cập nhật profile tại vị trí cụ thể. Ném [ApiException] nếu trùng số CCCD
  /// với profile khác / lỗi server.
  Future<void> updateProfileAt(int index, IdCardData card) async {
    if (index < 0 || index >= _profiles.length) return;
    _ensureNoDuplicate(card, exceptIndex: index);

    final original = _profiles[index];
    var updated = card.clone()..profileId = original.profileId;

    if (_useServer) {
      final id = updated.profileId;
      final payload = updated.toServerJson();
      // Profile cache cũ chưa có id server → tạo mới trên server.
      final p = await _guardNetwork(
        () => id != null
            ? _auth.updateProfile(id, payload)
            : _auth.createProfile(payload),
      );
      updated = _fromServerProfile(p);
    }

    // Tìm lại vị trí sau await (danh sách có thể đã đổi).
    _profilesVersion++;
    final i = _profiles.indexOf(original);
    if (i < 0) return;
    // Cập nhật TẠI CHỖ (giữ nguyên đối tượng) để các màn hình đang giữ tham
    // chiếu profile này (ProfileDetailScreen) vẫn tìm thấy nó qua indexOfProfile.
    original
      ..applyMap(updated.toMap())
      ..profileId = updated.profileId;
    notifyListeners();
    await _persistLocal();
  }

  /// Xóa profile tại vị trí cụ thể (thật: xoá trên server trước).
  Future<void> removeProfileAt(int index) async {
    if (index < 0 || index >= _profiles.length) return;

    final removed = _profiles[index];
    final id = removed.profileId;
    if (_useServer && id != null) {
      await _guardNetwork(() => _auth.deleteProfile(id));
    }

    _profilesVersion++;
    _profiles.remove(removed); // tìm lại theo tham chiếu (danh sách có thể đã đổi)
    notifyListeners();
    await _persistLocal();
  }

  /// Xóa tất cả profiles (thật: xoá từng profile trên server trước).
  Future<void> clearProfiles() async {
    _profilesVersion++;
    try {
      if (_useServer) {
        for (final p in List.of(_profiles)) {
          final id = p.profileId;
          if (id != null) {
            await _guardNetwork(() => _auth.deleteProfile(id));
          }
          _profiles.remove(p);
        }
      }
      _profiles.clear();
    } finally {
      notifyListeners();
      await _persistLocal();
    }
  }

  /// Nạp thông tin từ hồ sơ gần nhất thành profile (tiện ích cho người dùng).
  Future<bool> importProfileFromLatestRecord() async {
    final c = latestCard;
    if (c == null || c.isEmpty) return false;
    await addProfile(c);
    return true;
  }

  // ── Biểu mẫu (P2: lấy từ server, fallback kFormTypes khi mock) ──────────

  Future<void> loadForms() async {
    if (ApiConfig.useMock) {
      if (_forms.isEmpty) _forms.addAll(kFormTypes);
      notifyListeners();
      return;
    }
    _loadingForms = true;
    notifyListeners();
    try {
      final raw = await _auth.listForms();
      _forms
        ..clear()
        ..addAll(raw.map(FormType.fromJson));
    } catch (_) {
      // Lỗi mạng: giữ danh mục hiện có (nếu trống thì rơi về kFormTypes).
      if (_forms.isEmpty) _forms.addAll(kFormTypes);
    } finally {
      _loadingForms = false;
      notifyListeners();
    }
  }

  FormType? formById(String id) {
    for (final f in _forms) {
      if (f.id == id) return f;
    }
    return null;
  }

  // ── Hồ sơ (P2: server là nguồn chân lý lịch sử) ─────────────────────────

  /// Gửi hồ sơ lên server (real) hoặc lưu RAM (mock). Trả hồ sơ đã lưu —
  /// `code` là mã do SERVER cấp (real) hoặc mã tạm client (mock).
  Future<SubmittedRecord> submitRecord({
    required FormType formType,
    required IdCardData card,
    required Map<String, String> supp,
  }) async {
    if (ApiConfig.useMock) {
      final record = SubmittedRecord(
        code: SubmittedRecord.newCode(),
        formId: formType.id,
        name: card.fullName,
        date: _today(),
        card: card,
        supp: supp,
      );
      _records.insert(0, record);
      notifyListeners();
      return record;
    }
    final result = await _auth.submitRecord(
      formId: formType.id,
      extractedData: card.toServerJson(),
      supp: supp,
      cardSide: 'both',
      isEdited: false,
    );
    final record = SubmittedRecord(
      id: result['record_id'],
      code: result['code'] ?? '',
      formId: formType.id,
      name: card.fullName,
      date: _today(),
      card: card,
      supp: supp,
    );
    _records.insert(0, record);
    notifyListeners();
    return record;
  }

  /// Tải lịch sử hồ sơ từ PostgreSQL (real).
  ///
  /// Không ném lỗi ra ngoài (nơi gọi dùng `unawaited`): lỗi được ghi vào
  /// [recordsError] để tab Hồ sơ hiện thông báo + nút Thử lại; danh sách cũ
  /// giữ nguyên.
  Future<void> loadRecords() async {
    if (ApiConfig.useMock) return; // mock dùng dữ liệu seed sẵn
    _loadingRecords = true;
    notifyListeners();
    try {
      final records = await _auth.listRecords();
      final list = records.map(SubmittedRecord.fromServer).toList();
      _records
        ..clear()
        ..addAll(list);
      _recordsError = null;
    } on ApiException catch (e) {
      // 401 = phiên hết hạn: expireSession đã xử lý (về màn đăng nhập), không
      // để lại lỗi cũ cho lần đăng nhập sau.
      if (e.statusCode != 401) _recordsError = e.userMessage;
    } catch (e) {
      debugPrint('Không tải được lịch sử hồ sơ: $e');
      _recordsError = _recordsNetworkErrorMsg;
    } finally {
      _loadingRecords = false;
      notifyListeners();
    }
  }

  /// Cập nhật hồ sơ đã gửi (real: gọi PATCH API; mock: cập nhật RAM).
  /// Trả về `SubmittedRecord` mới sau khi cập nhật.
  Future<SubmittedRecord> updateRecord({
    required SubmittedRecord original,
    required IdCardData card,
    required Map<String, String> supp,
  }) async {
    if (ApiConfig.useMock) {
      // Mock: tạo record mới thay thế record cũ trong danh sách RAM.
      final updated = SubmittedRecord(
        id: original.id,
        code: original.code,
        formId: original.formId,
        name: card.fullName,
        date: original.date,
        card: card,
        supp: supp,
      );
      final idx = _records.indexWhere((r) => r.code == original.code);
      if (idx >= 0) {
        _records[idx] = updated;
      }
      notifyListeners();
      return updated;
    }

    if (original.id == null || original.id!.isEmpty) {
      throw Exception('Hồ sơ này không có ID server — không thể cập nhật.');
    }

    final json = await _auth.updateRecord(
      recordId: original.id!,
      extractedData: card.toServerJson(),
      supp: supp,
      isEdited: true,
    );
    final updated = SubmittedRecord.fromServer(json);

    // Cập nhật lại vị trí trong danh sách cục bộ
    final idx = _records.indexWhere((r) => r.id == original.id);
    if (idx >= 0) {
      _records[idx] = updated;
    }
    notifyListeners();
    return updated;
  }

  // ── Đổi mật khẩu (P2 — không OTP) ───────────────────────────────────────

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _auth.changePassword(
      currentPassword: currentPassword,
      newPassword: newPassword,
    );
  }

  static const _recordsNetworkErrorMsg =
      'Không tải được hồ sơ. Kiểm tra kết nối rồi thử lại.';

  static String _today() {
    final now = DateTime.now();

    String two(int n) => n.toString().padLeft(2, '0');

    return '${two(now.day)}/${two(now.month)}/${now.year}';
  }

  void _loginMock() {
    _user = const AuthUser(
      id: 'mock-user',
      username: 'nguyenvana',
      fullName: 'Nguyễn Văn A',
      email: 'nguyenvana@demo.vn',
      role: 'user',
    );
  }

  /// Hồ sơ mẫu chỉ tồn tại ở chế độ mock (`ApiConfig.useMock`). Bản chạy thật
  /// phải khởi động với danh sách trống (lịch sử từ server).
  void seedDemoRecords() {
    final now = DateTime.now();

    String two(int n) => n.toString().padLeft(2, '0');

    final today = '${two(now.day)}/${two(now.month)}/${now.year}';

    final demoCard = IdCardData(
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

    _records.add(SubmittedRecord(
      code: SubmittedRecord.newCode(),
      formId: 'atm_open',
      name: demoCard.fullName,
      date: today,
      card: demoCard,
      supp: const {
        'phone': '0901 234 567',
        'occupation': 'Nhân viên văn phòng',
      },
    ));
    notifyListeners();
  }
}

/// Singleton dùng chung cho toàn app.
final sessionStore = SessionStore();