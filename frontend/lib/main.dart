import 'package:flutter/material.dart';

import 'core/config/api_config.dart';
import 'core/theme/app_theme.dart';
import 'data/session/session_store.dart';
import 'features/auth/auth_screen.dart';
import 'features/shell/home_shell.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SmartIdApp());
}

class SmartIdApp extends StatefulWidget {
  const SmartIdApp({super.key});

  @override
  State<SmartIdApp> createState() => _SmartIdAppState();
}

class _SmartIdAppState extends State<SmartIdApp> {
  bool _restored = false;
  bool _loggedIn = false;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    // Chế độ mock: chỉ khởi tạo hồ sơ mẫu, không cần token.
    if (ApiConfig.useMock) {
      sessionStore.seedDemoRecords();
      await sessionStore.login(
          identifier: 'nguyenvana@demo.vn', password: 'demoPass123');
      if (mounted) {
        setState(() {
          _restored = true;
          _loggedIn = true;
        });
      }
      return;
    }
    final ok = await sessionStore.tryAutoLogin();
    if (mounted) {
      setState(() {
        _restored = true;
        _loggedIn = ok;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Định danh SmartID',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      home: _buildHome(),
    );
  }

  Widget _buildHome() {
    if (!_restored) {
      return const Scaffold(
        backgroundColor: AppColors.bg,
        body: Center(child: CircularProgressIndicator()),
      );
    }
    return _loggedIn ? const HomeShell() : const AuthScreen();
  }
}