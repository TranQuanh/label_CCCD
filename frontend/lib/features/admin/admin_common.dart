import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/api/api_exception.dart';

/// Tiện ích dùng chung cho các màn Quản trị.
///
/// Nguyên tắc: admin chỉ thấy thông tin QUẢN LÝ (tài khoản, mã hồ sơ, biểu mẫu,
/// thời gian, trạng thái) — KHÔNG thấy nội dung CCCD hay trường bổ sung của
/// người dùng. Server cũng không trả các dữ liệu đó cho admin.

/// Nhãn role (chỉ còn 2 role: admin, user).
String roleLabel(String? role) =>
    role == 'admin' ? 'Quản trị viên' : 'Người dùng';

/// Thông điệp lỗi thân thiện từ exception của API.
String adminErrorMessage(Object e) =>
    e is ApiException ? e.userMessage : 'Không kết nối được máy chủ.';

void showAdminSnack(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));
}

String _two(int n) => n.toString().padLeft(2, '0');

/// Chuỗi ISO từ server → DateTime giờ máy (null nếu không parse được).
DateTime? parseServerTime(Object? raw) {
  if (raw == null) return null;
  final t = DateTime.tryParse(raw.toString());
  return t?.toLocal();
}

/// dd/MM/yyyy HH:mm (giờ máy).
String formatDateTime(Object? raw) {
  final t = parseServerTime(raw);
  if (t == null) return raw?.toString() ?? '—';
  return '${_two(t.day)}/${_two(t.month)}/${t.year} '
      '${_two(t.hour)}:${_two(t.minute)}';
}

/// HH:mm (giờ máy).
String formatTime(Object? raw) {
  final t = parseServerTime(raw);
  if (t == null) return '';
  return '${_two(t.hour)}:${_two(t.minute)}';
}

/// YYYY-MM-DD cho tham số lọc của API.
String apiDate(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';

/// dd/MM/yyyy để hiển thị.
String displayDate(DateTime d) => '${_two(d.day)}/${_two(d.month)}/${d.year}';

/// Tiêu đề nhóm ngày: "Hôm nay", "Hôm qua" hoặc dd/MM/yyyy.
String dayHeader(DateTime d) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final day = DateTime(d.year, d.month, d.day);
  final diff = today.difference(day).inDays;
  if (diff == 0) return 'Hôm nay';
  if (diff == 1) return 'Hôm qua';
  return displayDate(day);
}

/// Mô tả một loại hành động trong nhật ký.
class ActionInfo {
  final String label;
  final IconData icon;
  final Color color;

  /// Sự kiện bảo mật (đăng nhập sai, thay đổi tài khoản, ẩn/hiện...).
  final bool security;

  const ActionInfo(this.label, this.icon, this.color, {this.security = false});
}

const _red = AppColors.flagRed;
const _amber = Color(0xFFB08900);
const _green = AppColors.valid;
const _blue = AppColors.cobalt;
const _grey = AppColors.muted;

const Map<String, ActionInfo> _actions = {
  'auth.register': ActionInfo('Đăng ký tài khoản', Icons.person_add_alt, _green),
  'auth.login': ActionInfo('Đăng nhập', Icons.login, _blue),
  'auth.login_failed':
      ActionInfo('Đăng nhập sai', Icons.gpp_bad_outlined, _red, security: true),
  'auth.logout': ActionInfo('Đăng xuất', Icons.logout, _grey),
  'auth.change_password': ActionInfo(
      'Đổi mật khẩu', Icons.password, _amber, security: true),
  'auth.change_password_failed': ActionInfo(
      'Đổi mật khẩu thất bại', Icons.password, _red, security: true),
  'user.create': ActionInfo(
      'Admin tạo tài khoản', Icons.person_add, _amber, security: true),
  'user.update': ActionInfo(
      'Admin cập nhật tài khoản', Icons.manage_accounts, _amber, security: true),
  'user.unlock': ActionInfo(
      'Admin gỡ khóa đăng nhập', Icons.lock_open, _amber, security: true),
  'user.revoke_sessions': ActionInfo(
      'Admin đăng xuất mọi thiết bị', Icons.devices_other, _amber, security: true),
  'user.bootstrap_admin': ActionInfo(
      'Tạo admin đầu tiên', Icons.shield_outlined, _amber, security: true),
  'record.create': ActionInfo('Gửi hồ sơ', Icons.note_add_outlined, _green),
  'record.update': ActionInfo('Sửa hồ sơ', Icons.edit_note, _blue),
  'record.hide': ActionInfo(
      'Admin ẩn hồ sơ', Icons.visibility_off_outlined, _red, security: true),
  'record.show': ActionInfo(
      'Admin hiện lại hồ sơ', Icons.visibility_outlined, _green, security: true),
  'profile.create': ActionInfo('Tạo Profile CCCD', Icons.badge_outlined, _green),
  'profile.update': ActionInfo('Sửa Profile CCCD', Icons.badge_outlined, _blue),
  'profile.delete': ActionInfo('Xoá Profile CCCD', Icons.badge_outlined, _grey),
  'form.hide': ActionInfo(
      'Admin ẩn biểu mẫu', Icons.visibility_off_outlined, _red, security: true),
  'form.show': ActionInfo(
      'Admin hiện lại biểu mẫu', Icons.visibility_outlined, _green, security: true),
};

