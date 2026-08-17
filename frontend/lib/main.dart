import 'package:flutter/material.dart';

import 'core/config/api_config.dart';
import 'core/theme/app_theme.dart';
import 'data/session/session_store.dart';
import 'features/auth/auth_screen.dart';

void main() {
  // Hồ sơ mẫu chỉ tồn tại ở chế độ mock. Bản chạy thật khởi động với danh sách
  // hồ sơ trống — dữ liệu giả trong app e-KYC dễ bị hiểu là hồ sơ đã nộp thật.
  if (ApiConfig.useMock) {
    sessionStore.seedDemoRecords();
  }
  runApp(const SmartIdApp());
}

class SmartIdApp extends StatelessWidget {
  const SmartIdApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Định danh SmartID',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      home: const AuthScreen(),
    );
  }
}
