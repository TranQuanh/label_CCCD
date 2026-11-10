import 'dart:async';

import 'package:flutter/material.dart';

import 'core/config/api_config.dart';
import 'core/theme/app_theme.dart';
import 'core/utils/temp_file_cleaner.dart';
import 'data/session/session_store.dart';
import 'features/auth/auth_screen.dart';
import 'features/shell/home_shell.dart';

/// Tắt hiệu ứng kéo dãn (stretch overscroll) trên toàn ứng dụng.
/// Thay bằng ClampingScrollPhysics: cuộn dừng hẳn khi chạm giới hạn.
class _NoStretchScrollBehavior extends ScrollBehavior {
  const _NoStretchScrollBehavior();

  @override
  Widget buildOverscrollIndicator(
      BuildContext context, Widget child, ScrollableDetails details) {
    // Trả về widget con nguyên vẹn — không bọc thêm StretchingOverscrollIndicator.
    return child;
  }

  @override
  ScrollPhysics getScrollPhysics(BuildContext context) {
    // ClampingScrollPhysics: dừng tại giới hạn, không nảy, không kéo dãn.
    return const ClampingScrollPhysics();
  }
}

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
  // Trạng thái đăng nhập ở lần sessionStore thông báo trước — phát hiện lúc
  // phiên chuyển từ "đang đăng nhập" sang "đã thoát".
  bool _wasLoggedIn = false;

  /// Điều hướng/hiện thông báo từ ngoài cây widget (phiên hết hạn ở bất kỳ màn nào).
  final _navigatorKey = GlobalKey<NavigatorState>();
  final _messengerKey = GlobalKey<ScaffoldMessengerState>();

  @override
  void initState() {
    super.initState();
    _wasLoggedIn = sessionStore.isLoggedIn;
    sessionStore.addListener(_onSessionChanged);
    // DEF-43: dọn PDF đã chia sẻ ở lần chạy trước (chứa dữ liệu CCCD).
    unawaited(cleanSharedExports());
    _restore();
  }

  @override
  void dispose() {
    sessionStore.removeListener(_onSessionChanged);
    super.dispose();
  }

  /// Phiên kết thúc KHÔNG do bấm đăng xuất (hết hạn / đổi mật khẩu) → về màn
  /// đăng nhập + thông báo. Đăng xuất thường không có thông báo → bỏ qua, vì
  /// AccountTab đã tự điều hướng (tránh push AuthScreen 2 lần).
  void _onSessionChanged() {
    final now = sessionStore.isLoggedIn;
    final ended = _wasLoggedIn && !now;
    _wasLoggedIn = now;
    if (!ended) return;
    final message = sessionStore.takeSessionEndMessage();
    if (message == null) return;
    _navigatorKey.currentState?.pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const AuthScreen()),
      (r) => false,
    );
    _messengerKey.currentState
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _restore() async {
    // Chế độ mock: chỉ khởi tạo hồ sơ mẫu, không cần token.
    if (ApiConfig.useMock) {
      // login() ở chế độ mock đã tự seed hồ sơ mẫu — gọi thêm ở đây sẽ ra 2 bản.
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
      navigatorKey: _navigatorKey,
      scaffoldMessengerKey: _messengerKey,
      title: 'Định danh SmartID',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      // Tắt hiệu ứng kéo dãn khi cuộn chạm giới hạn.
      scrollBehavior: const _NoStretchScrollBehavior(),
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