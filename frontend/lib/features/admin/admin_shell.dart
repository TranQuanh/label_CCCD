import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import 'audit_logs_admin_tab.dart';
import 'users_admin_tab.dart';

/// Quản trị hệ thống (admin-only) — 2 tab: Người dùng · Nhật ký kiểm toán.
///
/// Dữ liệu lấy từ `/api/v1/users` và `/api/v1/audit-logs`; mọi thay đổi quyền
/// hoặc khóa tài khoản do backend xử lý và tự ghi audit.
class AdminShell extends StatelessWidget {
  const AdminShell({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        backgroundColor: AppColors.bg,
        appBar: AppBar(
          backgroundColor: AppColors.navy,
          foregroundColor: Colors.white,
          title: const Text('Quản trị hệ thống',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          bottom: const TabBar(
            indicatorColor: AppColors.star,
            indicatorWeight: 3,
            labelColor: Colors.white,
            unselectedLabelColor: AppColors.onNavy,
            labelStyle:
                TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
            tabs: [
              Tab(text: 'Người dùng'),
              Tab(text: 'Nhật ký'),
            ],
          ),
        ),
        body: const TabBarView(
          children: [UsersAdminTab(), AuditLogsAdminTab()],
        ),
      ),
    );
  }
}