import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Lưu trữ token trên thiết bị qua Secure Storage (Keychain/Keystore).
///
/// Access token dùng ngay; refresh token dùng để tự đăng nhập lại khi mở app
/// và để xin access token mới khi hết hạn. Không lưu user trong secure storage
/// — khi cần thì gọi `/api/v1/auth/me`.
class TokenStore {
  static const _storage = FlutterSecureStorage();
  static const _kAccess = 'auth_access_token';
  static const _kRefresh = 'auth_refresh_token';
  static const _kProfiles = 'user_cccd_profiles';

  static Future<String?> readAccessToken() => _storage.read(key: _kAccess);

  static Future<String?> readRefreshToken() => _storage.read(key: _kRefresh);

  static Future<String?> readProfiles([String? userId]) =>
      _storage.read(key: userId != null ? '${_kProfiles}_$userId' : _kProfiles);

  static Future<void> saveProfiles(String jsonStr, [String? userId]) =>
      _storage.write(
        key: userId != null ? '${_kProfiles}_$userId' : _kProfiles,
        value: jsonStr,
      );

  static Future<void> deleteProfiles([String? userId]) =>
      _storage.delete(key: userId != null ? '${_kProfiles}_$userId' : _kProfiles);


  static Future<void> save(String access, String refresh) async {
    await _storage.write(key: _kAccess, value: access);
    await _storage.write(key: _kRefresh, value: refresh);
  }

  static Future<void> saveAccess(String access) =>
      _storage.write(key: _kAccess, value: access);

  static Future<void> clear() async {
    await _storage.delete(key: _kAccess);
    await _storage.delete(key: _kRefresh);
  }
}