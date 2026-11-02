import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'token_store.dart';

/// Client HTTP dùng chung cho các endpoint `/api/v1` — tự gắn Bearer token và
/// **tự làm mới token** khi gặp 401.
///
/// Quy ước trả về từ FastAPI (backend P1):
///   - Thành công: HTTP 2xx, body JSON bất kỳ.
///   - Lỗi nghiệp vụ: HTTP 4xx/5xx, body `{"detail": "..."}` (hoặc `message`).
///
/// UTF-8 được decode thủ công (`utf8.decode(bodyBytes)`) — FastAPI không gửi
/// charset, `http` mặc định latin1 làm hỏng dấu tiếng Việt.
class ApiClient {
  final http.Client _client;
  final String baseUrl;

  /// Callback cấp access token mới từ refresh token; trả null nếu refresh thất bại.
  final Future<String?> Function() refreshCallback;

  /// Gọi khi token hết hạn hẳn và không refresh được (ép người dùng đăng nhập lại).
  final void Function()? onSessionExpired;

  String? accessToken;

  ApiClient({
    http.Client? client,
    required this.baseUrl,
    required this.refreshCallback,
    this.onSessionExpired,
  }) : _client = client ?? http.Client();

  void dispose() => _client.close();

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String>? query,
  }) =>
      _request('GET', path, query: query);

  Future<Map<String, dynamic>> post(
    String path, {
    Object? jsonBody,
  }) =>
      _request('POST', path, jsonBody: jsonBody);

  Future<Map<String, dynamic>> put(
    String path, {
    Object? jsonBody,
  }) =>
      _request('PUT', path, jsonBody: jsonBody);

  Future<Map<String, dynamic>> patch(
    String path, {
    Object? jsonBody,
  }) =>
      _request('PATCH', path, jsonBody: jsonBody);

  Future<Map<String, dynamic>> delete(
    String path, {
    Map<String, String>? query,
  }) =>
      _request('DELETE', path, query: query);

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, String>? query,
    Object? jsonBody,
    bool retried = false,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
    final token = accessToken;
    if (token != null) headers['Authorization'] = 'Bearer $token';

    final request = http.Request(method, uri)..headers.addAll(headers);
    if (jsonBody != null) request.body = jsonEncode(jsonBody);

    final streamed = await _client.send(request).timeout(_timeout);
    final res = await http.Response.fromStream(streamed);
    final body = utf8.decode(res.bodyBytes);
    final json = _decodeJson(body);

    if (res.statusCode == 401 && !retried) {
      // Token hết hạn → thử làm mới một lần rồi chơi lại request ban đầu.
      final newAccess = await refreshCallback();
      if (newAccess != null) {
        accessToken = newAccess;
        return _request(method, path,
            query: query, jsonBody: jsonBody, retried: true);
      }
      onSessionExpired?.call();
      throw const ApiException('Phiên đã hết hạn. Vui lòng đăng nhập lại.',
          statusCode: 401);
    }

    if (res.statusCode >= 200 && res.statusCode < 300) {
      if (json == null) {
        throw const ApiException('Máy chủ trả về dữ liệu không hợp lệ.');
      }
      return json;
    }

    throw ApiException(_errorMessage(json, res.statusCode),
        statusCode: res.statusCode);
  }

  /// Giải mã thông điệp lỗi từ body FastAPI (`detail` chuỗi hoặc mảng
  /// validation, hoặc `message`).
  static String _errorMessage(Map<String, dynamic>? json, int statusCode) {
    if (json != null) {
      final detail = json['detail'];
      if (detail is String && detail.isNotEmpty) return detail;
      if (detail is List && detail.isNotEmpty) {
        final first = detail.first;
        if (first is Map) {
          final msg = first['msg']?.toString();
          if (msg != null && msg.isNotEmpty) return msg;
        }
        return detail.first.toString();
      }
      final message = json['message'];
      if (message is String && message.isNotEmpty) return message;
    }
    return 'Lỗi máy chủ ($statusCode). Thử lại sau.';
  }

  Map<String, dynamic>? _decodeJson(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }

  static const _timeout = Duration(seconds: 30);
}

/// Factory xây [ApiClient] nối sẵn vòng làm mới token từ [TokenStore].
ApiClient buildApiClient({
  required String baseUrl,
  required Future<String?> Function() refreshTokens,
  void Function()? onSessionExpired,
  http.Client? client,
}) {
  return ApiClient(
    client: client,
    baseUrl: baseUrl,
    refreshCallback: refreshTokens,
    onSessionExpired: onSessionExpired,
  );
}