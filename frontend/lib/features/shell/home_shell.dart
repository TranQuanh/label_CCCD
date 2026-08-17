import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../account/account_tab.dart';
import '../forms/forms_tab.dart';
import '../records/records_tab.dart';

/// Khung chính với 3 tab: Biểu mẫu · Hồ sơ · Tài khoản.
class HomeShell extends StatefulWidget {
  final int initialIndex;
  const HomeShell({super.key, this.initialIndex = 0});

  @override
  State<HomeShell> createState() => HomeShellState();
}

class HomeShellState extends State<HomeShell> {
  late int _index = widget.initialIndex;

  void goToTab(int i) => setState(() => _index = i);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: IndexedStack(
        index: _index,
        children: [
          const FormsTab(),
          RecordsTab(onCreateNew: () => goToTab(0)),
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
                _tab(0, Icons.assignment_outlined, Icons.assignment, 'Biểu mẫu'),
                _tab(1, Icons.folder_outlined, Icons.folder, 'Hồ sơ'),
                _tab(2, Icons.person_outline, Icons.person, 'Tài khoản'),
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
