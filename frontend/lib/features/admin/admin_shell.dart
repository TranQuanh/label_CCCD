import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import 'audit_logs_admin_tab.dart';
import 'forms_admin_tab.dart';
import 'records_admin_tab.dart';
import 'users_admin_tab.dart';

/// Quản trị hệ thống (admin-only) — 4 tab: Người dùng · Hồ sơ · Biểu mẫu · Nhật ký.
///
/// Nguyên tắc: admin chỉ thấy thông tin QUẢN LÝ, không thấy nội dung CCCD /
/// Profile / trường bổ sung của người dùng (server không trả cho admin).
///   - Người dùng: danh sách, tìm kiếm, lọc, tạo tài khoản; chi tiết tài khoản
///     (đổi vai trò, khóa/mở khóa, gỡ khóa tạm, đặt lại mật khẩu, đăng xuất mọi
///     thiết bị, xem hồ sơ / nhật ký của tài khoản).
///   - Hồ sơ: danh sách quản lý (mã, biểu mẫu, người tạo, thời gian), lọc, ẩn/hiện.
///   - Biểu mẫu: ẩn / hiện biểu mẫu (không sửa nội dung).
///   - Nhật ký: câu tiếng Việt, nhóm theo ngày, lọc, chi tiết, tải thêm.
/// Mọi thay đổi do backend xử lý và tự ghi nhật ký.
class AdminShell extends StatelessWidget {
  const AdminShell({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        backgroundColor: AppColors.bg,
        appBar: AppBar(
          backgroundColor: AppColors.navy,
          foregroundColor: Colors.white,
          title: const Text('Quản trị hệ thống',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          bottom: const TabBar(
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            indicatorColor: AppColors.star,
            indicatorWeight: 3,
            labelColor: Colors.white,
            unselectedLabelColor: AppColors.onNavy,
            labelStyle: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
            tabs: [
              Tab(icon: Icon(Icons.people_outline, size: 20), text: 'Người dùng'),
              Tab(icon: Icon(Icons.folder_outlined, size: 20), text: 'Hồ sơ'),
              Tab(icon: Icon(Icons.assignment_outlined, size: 20), text: 'Biểu mẫu'),
              Tab(icon: Icon(Icons.history, size: 20), text: 'Nhật ký'),
            ],
          ),
        ),
        body: const TabBarView(
          children: [
            UsersAdminTab(),
            RecordsAdminTab(),
            FormsAdminTab(),
            AuditLogsAdminTab(),
          ],
        ),
      ),
    );
  }
}
