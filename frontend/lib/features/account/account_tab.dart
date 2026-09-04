import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/session/session_store.dart';
import '../admin/admin_shell.dart';
import '../auth/auth_screen.dart';
import '../auth/change_password_screen.dart';

/// Tab 3 — Tài khoản: thông tin người dùng + đăng xuất.
///
// P1: thông tin lấy từ server qua `/api/v1/auth/me` ([AuthUser]) — không còn
// `dob` (bảng `tblUser` không có cột này). Thẻ CCCD vẫn hiển thị ở khối riêng
// có nhãn "Từ hồ sơ gần nhất" để không bị hiểu nhầm là danh tính đã xác thực.
///
// Với vai trò `admin` hiện thêm mục "Quản trị hệ thống" (quản lý người dùng +
// nhật ký kiểm toán).
class AccountTab extends StatelessWidget {
  const AccountTab({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionStore,
      builder: (context, _) {
        final name = sessionStore.displayName;
        final accountRows = <List<String>>[
          ['Tên đăng nhập', name.isEmpty ? '—' : sessionStore.user?.username ?? '—'],
          ['Họ và tên', name.isEmpty ? '—' : name],
          ['Email', sessionStore.email.isEmpty ? '—' : sessionStore.email],
          ['Vai trò', _roleLabel(sessionStore.role)],
          ['Số hồ sơ đã tạo', sessionStore.records.length.toString()],
        ];

        return Column(
          children: [
            _header(context, name),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
                children: [
                  _groupLabel('THÔNG TIN TÀI KHOẢN'),
                  _rowCard(accountRows),
                  const SizedBox(height: 18),
                  _groupLabel('BẢO MẬT'),
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(AppRadius.card),
                      border: Border.all(color: AppColors.lineSoft),
                    ),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(AppRadius.card),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                            builder: (_) => const ChangePasswordScreen()),
                      ),
                      child: const Padding(
                        padding:
                            EdgeInsets.symmetric(horizontal: 16, vertical: 15),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('Đổi mật khẩu',
                                style: TextStyle(
                                    fontSize: 13.5,
                                    fontWeight: FontWeight.w600,
                                    color: AppColors.ink)),
                            Icon(Icons.chevron_right,
                                color: Color(0xFFB0BBD2)),
                          ],
                        ),
                      ),
                    ),
                  ),
                  if (sessionStore.user?.isAdmin ?? false) ...[
                    const SizedBox(height: 12),
                    _menuTile(
                      context,
                      icon: Icons.admin_panel_settings_outlined,
                      label: 'Quản trị hệ thống',
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                            builder: (_) => const AdminShell()),
                      ),
                    ),
                  ],
                  const SizedBox(height: 20),
                  SizedBox(
                    height: 52,
                    child: OutlinedButton.icon(
                      onPressed: () => _confirmLogout(context),
                      icon: const Icon(Icons.logout, size: 18),
                      label: const Text('Đăng xuất',
                          style: TextStyle(
                              fontSize: 15, fontWeight: FontWeight.w700)),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.flagRed,
                        backgroundColor: const Color(0xFFFDECEA),
                        side: const BorderSide(
                            color: Color(0xFFF3C6C3), width: 1.5),
                        shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(AppRadius.button)),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  static String _roleLabel(String role) {
    switch (role) {
      case 'admin':
        return 'Quản trị viên';
      case 'operator':
        return 'Cán bộ xử lý';
      case 'viewer':
        return 'Người xem';
      default:
        return role;
    }
  }

  Widget _menuTile(BuildContext context,
          {required IconData icon,
          required String label,
          required VoidCallback onTap}) =>
      Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppRadius.card),
          border: Border.all(color: AppColors.lineSoft),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(AppRadius.card),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
            child: Row(children: [
              Icon(icon, size: 20, color: AppColors.cobalt),
              const SizedBox(width: 12),
              Text(label,
                  style: const TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w600,
                      color: AppColors.ink)),
              const Spacer(),
              const Icon(Icons.chevron_right, color: Color(0xFFB0BBD2)),
            ]),
          ),
        ),
      );

  /// Đăng xuất phải **xoá dữ liệu phiên + token trên thiết bị**, không chỉ điều
  /// hướng. Backend thu hồi refresh token + blacklist access token (best-effort).
  Future<void> _confirmLogout(BuildContext context) async {
    final navigator = Navigator.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Đăng xuất?'),
        content: const Text(
            'Toàn bộ hồ sơ đang lưu trên thiết bị sẽ bị xoá khỏi ứng dụng.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Huỷ')),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Đăng xuất',
                style: TextStyle(color: AppColors.flagRed)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await sessionStore.logout();
    navigator.pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const AuthScreen()),
      (r) => false,
    );
  }

  Widget _header(BuildContext context, String name) => Container(
        width: double.infinity,
        padding: EdgeInsets.fromLTRB(
            24, MediaQuery.of(context).padding.top + 22, 24, 26),
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AppColors.navy, AppColors.navySoft],
          ),
        ),
        child: Column(
          children: [
            Container(
              width: 78,
              height: 78,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: .12),
                border:
                    Border.all(color: AppColors.star.withValues(alpha: .6), width: 2),
              ),
              child: Text(sessionStore.initial,
                  style: const TextStyle(
                      fontSize: 30,
                      fontWeight: FontWeight.w900,
                      color: AppColors.star)),
            ),
            const SizedBox(height: 12),
            Text(name.isEmpty ? 'Chưa đăng nhập' : name,
                style: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w800,
                    color: Colors.white)),
            const SizedBox(height: 3),
            Text(sessionStore.email.isEmpty ? '—' : sessionStore.email,
                style:
                    const TextStyle(fontSize: 12.5, color: AppColors.onNavy)),
          ],
        ),
      );

  Widget _rowCard(List<List<String>> rows) => Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppRadius.card),
          border: Border.all(color: AppColors.lineSoft),
        ),
        child: Column(
          children: [
            for (var i = 0; i < rows.length; i++)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                decoration: BoxDecoration(
                  border: i == rows.length - 1
                      ? null
                      : const Border(
                          bottom: BorderSide(color: Color(0xFFF0F3F9))),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(rows[i][0],
                        style: const TextStyle(
                            fontSize: 13, color: AppColors.muted)),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                          rows[i][1].trim().isEmpty ? '—' : rows[i][1],
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                              fontSize: 13.5,
                              fontWeight: FontWeight.w600,
                              color: AppColors.ink)),
                    ),
                  ],
                ),
              ),
          ],
        ),
      );

  Widget _groupLabel(String t) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text(t,
            style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w800,
                color: AppColors.muted,
                letterSpacing: .6)),
      );
}