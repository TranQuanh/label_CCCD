import 'package:flutter/material.dart';
import '../../data/models/form_type.dart';
import '../../core/theme/app_theme.dart';
import 'camera_screen.dart';

/// Màn hình 3 — Hướng dẫn cầm/chụp thẻ trước khi mở camera.
class OnboardingScreen extends StatelessWidget {
  final FormType formType;
  const OnboardingScreen({super.key, required this.formType});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
                22, MediaQuery.of(context).padding.top + 10, 22, 0),
            child: Row(children: [
              InkWell(
                onTap: () => Navigator.of(context).maybePop(),
                borderRadius: BorderRadius.circular(10),
                child: Container(
                  width: 36,
                  height: 36,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppColors.line, width: 1.5),
                  ),
                  child: const Icon(Icons.arrow_back,
                      size: 18, color: AppColors.navy),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Hướng dẫn quét thẻ',
                        style: TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w800,
                            color: AppColors.ink)),
                    Text(formType.title,
                        style: const TextStyle(
                            fontSize: 12, color: AppColors.muted)),
                  ],
                ),
              ),
            ]),
          ),
          // Minh họa
          Container(
            height: 200,
            margin: const EdgeInsets.fromLTRB(24, 18, 24, 0),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(18),
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [AppColors.navy, AppColors.cobalt],
              ),
            ),
            child: Center(
              child: Transform.rotate(
                angle: -.07,
                child: Container(
                  width: 186,
                  height: 118,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    color: Colors.white,
                    border: Border.all(
                        color: Colors.white.withValues(alpha: .6), width: 2),
                    boxShadow: [
                      BoxShadow(
                          color: Colors.black.withValues(alpha: .4),
                          blurRadius: 30,
                          offset: const Offset(0, 16)),
                    ],
                  ),
                  child: Row(children: [
                    Container(
                      width: 40,
                      height: 52,
                      decoration: BoxDecoration(
                        color: const Color(0xFFC6D2E8),
                        borderRadius: BorderRadius.circular(6),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _bar(.8, AppColors.flagRed),
                          const SizedBox(height: 6),
                          _bar(.95, const Color(0xFFC6D2E8)),
                          const SizedBox(height: 6),
                          _bar(.7, const Color(0xFFC6D2E8)),
                        ],
                      ),
                    ),
                  ]),
                ),
              ),
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 16),
              children: [
                const Row(children: [
                  Text('Bạn sẽ quét 2 mặt thẻ:',
                      style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: AppColors.ink)),
                  SizedBox(width: 9),
                  _Pill(text: 'Mặt trước + Mặt sau'),
                ]),
                const SizedBox(height: 14),
                _tip('Đủ ánh sáng, không bị lóa',
                    'Tránh ánh sáng chiếu trực tiếp lên mặt thẻ'),
                const SizedBox(height: 13),
                _tip('Đặt thẻ trên nền tối, phẳng',
                    'Giúp app nhận diện viền thẻ dễ dàng'),
                const SizedBox(height: 13),
                _tip('Thẻ nằm trọn trong khung',
                    'Chụp lần lượt mặt trước rồi mặt sau'),
              ],
            ),
          ),
          Padding(
            padding: EdgeInsets.fromLTRB(
                24, 0, 24, MediaQuery.of(context).padding.bottom + 22),
            child: SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton.icon(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                      builder: (_) => CameraScreen(formType: formType)),
                ),
                icon: const Icon(Icons.photo_camera_outlined, size: 20),
                label: const Text('Bắt đầu quét mặt trước',
                    style:
                        TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.navy,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  static Widget _bar(double w, Color c) => FractionallySizedBox(
        widthFactor: w,
        child: Container(
          height: 7,
          decoration: BoxDecoration(
              color: c, borderRadius: BorderRadius.circular(3)),
        ),
      );

  static Widget _tip(String title, String sub) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 28,
            height: 28,
            alignment: Alignment.center,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: Color(0xFFE7F6ED),
            ),
            child: const Icon(Icons.check, size: 16, color: AppColors.valid),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w600,
                        color: AppColors.ink)),
                const SizedBox(height: 2),
                Text(sub,
                    style: const TextStyle(
                        fontSize: 12.5, color: AppColors.muted)),
              ],
            ),
          ),
        ],
      );
}

class _Pill extends StatelessWidget {
  final String text;
  const _Pill({required this.text});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
        decoration: BoxDecoration(
          color: AppColors.tint,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text(text,
            style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: AppColors.cobalt)),
      );
}
