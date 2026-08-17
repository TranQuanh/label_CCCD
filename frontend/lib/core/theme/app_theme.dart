import 'package:flutter/material.dart';

/// Bảng màu — phong cách ứng dụng dịch vụ công Việt Nam.
class AppColors {
  const AppColors._();

  static const navy = Color(0xFF0A2A66); // Nền header, nút phụ
  static const navySoft = Color(0xFF123A86); // Gradient
  static const cobalt = Color(0xFF1656C4); // Focus, liên kết
  static const flagRed = Color(0xFFDA251D); // Nút hành động chính
  static const flagRedSoft = Color(0xFFE08A85);
  static const star = Color(0xFFF6D24B); // Điểm nhấn
  static const bg = Color(0xFFF4F6FB);
  static const card = Color(0xFFFFFFFF);
  static const ink = Color(0xFF1A2438);
  static const inkSoft = Color(0xFF41506E);
  static const muted = Color(0xFF6B7896);
  static const hint = Color(0xFF8A97B2);
  static const line = Color(0xFFCBD5E8);
  static const lineSoft = Color(0xFFE1E7F2);
  static const tint = Color(0xFFEAF0FB);
  static const valid = Color(0xFF16A34A);
  static const warn = Color(0xFFEA580C);
  static const onNavy = Color(0xFF9FB6E6);
  static const inactive = Color(0xFF98A4BD);
}

class AppRadius {
  const AppRadius._();

  static const field = 12.0;
  static const button = 14.0;
  static const card = 14.0;
}

/// Tỉ lệ thẻ CCCD chuẩn (85.6mm x 53.98mm) — dùng cho khung quét.
const double kCardAspect = 1.585;

ThemeData buildAppTheme() => ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: AppColors.bg,
      colorScheme: ColorScheme.fromSeed(seedColor: AppColors.navy),
    );
