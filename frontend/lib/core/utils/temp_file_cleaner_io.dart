import 'dart:io';

/// Xoá các ảnh tạm (bản sao do camera / image_picker ghi vào cache của app).
///
/// CHỈ xoá file nằm trong thư mục tạm/cache (đường dẫn có thư mục `cache`,
/// `tmp` hoặc `temp`) để không bao giờ xoá ảnh gốc trong thư viện người dùng.
/// Lỗi xoá (file đã mất, không có quyền) được bỏ qua.
///
/// DEF-43: image_picker (Android) chép ảnh gốc vào `cache/<uuid>/` rồi mới tạo
/// bản nén `scaled_*.jpg` cùng thư mục — app chỉ nhận đường dẫn bản nén. Sau
/// khi xoá file, nếu thư mục cha là thư mục riêng của image_picker (tên dạng
/// UUID, nằm NGAY dưới thư mục `cache`) thì xoá luôn cả thư mục đó.
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

/// Dọn file PDF đã chia sẻ ở lần chạy trước (`cache/share/`, do package
/// printing ghi khi `sharePdf`). Gọi lúc khởi động app — KHÔNG xoá ngay sau khi
/// chia sẻ vì ứng dụng nhận (Zalo, email…) có thể chưa đọc xong file.
/// Chỉ chạy khi thư mục tạm hệ thống đúng là thư mục `cache` của app (Android).
Future<void> cleanSharedExports() async {
  try {
    final tmp = Directory.systemTemp;
    if (_baseName(tmp.path).toLowerCase() != 'cache') return;
    final share = Directory('${tmp.path}${Platform.pathSeparator}share');
    if (await share.exists()) await share.delete(recursive: true);
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
