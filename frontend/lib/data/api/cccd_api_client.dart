<<<<<<< HEAD
import 'dart:async';
=======
>>>>>>> 8593503 (add data)
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../../core/config/api_config.dart';
import 'api_exception.dart';

<<<<<<< HEAD
/// Client HTTP tới backend FastAPI trong `backend/main.py`.
///
/// Hợp đồng thật (đối chiếu trực tiếp với code backend):
///
///   POST {base}/extract-cccd/?side=truoc|sau|auto
///   multipart/form-data, field tên **`file`** (một ảnh mỗi request)
///
///   → 200 {"filename","side","parse_ok",
///          "data":{"so_cccd","ho_va_ten",...,"mat_the"},
///          "raw":null,"latency_ms":12345.6}
///   → 200 {"filename","error":"..."}        ← lỗi cũng trả 200, phải tự kiểm
///
/// Hai điểm dễ sai, đã xử lý ở đây:
///
/// 1. **Luôn truyền `side` tường minh.** Với `side=auto` backend suy mặt thẻ từ
///    *tên file*; ảnh do `CameraController.takePicture()` sinh ra có tên kiểu
///    `CAP1234.jpg`, không chứa token `front`/`back` ⇒ suy ra `unknown` ⇒ bị từ
///    chối. App luôn biết mình đang chụp mặt nào nên phải nói thẳng.
/// 2. **Giải mã UTF-8 thủ công.** FastAPI trả `application/json` không kèm
///    charset; `http` khi đó mặc định latin1, làm hỏng toàn bộ dấu tiếng Việt
///    (`Nguyễn` → `NguyÃªn`). Phải dùng `utf8.decode(res.bodyBytes)`.
class CccdApiClient {
  final http.Client _client;
  final String baseUrl;

  CccdApiClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ?? ApiConfig.baseUrl;

  /// Trích xuất một mặt thẻ. Trả về khối `data` đã parse.
  Future<Map<String, dynamic>> extractSide({
    required File image,
    required bool isFront,
  }) async {
    final side = isFront ? ApiConfig.sideFront : ApiConfig.sideBack;
    final uri = Uri.parse('$baseUrl${ApiConfig.extractPath}')
        .replace(queryParameters: {'side': side});

    final body = await _sendWithRetry(uri, image, isFront);

    if (body['error'] != null) {
      // Backend từ chối có lý do (vd: model chưa có adapter cho mặt này).
      throw ApiException(ApiErrorKind.rejected, body['error'].toString());
    }
    if (body['parse_ok'] != true || body['data'] == null) {
      final raw = (body['raw'] ?? '').toString();
      throw ApiException(
        ApiErrorKind.badResponse,
        'Model không trả về JSON hợp lệ cho mặt '
        '${isFront ? 'trước' : 'sau'}.${raw.isEmpty ? '' : '\n$raw'}',
      );
    }
    return Map<String, dynamic>.from(body['data'] as Map);
  }

  Future<Map<String, dynamic>> _sendWithRetry(
    Uri uri,
    File image,
    bool isFront,
  ) async {
    ApiException? last;
    for (var attempt = 0; attempt <= ApiConfig.maxRetries; attempt++) {
      try {
        return await _sendOnce(uri, image, isFront);
      } on ApiException catch (e) {
        last = e;
        if (!e.retryable || attempt == ApiConfig.maxRetries) rethrow;
        await Future<void>.delayed(ApiConfig.retryBackoff * (attempt + 1));
      }
    }
    throw last!;
  }

  Future<Map<String, dynamic>> _sendOnce(
    Uri uri,
    File image,
    bool isFront,
  ) async {
    final request = http.MultipartRequest('POST', uri);
    // Tên file cũng mang token front/back để `side=auto` vẫn suy đúng nếu ai đó
    // gọi lại endpoint mà quên truyền `side`.
    request.files.add(
      await http.MultipartFile.fromPath(
        ApiConfig.fileField,
        image.path,
        filename: isFront ? 'cccd_front.jpg' : 'cccd_back.jpg',
      ),
    );

    http.Response response;
    try {
      final streamed =
          await _client.send(request).timeout(ApiConfig.requestTimeout);
      response = await http.Response.fromStream(streamed)
          .timeout(ApiConfig.requestTimeout);
    } on TimeoutException {
      throw const ApiException(ApiErrorKind.timeout, 'Hết thời gian chờ.');
    } on SocketException catch (e) {
      throw ApiException(ApiErrorKind.network, e.message);
    } on http.ClientException catch (e) {
      throw ApiException(ApiErrorKind.network, e.message);
    }

    if (response.statusCode != 200) {
      throw ApiException(
        ApiErrorKind.server,
        _shorten(utf8.decode(response.bodyBytes, allowMalformed: true)),
        statusCode: response.statusCode,
      );
    }

    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is! Map) {
        throw const ApiException(
            ApiErrorKind.badResponse, 'Phản hồi không phải object JSON.');
      }
      return Map<String, dynamic>.from(decoded);
    } on FormatException catch (e) {
      throw ApiException(ApiErrorKind.badResponse, e.message);
    }
  }

  /// `GET /health` — dùng để báo sớm "server chưa nạp model" thay vì để người
  /// dùng chụp xong 2 ảnh rồi mới biết.
  Future<Map<String, dynamic>> health() async {
    final uri = Uri.parse('$baseUrl${ApiConfig.healthPath}');
    try {
      final res =
          await _client.get(uri).timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) {
        throw ApiException(ApiErrorKind.server, 'health ${res.statusCode}',
            statusCode: res.statusCode);
      }
      return Map<String, dynamic>.from(
          jsonDecode(utf8.decode(res.bodyBytes)) as Map);
    } on TimeoutException {
      throw const ApiException(ApiErrorKind.timeout, 'health timeout');
    } on SocketException catch (e) {
      throw ApiException(ApiErrorKind.network, e.message);
    }
  }

  static String _shorten(String s) =>
      s.length <= 300 ? s : '${s.substring(0, 300)}…';

  void close() => _client.close();
}
=======
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
>>>>>>> 8593503 (add data)
