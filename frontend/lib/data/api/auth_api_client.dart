import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/config/api_config.dart';
import '../models/auth_user.dart';
import 'api_client.dart';
import 'api_exception.dart';
import 'token_store.dart';

/// Client xác thực (`/api/v1/auth/*`) + quản lý tài khoản (`/api/v1/users`) +
/// nhật ký kiểm toán (`/api/v1/audit-logs`) + hồ sơ (`/api/v1/scan-records`) +
/// danh mục biểu mẫu (`/api/v1/forms`) + Profile CCCD (`/api/v1/profiles`).
///
// Là nơi DUY NHẤT biết các endpoint của app API; các nơi khác gọi qua
// [AuthApiClient] chứ không hardcode đường dẫn.
class AuthApiClient {
  final http.Client _http;
  final String _baseUrl;
  late final ApiClient _api;

  /// Hook dùng chung cho MỌI instance (các tab admin tự tạo [AuthApiClient]
  /// riêng): gọi khi token hết hạn hẳn và không refresh được. [SessionStore]
  /// đăng ký hook này để xoá phiên cục bộ và đưa người dùng về màn đăng nhập.
  static void Function()? onSessionExpired;

  AuthApiClient({http.Client? client, String? baseUrl})
      : _http = client ?? http.Client(),
        _baseUrl = baseUrl ?? ApiConfig.baseUrl {
    _api = ApiClient(
      client: _http,
      baseUrl: _baseUrl,
      refreshCallback: refreshAccessToken,
      // Đọc hook lúc gọi (không chụp lúc tạo) để instance tạo trước khi
      // SessionStore đăng ký vẫn dùng được.
      onSessionExpired: () => AuthApiClient.onSessionExpired?.call(),
    );
  }

  void dispose() => _http.close();

  /// Cấp access token mới từ refresh token (dùng cho auto-refresh trong
  /// [ApiClient] và auto-login khi mở app).
  ///
  /// Trả null khi không có refresh token hoặc server TỪ CHỐI (401/403: token
  /// bị thu hồi/hết hạn, tài khoản bị khoá). Lỗi mạng/timeout/5xx → ném lại để
  /// nơi gọi không nhầm thành "phiên hết hạn" và xoá token oan.
  Future<String?> refreshAccessToken() async {
    final refresh = await TokenStore.readRefreshToken();
    if (refresh == null) return null;
    try {
      final body = await _postPublic('/api/v1/auth/refresh', {
        'refresh_token': refresh,
      });
      final access = body['data']?['access_token']?.toString();
      if (access != null && access.isNotEmpty) {
        await TokenStore.saveAccess(access);
        return access;
      }
      return null;
    } on ApiException catch (e) {
      if (e.statusCode == 401 || e.statusCode == 403) return null;
      rethrow;
    }
  }

