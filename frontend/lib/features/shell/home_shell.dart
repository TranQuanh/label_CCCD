import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/session/session_store.dart';
import '../account/account_tab.dart';
import '../forms/forms_tab.dart';
import '../profile/profile_tab.dart';
import '../records/records_tab.dart';

/// Chỉ số các tab của [HomeShell] (đúng thứ tự trên thanh điều hướng).
/// Dùng hằng có tên thay cho số để không mở nhầm tab khi thứ tự thay đổi.
abstract final class HomeTab {
  static const forms = 0;
  static const profile = 1;
  static const records = 2;
  static const account = 3;
}

/// Khung chính với 4 tab: Biểu mẫu · Profile · Hồ sơ · Tài khoản.
///
/// `IndexedStack` dựng sẵn mọi tab nên lịch sử được nạp lại mỗi khi
/// chuyển tab (không phải chỉ lần đầu mở app).
class HomeShell extends StatefulWidget {
  final int initialIndex;
  const HomeShell({super.key, this.initialIndex = HomeTab.forms});

  @override
  State<HomeShell> createState() => HomeShellState();
}

class HomeShellState extends State<HomeShell> {
  late int _index = widget.initialIndex;

  void goToTab(int i) {
    setState(() => _index = i);
    if (i == HomeTab.records) unawaited(sessionStore.loadRecords());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: IndexedStack(
        index: _index,
        children: [
          const FormsTab(),
          ProfileTab(onUseInForms: () => goToTab(HomeTab.forms)),
          RecordsTab(onCreateNew: () => goToTab(HomeTab.forms)),
          const AccountTab(),
        ],
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: AppColors.lineSoft)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 64,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _tab(HomeTab.forms, Icons.assignment_outlined, Icons.assignment, 'Biểu mẫu'),
                _tab(HomeTab.profile, Icons.badge, Icons.badge, 'Profile'),
                _tab(HomeTab.records, Icons.folder_outlined, Icons.folder, 'Hồ sơ'),
                _tab(HomeTab.account, Icons.person_outline, Icons.person, 'Tài khoản'),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _tab(int i, IconData icon, IconData iconActive, String label) {
    final active = _index == i;
    final color = active ? AppColors.navy : AppColors.inactive;
    return Expanded(
      child: InkWell(
        onTap: () => goToTab(i),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(active ? iconActive : icon, size: 22, color: color),
            const SizedBox(height: 4),
            Text(label,
                style: TextStyle(
                    fontSize: 11,
                    fontWeight: active ? FontWeight.w700 : FontWeight.w600,
                    color: color)),
          ],
        ),
      ),
    );
  }
}
