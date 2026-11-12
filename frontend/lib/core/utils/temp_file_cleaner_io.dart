import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Xoá các ảnh tạm (bản sao do camera / image_picker ghi vào cache của app).
///
/// CHỈ xoá file nằm trong thư mục tạm/cache (đường dẫn có thư mục `cache`,
/// `tmp` hoặc `temp`) để không bao giờ xoá ảnh gốc trong thư viện người dùng.
/// Lỗi xoá (file đã mất, không có quyền) được bỏ qua.
///
/// DEF-43a: image_picker (Android, không truyền imageQuality) chép ảnh chọn từ
/// thư viện vào thư mục riêng `cache/<uuid>/<tên>.jpg`. Sau khi xoá file, nếu
/// thư mục cha là thư mục riêng đó (tên dạng UUID, nằm NGAY dưới thư mục
/// `cache`) thì xoá luôn cả thư mục.
Future<void> deleteTempImages(Iterable<String?> paths) async {
  for (final path in paths) {
    if (path == null || path.isEmpty || !_isInTempDir(path)) continue;
    try {
      final file = File(path);
      if (await file.exists()) await file.delete();
      await _deletePickerDir(file.parent);
    } catch (_) {
      // Bỏ qua: dọn dẹp là best-effort.
    }
  }
}

/// Dọn dữ liệu CCCD còn sót từ lần chạy trước. Gọi lúc khởi động app (sau
/// `WidgetsFlutterBinding.ensureInitialized()`).
///
/// - `cache/share/`: PDF do package printing ghi khi `sharePdf`. KHÔNG xoá ngay
///   sau khi chia sẻ vì ứng dụng nhận (Zalo, email…) có thể chưa đọc xong.
/// - `cache/<uuid>/`: bản sao ảnh image_picker còn sót (ví dụ app bị tắt giữa
///   chừng trước khi kịp xoá).
///
/// DEF-43b: lấy thư mục cache bằng `getTemporaryDirectory()` của path_provider
/// (Android: `.../cache`). `Directory.systemTemp` của Dart trên Android lại là
/// `code_cache`, nên bản trước không bao giờ tìm thấy `cache/share`.
Future<void> cleanSharedExports() async {
  try {
    final cache = await getTemporaryDirectory();
    final share = Directory('${cache.path}${Platform.pathSeparator}share');
    if (await share.exists()) await share.delete(recursive: true);

    // Chỉ dọn thư mục con tên dạng UUID nằm ngay dưới thư mục `cache`.
    if (_baseName(cache.path).toLowerCase() != 'cache') return;
    await for (final entry in cache.list(followLinks: false)) {
      if (entry is Directory && _uuidPattern.hasMatch(_baseName(entry.path))) {
        try {
          await entry.delete(recursive: true);
        } catch (_) {}
      }
    }
  } catch (_) {
    // Bỏ qua: dọn dẹp là best-effort.
  }
}

final _tempDirPattern =
    RegExp(r'[/\\](cache|tmp|temp)[/\\]', caseSensitive: false);

final _uuidPattern = RegExp(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    caseSensitive: false);

bool _isInTempDir(String path) => _tempDirPattern.hasMatch(path);

String _baseName(String path) {
  final parts = path.split(RegExp(r'[/\\]')).where((p) => p.isNotEmpty);
  return parts.isEmpty ? '' : parts.last;
}

/// Xoá [dir] nếu và chỉ nếu: tên dạng UUID VÀ thư mục cha tên `cache`.
Future<void> _deletePickerDir(Directory dir) async {
  if (!_uuidPattern.hasMatch(_baseName(dir.path))) return;
  if (_baseName(dir.parent.path).toLowerCase() != 'cache') return;
  if (await dir.exists()) await dir.delete(recursive: true);
}