  Future<Map<String, dynamic>> _postPublic(String path, Object jsonBody) async {
    final res = await _http
        .post(
          Uri.parse('$_baseUrl$path'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(jsonBody),
        )
        .timeout(ApiConfig.requestTimeout);
    final body = utf8.decode(res.bodyBytes);
    final json = _tryDecode(body);
    if (res.statusCode >= 200 && res.statusCode < 300 && json != null) {
      return json;
    }
    throw ApiException(_errorMessage(json), statusCode: res.statusCode);
  }

  Map<String, dynamic>? _tryDecode(String body) {
    try {
      final d = jsonDecode(body);
      return d is Map<String, dynamic> ? d : null;
    } catch (_) {
      return null;
    }
  }

  String _errorMessage(Map<String, dynamic>? json) {
    if (json != null) {
      final detail = json['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
      final message = json['message'];
      if (message is String && message.isNotEmpty) return message;
    }
    return 'Không kết nối được máy chủ. Thử lại sau.';
  }

  // ── Auth ────────────────────────────────────────────────────────────────

  Future<AuthUser> register({
    required String username,
    required String email,
    required String password,
    required String fullName,
  }) async {
    final body = await _postPublic('/api/v1/auth/register', {
      'username': username,
      'email': email,
      'password': password,
      'full_name': fullName,
    });
    final data = body['data'] as Map<String, dynamic>? ?? {};
    await _saveTokens(data);
    return _userFromData(data);
  }

  Future<AuthUser> login({
    required String identifier,
    required String password,
  }) async {
    final body = await _postPublic('/api/v1/auth/login', {
      'identifier': identifier,
      'password': password,
      'device_info': 'SmartID Flutter',
    });
    final data = body['data'] as Map<String, dynamic>? ?? {};
    await _saveTokens(data);
    return _userFromData(data);
  }

  /// Đăng xuất: gọi server thu hồi refresh token + blacklist access, rồi LUÔN
  /// xoá token trên máy (finally) — kể cả khi không còn access token, access
  /// hết hạn (401), lỗi mạng. Không bao giờ ném lỗi ra UI.
  ///
  /// Gọi qua [_api] để access hết hạn được tự refresh rồi gửi lại (server vẫn
  /// thu hồi được refresh token). Refresh thất bại trong lúc này sẽ gọi hook
  /// onSessionExpired → `SessionStore.expireSession` bỏ qua vì
  /// `SessionStore.logout` đã đặt `_expiring = true` trước khi gọi hàm này.
  Future<void> logout() async {
    try {
      final access = await TokenStore.readAccessToken();
      final refresh = await TokenStore.readRefreshToken();
      // Không còn token nào → không có gì để thu hồi trên server.
      if (access == null && refresh == null) return;
      await _api.post('/api/v1/auth/logout');
    } catch (_) {
      // Logout là best-effort — lỗi mạng/401 không được chặn việc xoá phiên cục bộ.
    } finally {
      await TokenStore.clear();
    }
  }

  Future<AuthUser> me() async {
    final body = await _api.get('/api/v1/auth/me');
    return _userFromData(body);
  }

  static Future<void> _saveTokens(Map<String, dynamic> data) async {
    final access = data['access_token']?.toString();
    final refresh = data['refresh_token']?.toString();
    if (access != null && access.isNotEmpty && refresh != null && refresh.isNotEmpty) {
      await TokenStore.save(access, refresh);
    }
  }

  static AuthUser _userFromData(Map<String, dynamic> data) {
    return AuthUser(
      id: data['user_id']?.toString() ?? '',
      username: data['username']?.toString() ?? '',
      fullName: data['full_name']?.toString() ?? '',
      email: data['email']?.toString() ?? '',
      role: data['role']?.toString() ?? 'user',
    );
  }

  // ── Users (admin) ───────────────────────────────────────────────────────

  Future<List<Map<String, dynamic>>> listUsers() async {
    final body = await _api.get('/api/v1/users');
    final list = body['users'];
    return list is List ? list.cast<Map<String, dynamic>>() : <Map<String, dynamic>>[];
  }

  Future<void> createUser({
    required String username,
    required String email,
    required String password,
    String fullName = '',
    String role = 'user',
  }) async {
    await _api.post('/api/v1/users', jsonBody: {
      'username': username,
      'email': email,
      'password': password,
      'full_name': fullName,
      'role': role,
    });
  }

  Future<void> updateUser(String userId, Map<String, dynamic> changes) async {
    await _api.put('/api/v1/users/$userId', jsonBody: changes);
  }

  /// Admin: chi tiết TÀI KHOẢN (không có Profile CCCD / nội dung hồ sơ).
  Future<Map<String, dynamic>> getUser(String userId) {
    return _api.get('/api/v1/users/$userId');
  }

  /// Admin: gỡ khóa tạm do đăng nhập sai nhiều lần.
  Future<void> unlockUser(String userId) async {
    await _api.post('/api/v1/users/$userId/unlock');
  }

  /// Admin: đăng xuất tài khoản khỏi mọi thiết bị.
  Future<void> revokeUserSessions(String userId) async {
    await _api.post('/api/v1/users/$userId/revoke-sessions');
  }

  // ── Audit (admin) ───────────────────────────────────────────────────────

  /// Nhật ký có lọc + phân trang. `actionGroup`: auth|user|record|profile|form.
  /// `startDate`/`endDate` dạng YYYY-MM-DD (end tính trọn ngày).
  Future<AdminPage> listAuditLogs({
    String? userId,
    String? targetId,
    String? actionType,
    String? actionGroup,
    bool securityOnly = false,
    String? startDate,
    String? endDate,
    int limit = 50,
    int offset = 0,
  }) async {
    final body = await _api.get('/api/v1/audit-logs', query: {
      if (userId != null) 'user_id': userId,
      if (targetId != null) 'target_id': targetId,
      if (actionType != null) 'action_type': actionType,
      if (actionGroup != null) 'action_group': actionGroup,
      if (securityOnly) 'security_only': 'true',
      if (startDate != null) 'start_date': startDate,
      if (endDate != null) 'end_date': endDate,
      'limit': limit.toString(),
      'offset': offset.toString(),
    });
    return AdminPage.fromBody(body, 'logs');
  }

  // ── Forms ───────────────────────────────────────────────────────────────

  Future<List<Map<String, dynamic>>> listForms() async {
    final body = await _api.get('/api/v1/forms');
    final list = body['forms'];
    return list is List ? list.cast<Map<String, dynamic>>() : <Map<String, dynamic>>[];
  }

  /// Admin: mọi biểu mẫu (kể cả đang ẩn) + `record_count`.
  /// Biểu mẫu KHÔNG được tạo / sửa trên app — chỉ ẩn / hiện.
  Future<List<Map<String, dynamic>>> listAllForms() async {
    final body = await _api.get('/api/v1/forms/all');
    return _mapList(body['forms']);
  }

  /// Admin: ẩn / hiện biểu mẫu. Trả biểu mẫu sau khi cập nhật.
  Future<Map<String, dynamic>> setFormActive(String slug, bool active) {
    return _api.patch('/api/v1/forms/$slug/visibility',
        jsonBody: {'is_active': active});
  }

  static List<Map<String, dynamic>> _mapList(Object? list) => list is List
      ? list.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
      : <Map<String, dynamic>>[];

  // ── Scan records (P2) ───────────────────────────────────────────────────

  /// Gửi hồ sơ lên server; trả `{record_id, code}` — mã hồ sơ do SERVER cấp.
  /// `extractedData` phải là map snake_case tiếng Việt (xem `toServerJson`).
  Future<Map<String, String>> submitRecord({
    required String formId,
    required Map<String, dynamic> extractedData,
    required Map<String, String> supp,
    required String cardSide,
    bool parseOk = true,
    bool isEdited = false,
  }) async {
    final body = await _api.post('/api/v1/scan-records', jsonBody: {
      'form_id': formId,
      'extracted_data': extractedData,
      'supp': supp,
      'card_side': cardSide,
      'parse_ok': parseOk,
      'is_edited': isEdited,
    });
    return {
      'record_id': body['record_id']?.toString() ?? '',
      'code': body['code']?.toString() ?? '',
    };
  }

  /// Tải lịch sử hồ sơ.
  Future<List<Map<String, dynamic>>> listRecords({
    int limit = 50,
    int offset = 0,
  }) async {
    final body = await _api.get('/api/v1/scan-records', query: {
      'limit': limit.toString(),
      'offset': offset.toString(),
    });
    final list = body['records'];
    return list is List ? list.cast<Map<String, dynamic>>() : <Map<String, dynamic>>[];
  }

  Future<Map<String, dynamic>> getRecord(String recordId) async {
    return _api.get('/api/v1/scan-records/$recordId');
  }

  /// Cập nhật hồ sơ đã gửi (PATCH). Trả về record sau khi cập nhật.
  /// [extractedData] phải là map snake_case tiếng Việt (xem `toServerJson`).
  Future<Map<String, dynamic>> updateRecord({
    required String recordId,
    required Map<String, dynamic> extractedData,
    required Map<String, String> supp,
    bool parseOk = true,
    bool isEdited = true,
  }) async {
    return _api.patch('/api/v1/scan-records/$recordId', jsonBody: {
      'extracted_data': extractedData,
      'supp': supp,
      'parse_ok': parseOk,
      'is_edited': isEdited,
    });
  }

  // ── Scan records (admin) ────────────────────────────────────────────────

  /// Admin: danh sách QUẢN LÝ hồ sơ của mọi người dùng. Server KHÔNG trả nội
  /// dung CCCD / trường bổ sung — chỉ mã, biểu mẫu, người tạo, thời gian,
  /// `is_hidden`, `form_active`. `status`: all|visible|hidden|form_hidden.
  Future<AdminPage> listAllRecords({
    String? userId,
    String? formId,
    String status = 'all',
    String? query,
    String? startDate,
    String? endDate,
    int limit = 50,
    int offset = 0,
  }) async {
    final body = await _api.get('/api/v1/scan-records', query: {
      'all_users': 'true',
      if (userId != null) 'user_id': userId,
      if (formId != null) 'form_id': formId,
      'status': status,
      if (query != null && query.trim().isNotEmpty) 'q': query.trim(),
      if (startDate != null) 'start_date': startDate,
      if (endDate != null) 'end_date': endDate,
      'limit': limit.toString(),
      'offset': offset.toString(),
    });
    return AdminPage.fromBody(body, 'records');
  }

  /// Admin: ẩn / hiện một hồ sơ với chủ hồ sơ. Trả record sau khi cập nhật.
  Future<Map<String, dynamic>> setRecordHidden(String recordId, bool hidden) {
    return _api.patch('/api/v1/scan-records/$recordId/visibility', jsonBody: {
      'is_hidden': hidden,
    });
  }

  // ── Đổi mật khẩu (P2 — không OTP) ───────────────────────────────────────

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    await _api.post('/api/v1/auth/change-password', jsonBody: {
      'current_password': currentPassword,
      'new_password': newPassword,
    });
  }

  // ── Profile CCCD (`/api/v1/profiles`, bảng tblCccdProfile) ──────────────
  //
  // Mỗi profile server: `{id, data, created_at, updated_at}` với `data` là map
  // snake_case (xem `IdCardData.toServerJson`). Các profile ngang hàng, không
  // có profile "mặc định". Trùng số CCCD → ApiException 409.

  /// Danh sách profile của user hiện tại (cũ → mới).
  Future<List<Map<String, dynamic>>> listProfiles() async {
    final body = await _api.get('/api/v1/profiles');
    final list = body['profiles'];
    return list is List ? list.cast<Map<String, dynamic>>() : <Map<String, dynamic>>[];
  }

  /// Tạo profile mới; trả profile server vừa tạo (có `id`).
  Future<Map<String, dynamic>> createProfile(Map<String, dynamic> data) {
    return _api.post('/api/v1/profiles', jsonBody: {'data': data});
  }

  /// Cập nhật dữ liệu một profile; trả profile server sau khi cập nhật.
  Future<Map<String, dynamic>> updateProfile(
    String id,
    Map<String, dynamic> data,
  ) {
    return _api.put('/api/v1/profiles/$id', jsonBody: {'data': data});
  }

  /// Xoá một profile.
  Future<void> deleteProfile(String id) async {
    await _api.delete('/api/v1/profiles/$id');
  }
}

/// Một trang kết quả của API admin có phân trang (`total` = tổng số dòng khớp
/// bộ lọc, dùng cho nút "Tải thêm").
class AdminPage {
  final List<Map<String, dynamic>> items;
  final int total;

  const AdminPage(this.items, this.total);

  factory AdminPage.fromBody(Map<String, dynamic> body, String key) {
    final raw = body[key];
    final items = raw is List
        ? raw.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
        : <Map<String, dynamic>>[];
    final total = body['total'];
    return AdminPage(items, total is int ? total : items.length);
  }
}
