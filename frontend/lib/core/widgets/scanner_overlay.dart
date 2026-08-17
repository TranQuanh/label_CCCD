import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Lớp phủ trên CameraPreview:
/// - Làm tối vùng ngoài khung (mask) bằng ClipPath đục lỗ.
/// - Khung chữ nhật đúng tỉ lệ thẻ CCCD, 4 góc vàng nhấp nháy.
/// - Đường quét chạy dọc trong khung.
/// - Dòng nhắc trực quan + chỉ báo mặt trước / mặt sau.
class ScannerOverlay extends StatefulWidget {
  final String hint;
  final bool isBack;
  final bool frontDone;

  const ScannerOverlay({
    super.key,
    required this.hint,
    this.isBack = false,
    this.frontDone = false,
  });

  @override
  State<ScannerOverlay> createState() => _ScannerOverlayState();
}

class _ScannerOverlayState extends State<ScannerOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c;

  @override
  void initState() {
    super.initState();
    _c = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = Size(constraints.maxWidth, constraints.maxHeight);
        final frameW = size.width * .82;
        final frameH = frameW / kCardAspect;
        final rect = Rect.fromCenter(
          center: Offset(size.width / 2, size.height * .44),
          width: frameW,
          height: frameH,
        );
        final rrect = RRect.fromRectAndRadius(rect, const Radius.circular(16));

        return Stack(
          children: [
            // Mask tối
            IgnorePointer(
              child: ClipPath(
                clipper: _HoleClipper(rrect),
                child: Container(color: Colors.black.withOpacity(.72)),
              ),
            ),
            // Khung + đường quét
            Positioned.fromRect(
              rect: rect,
              child: IgnorePointer(
                child: AnimatedBuilder(
                  animation: _c,
                  builder: (_, __) =>
                      CustomPaint(painter: _FramePainter(_c.value)),
                ),
              ),
            ),
            // Dòng nhắc
            Positioned(
              left: 0,
              right: 0,
              top: rect.bottom + 22,
              child: Center(
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                  decoration: BoxDecoration(
                    color: AppColors.navy.withOpacity(.9),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(widget.hint,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 13.5,
                          fontWeight: FontWeight.w600)),
                ),
              ),
            ),
            // Chỉ báo 2 mặt
            Positioned(
              left: 0,
              right: 0,
              top: rect.bottom + 68,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _sideDot(
                    label: 'Mặt trước',
                    text: widget.frontDone ? '✓' : '1',
                    color: widget.isBack ? AppColors.valid : AppColors.star,
                  ),
                  Container(
                    width: 26,
                    height: 2,
                    margin: const EdgeInsets.symmetric(horizontal: 12),
                    color: Colors.white24,
                  ),
                  _sideDot(
                    label: 'Mặt sau',
                    text: '2',
                    color: widget.isBack ? AppColors.star : Colors.white38,
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _sideDot(
          {required String label, required String text, required Color color}) =>
      Row(children: [
        Container(
          width: 22,
          height: 22,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: color, width: 2),
          ),
          child: Text(text,
              style: TextStyle(
                  color: color, fontSize: 11, fontWeight: FontWeight.w800)),
        ),
        const SizedBox(width: 7),
        Text(label,
            style: TextStyle(
                color: color, fontSize: 12, fontWeight: FontWeight.w600)),
      ]);
}

class _FramePainter extends CustomPainter {
  final double progress;
  _FramePainter(this.progress);

  @override
  void paint(Canvas canvas, Size size) {
    const corner = 36.0;
    final p = Paint()
      ..color = AppColors.star
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    // Trên-trái
    canvas.drawLine(const Offset(0, corner), Offset.zero, p);
    canvas.drawLine(Offset.zero, const Offset(corner, 0), p);
    // Trên-phải
    canvas.drawLine(Offset(size.width - corner, 0), Offset(size.width, 0), p);
    canvas.drawLine(Offset(size.width, 0), Offset(size.width, corner), p);
    // Dưới-trái
    canvas.drawLine(Offset(0, size.height - corner), Offset(0, size.height), p);
    canvas.drawLine(Offset(0, size.height), Offset(corner, size.height), p);
    // Dưới-phải
    canvas.drawLine(Offset(size.width - corner, size.height),
        Offset(size.width, size.height), p);
    canvas.drawLine(Offset(size.width, size.height - corner),
        Offset(size.width, size.height), p);

    // Đường quét
    final y = size.height * progress;
    final scan = Paint()
      ..shader = LinearGradient(colors: [
        AppColors.star.withOpacity(0),
        AppColors.star,
        AppColors.star.withOpacity(0),
      ]).createShader(Rect.fromLTWH(0, y - 2, size.width, 4));
    canvas.drawRect(Rect.fromLTWH(8, y, size.width - 16, 3), scan);
  }

  @override
  bool shouldRepaint(_FramePainter old) => old.progress != progress;
}

class _HoleClipper extends CustomClipper<Path> {
  final RRect hole;
  _HoleClipper(this.hole);

  @override
  Path getClip(Size size) => Path.combine(
        PathOperation.difference,
        Path()..addRect(Offset.zero & size),
        Path()..addRRect(hole),
      );

  @override
  bool shouldReclip(_HoleClipper old) => old.hole != hole;
}
