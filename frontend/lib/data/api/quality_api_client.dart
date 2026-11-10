import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
// XFile đọc được ảnh trên cả mobile lẫn web — KHÔNG dùng dart:io.
import 'package:image_picker/image_picker.dart' show XFile;

import '../../core/config/api_config.dart';
import '../../core/image_quality/image_quality.dart';
import 'auth_api_client.dart';
import 'token_store.dart';

/// Kết quả kiểm tra chất lượng ảnh / khung thẻ từ server (OpenCV).
class ServerQualityResult {
  final List<QualityIssue> issues;

  /// Server có nhận ra khung thẻ không (null = không xác định được).
  final bool? cardFound;

  const ServerQualityResult({required this.issues, this.cardFound});
}

/// Client gọi `POST /api/v1/quality-check` (bắt buộc đăng nhập).
///
/// Chỉ để CẢNH BÁO: mọi lỗi (mạng, timeout, backend cũ chưa có endpoint → 404,
/// 5xx, server chưa cài OpenCV → `available=false`) đều trả `null`, không ném.
/// Cùng mẫu token với `CccdApiClient`: 401 → làm mới token một lần; refresh bị
/// từ chối → gọi hook [AuthApiClient.onSessionExpired]. Không retry.
class QualityApiClient {
  final http.Client _client;
  final String _baseUrl;

  QualityApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? ApiConfig.baseUrl;

  void dispose() => _client.close();

  /// [side]: `ApiConfig.sideFront` (truoc) hoặc `ApiConfig.sideBack` (sau).
  Future<ServerQualityResult?> checkQuality(
    String imagePath, {
    required String side,
  }) async {
    if (ApiConfig.useMock) return null;
    try {
      final xfile = XFile(imagePath);
      final bytes = await xfile.readAsBytes();
      final filename = _fileName(xfile, imagePath);

      var res = await _send(bytes, filename, side);
      if (res.statusCode == 401) {
        // Access token hết hạn → làm mới một lần rồi gửi lại.
        final auth = AuthApiClient();
        String? newAccess;
        try {
          newAccess = await auth.refreshAccessToken();
        } catch (_) {
          // Lỗi mạng khi refresh → bỏ qua kiểm tra, không coi là hết phiên.
          return null;
        } finally {
          auth.dispose();
        }
        if (newAccess == null) {
          AuthApiClient.onSessionExpired?.call();
          return null;
        }
        res = await _send(bytes, filename, side);
      }
      if (res.statusCode < 200 || res.statusCode >= 300) return null;

      final json = jsonDecode(utf8.decode(res.bodyBytes));
      if (json is! Map || json['available'] != true) return null;

      final rawIssues = json['issues'];
      final issues = <QualityIssue>[];
      if (rawIssues is List) {
        for (final e in rawIssues) {
          final issue = QualityIssue.fromJson(e);
          if (issue != null) issues.add(issue);
        }
      }
      final cardFound = json['card_found'];
      return ServerQualityResult(
        issues: issues,
        cardFound: cardFound is bool ? cardFound : null,
      );
    } catch (_) {
      // Timeout / lỗi kết nối / JSON hỏng... → coi như chưa kiểm tra được.
      return null;
    }
  }

  /// Gửi một request multipart kèm Bearer token mới nhất (timeout ngắn).
  Future<http.Response> _send(
    Uint8List bytes,
    String filename,
    String side,
  ) async {
    final uri = Uri.parse('$_baseUrl${ApiConfig.qualityCheckPath}').replace(
      queryParameters: {'side': side},
    );
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
        await _client.send(request).timeout(ApiConfig.qualityCheckTimeout);
    return http.Response.fromStream(streamed)
        .timeout(ApiConfig.qualityCheckTimeout);
  }

  /// Tên file gửi lên server (web: path là blob URL, không có tên thật).
  static String _fileName(XFile xfile, String path) {
    if (xfile.name.isNotEmpty) return xfile.name;
    final segments = path.split(RegExp(r'[/\\]'));
    final last = segments.isEmpty ? '' : segments.last;
    return last.isEmpty ? 'cccd.jpg' : last;
  }
}
