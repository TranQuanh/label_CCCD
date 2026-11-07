import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
// XFile (package:cross_file, re-export qua image_picker) đọc được ảnh trên cả
// mobile lẫn web — KHÔNG dùng dart:io để file này chạy được trên Flutter Web.
import 'package:image_picker/image_picker.dart' show XFile;

import '../../core/config/api_config.dart';
import 'api_exception.dart';
import 'auth_api_client.dart';
import 'token_store.dart';

/// Kết quả một lần trích xuất một mặt thẻ (từ API `/extract-cccd/`).
class CccdExtractionResult {
  final String filename;
  final String side;
  final bool parseOk;
  final Map<String, dynamic>? data;
  final String? raw;

  const CccdExtractionResult({
    required this.filename,
    required this.side,
    required this.parseOk,
    this.data,
    this.raw,
  });
}

/// Client gọi proxy trích xuất `/extract-cccd/` của backend.
///
/// Endpoint bắt buộc đăng nhập: gửi `Authorization: Bearer <access>`; gặp 401
/// thì làm mới token một lần qua [AuthApiClient.refreshAccessToken] rồi gửi lại.
/// Chỉ dùng ở chế độ thật — chế độ mock không gọi tới client này.
class CccdApiClient {
  final http.Client _client;
  final String _baseUrl;

  CccdApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? ApiConfig.baseUrl;

  void dispose() => _client.close();

  static const _expiredMsg = 'Phiên đã hết hạn. Vui lòng đăng nhập lại.';

  /// Gửi một ảnh tới `/extract-cccd/?side=...` và trả kết quả đã parse.
  Future<CccdExtractionResult> extract(String imagePath, String side) async {
    final xfile = XFile(imagePath);
    final bytes = await _readBytes(xfile);
    final filename = _fileName(xfile, imagePath);

    var res = await _sendWithRetry(bytes, filename, side);
    if (res.statusCode == 401) {
      // Access token hết hạn → làm mới một lần rồi gửi lại.
      final auth = AuthApiClient();
      String? newAccess;
      try {
        newAccess = await auth.refreshAccessToken();
      } catch (_) {
        throw ApiException(
          'Không kết nối được máy chủ ($_baseUrl). Kiểm tra mạng và thử lại.',
        );
      } finally {
        auth.dispose();
      }
      if (newAccess == null) {
        AuthApiClient.onSessionExpired?.call();
        throw const ApiException(_expiredMsg, statusCode: 401);
      }
      res = await _sendWithRetry(bytes, filename, side);
      if (res.statusCode == 401) {
        throw const ApiException(_expiredMsg, statusCode: 401);
      }
    }

    final body = utf8.decode(res.bodyBytes);
    final json = _decodeJson(body);

    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw ApiException(_errorMessage(json, res.statusCode),
          statusCode: res.statusCode);
    }
    if (json == null) {
      throw const ApiException('Máy chủ trả về dữ liệu không hợp lệ.');
    }

    final error = json['error'];
    if (error != null && error.toString().isNotEmpty) {
      throw ApiException(error.toString(), statusCode: res.statusCode);
    }

    final data = json['data'];
    return CccdExtractionResult(
      filename: json['filename']?.toString() ?? filename,
      side: json['side']?.toString() ?? side,
      parseOk: (json['parse_ok'] as bool?) ?? false,
      data: data is Map<String, dynamic> ? data : null,
      raw: json['raw']?.toString(),
    );
  }

  /// Gửi request multipart (kèm Bearer token mới nhất). Chỉ thử lại khi lỗi
  /// kết nối ([http.ClientException]); timeout thì báo lỗi ngay — ảnh có thể
  /// đã tới GPU server, gửi lại chỉ làm hàng đợi dài thêm.
  Future<http.Response> _sendWithRetry(
    Uint8List bytes,
    String filename,
    String side,
  ) async {
    final uri = Uri.parse('$_baseUrl${ApiConfig.extractPath}').replace(
      queryParameters: {'side': side},
    );

    for (var attempt = 0;; attempt++) {
      if (attempt > 0) {
        await Future<void>.delayed(ApiConfig.retryBackoff);
      }
      try {
        final request = http.MultipartRequest('POST', uri)
          ..files.add(
            http.MultipartFile.fromBytes(
              ApiConfig.fileField,
              bytes,
              filename: filename,
            ),
          );
        final token = await TokenStore.readAccessToken();
        if (token != null) {
          request.headers['Authorization'] = 'Bearer $token';
        }

        final streamed =
            await _client.send(request).timeout(ApiConfig.requestTimeout);
        return await http.Response.fromStream(streamed)
            .timeout(ApiConfig.requestTimeout);
      } on TimeoutException {
        throw const ApiException(
          'Máy chủ phản hồi quá lâu. Vui lòng thử lại sau.',
        );
      } on http.ClientException {
        if (attempt >= ApiConfig.maxRetries) {
          throw ApiException(
            'Không kết nối được máy chủ ($_baseUrl). Kiểm tra mạng và thử lại.',
          );
        }
      } on ApiException {
        rethrow;
      } on Exception {
        // Dự phòng: http < 1.1 không bọc SocketException thành ClientException
        // → xử lý như lỗi kết nối để giữ thông báo thân thiện.
        if (attempt >= ApiConfig.maxRetries) {
          throw ApiException(
            'Không kết nối được máy chủ ($_baseUrl). Kiểm tra mạng và thử lại.',
          );
        }
      }
    }
  }

  static Future<Uint8List> _readBytes(XFile xfile) async {
    try {
      return await xfile.readAsBytes();
    } catch (_) {
      throw const ApiException('Không đọc được ảnh đã chụp. Vui lòng chụp lại.');
    }
  }

  /// Tên file gửi lên server (web: path là blob URL, không có tên thật).
  static String _fileName(XFile xfile, String path) {
    if (xfile.name.isNotEmpty) return xfile.name;
    final segments = path.split(RegExp(r'[/\\]'));
    final last = segments.isEmpty ? '' : segments.last;
    return last.isEmpty ? 'cccd.jpg' : last;
  }

  /// Thông điệp lỗi từ body FastAPI (`detail` chuỗi hoặc mảng validation,
  /// hoặc `error`/`message`).
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
        return first.toString();
      }
      for (final key in const ['error', 'message']) {
        final v = json[key];
        if (v is String && v.isNotEmpty) return v;
      }
    }
    return 'Lỗi máy chủ ($statusCode)';
  }

  Map<String, dynamic>? _decodeJson(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map<String, dynamic> ? decoded : null;
    } catch (_) {
      return null;
    }
  }
}
