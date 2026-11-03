import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../../core/config/api_config.dart';
import 'api_exception.dart';

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

class CccdApiClient {
  final http.Client _client;
  final String _baseUrl;

  CccdApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? ApiConfig.baseUrl;

  void dispose() => _client.close();

  /// Gửi một ảnh tới `/extract-cccd/?side=...` và trả kết quả đã parse.
  Future<CccdExtractionResult> extract(String imagePath, String side) async {
    final file = File(imagePath);
    if (!await file.exists()) {
      throw ApiException('Không tìm thấy ảnh tại: $imagePath');
    }

    var lastError = const ApiException('Lỗi không xác định khi gọi máy chủ.');
    for (var attempt = 0; attempt <= ApiConfig.maxRetries; attempt++) {
      if (attempt > 0) {
        await Future<void>.delayed(ApiConfig.retryBackoff);
      }
      try {
        // ✅ SỬA TẠI ĐÂY: Truyền ?side=... trực tiếp vào Query Parameter của URI
        final uri = Uri.parse('$_baseUrl${ApiConfig.extractPath}').replace(
          queryParameters: {'side': side},
        );

        final request = http.MultipartRequest('POST', uri)
          ..files.add(
            await http.MultipartFile.fromPath(ApiConfig.fileField, imagePath),
          );

        final streamed =
            await _client.send(request).timeout(ApiConfig.requestTimeout);
        final res = await http.Response.fromStream(streamed);

        final body = utf8.decode(res.bodyBytes);
        final json = _decodeJson(body);
        if (json == null) {
          throw const ApiException('Máy chủ trả về dữ liệu không hợp lệ.');
        }

        final error = json['error'];
        if (error != null && error.toString().isNotEmpty) {
          throw ApiException(error.toString(), statusCode: res.statusCode);
        }

        final data = json['data'];
        return CccdExtractionResult(
          filename: json['filename']?.toString() ?? file.uri.pathSegments.last,
          side: json['side']?.toString() ?? side,
          parseOk: (json['parse_ok'] as bool?) ?? false,
          data: data is Map<String, dynamic> ? data : null,
          raw: json['raw']?.toString(),
        );
      } on ApiException {
        rethrow;
      } on Exception {
        lastError = ApiException(
          'Không kết nối được máy chủ ($_baseUrl). Kiểm tra mạng và thử lại.',
        );
        if (attempt == ApiConfig.maxRetries) {
          throw lastError;
        }
      } catch (_) {
        lastError = const ApiException('Không kết nối được máy chủ. Thử lại sau.');
        if (attempt == ApiConfig.maxRetries) {
          throw lastError;
        }
      }
    }
    throw lastError;
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