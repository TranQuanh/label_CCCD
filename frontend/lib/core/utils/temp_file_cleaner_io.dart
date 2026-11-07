import 'dart:io';

/// Xoá các ảnh tạm (bản sao do camera / image_picker ghi vào cache của app).
///
/// CHỈ xoá file nằm trong thư mục tạm/cache (đường dẫn có thư mục `cache`,
/// `tmp` hoặc `temp`) để không bao giờ xoá ảnh gốc trong thư viện người dùng.
/// Lỗi xoá (file đã mất, không có quyền) được bỏ qua.
Future<void> deleteTempImages(Iterable<String?> paths) async {
  for (final path in paths) {
    if (path == null || path.isEmpty || !_isInTempDir(path)) continue;
    try {
      final file = File(path);
      if (await file.exists()) await file.delete();
    } catch (_) {
      // Bỏ qua: dọn dẹp là best-effort.
    }
  }
}

final _tempDirPattern =
    RegExp(r'[/\\](cache|tmp|temp)[/\\]', caseSensitive: false);

bool _isInTempDir(String path) => _tempDirPattern.hasMatch(path);
