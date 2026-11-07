/// Xoá ảnh CCCD tạm sau khi dùng xong.
///
/// Conditional import: mobile/desktop (có `dart:io`) dùng bản thật, web dùng
/// bản rỗng (ảnh web là blob trong bộ nhớ trình duyệt, không có file để xoá).
/// Hàm: `Future<void> deleteTempImages(Iterable<String?> paths)`.
library;

export 'temp_file_cleaner_stub.dart'
    if (dart.library.io) 'temp_file_cleaner_io.dart';