ActionInfo actionInfo(String action) =>
    _actions[action] ??
    ActionInfo(action, Icons.history, _grey);

/// Diễn giải metadata của nhật ký thành các dòng "nhãn: giá trị" tiếng Việt.
/// Bỏ qua khóa không nên hiển thị (không có PII CCCD trong nhật ký).
List<MapEntry<String, String>> describeMetadata(String action, Object? meta) {
  if (meta is! Map) return const [];
  const labels = {
    'identifier': 'Tên đăng nhập / email',
    'reason': 'Lý do',
    'attempt': 'Lần sai thứ',
    'username': 'Tên đăng nhập',
    'device': 'Thiết bị',
    'code': 'Mã hồ sơ',
    'form_id': 'Biểu mẫu',
    'slug': 'Mã biểu mẫu',
    'name': 'Tên biểu mẫu',
    'role': 'Vai trò mới',
    'is_active': 'Trạng thái',
    'full_name': 'Họ tên tài khoản',
    'password_reset': 'Đặt lại mật khẩu',
    'is_edited': 'Đã sửa tay',
  };
  final out = <MapEntry<String, String>>[];
  meta.forEach((key, value) {
    final k = key.toString();
    String v;
    if (k == 'role') {
      v = roleLabel(value?.toString());
    } else if (k == 'is_active') {
      v = value == true ? 'Mở khóa' : 'Khóa';
    } else if (k == 'reason' && value == 'not_found') {
      v = 'Tài khoản không tồn tại';
    } else if (value is bool) {
      v = value ? 'Có' : 'Không';
    } else {
      v = value?.toString() ?? '';
    }
    if (v.isEmpty) return;
    out.add(MapEntry(labels[k] ?? k, v));
  });
  return out;
}

/// Màn lỗi chung có nút "Thử lại" (đặt trong ListView để vẫn kéo làm mới được).
class AdminErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const AdminErrorView({super.key, required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 60),
        const Icon(Icons.cloud_off, size: 42, color: AppColors.muted),
        const SizedBox(height: 12),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Text(message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.inkSoft)),
        ),
        const SizedBox(height: 16),
        Center(
          child: OutlinedButton(onPressed: onRetry, child: const Text('Thử lại')),
        ),
      ],
    );
  }
}

/// Nhãn trạng thái nhỏ (chip màu).
class StatusPill extends StatelessWidget {
  final String text;
  final Color color;

  const StatusPill(this.text, this.color, {super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .1),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(text,
          style: TextStyle(
              fontSize: 10.5, fontWeight: FontWeight.w800, color: color)),
    );
  }
}

/// Bọc một tab admin thành màn riêng (mở từ chi tiết người dùng: "Hồ sơ của
/// người này", "Nhật ký của người này").
class AdminSubpage extends StatelessWidget {
  final String title;
  final Widget child;

  const AdminSubpage({super.key, required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.navy,
        foregroundColor: Colors.white,
        title: Text(title,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
      ),
      body: child,
    );
  }
}

/// Nút "Tải thêm" ở cuối danh sách có phân trang.
class LoadMoreFooter extends StatelessWidget {
  final int shown;
  final int total;
  final bool loading;
  final VoidCallback onLoadMore;

  const LoadMoreFooter({
    super.key,
    required this.shown,
    required this.total,
    required this.loading,
    required this.onLoadMore,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 4, 14, 24),
      child: Column(children: [
        Text('Đang hiện $shown / $total',
            style: const TextStyle(fontSize: 12, color: AppColors.muted)),
        if (shown < total) ...[
          const SizedBox(height: 8),
          loading
              ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2.5))
              : OutlinedButton(
                  onPressed: onLoadMore, child: const Text('Tải thêm')),
        ],
      ]),
    );
  }
}
