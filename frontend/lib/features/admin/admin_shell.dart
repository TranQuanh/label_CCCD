import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import 'audit_logs_admin_tab.dart';
import 'records_admin_tab.dart';
import 'users_admin_tab.dart';

/// Quản trị hệ thống (admin-only) — 3 tab: Người dùng · Hồ sơ · Nhật ký.
///
/// Dữ liệu lấy từ `/api/v1/users`, `/api/v1/scan-records?all_users=true` và
/// `/api/v1/audit-logs`; mọi thay đổi quyền, khóa tài khoản, ẩn/hiện hồ sơ do
/// backend xử lý và tự ghi audit.
class AdminShell extends StatelessWidget {
  const AdminShell({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
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
              Tab(text: 'Hồ sơ'),
              Tab(text: 'Nhật ký'),
            ],
          ),
        ),
        body: const TabBarView(
          children: [UsersAdminTab(), RecordsAdminTab(), AuditLogsAdminTab()],
        ),
      ),
    );
  }
}