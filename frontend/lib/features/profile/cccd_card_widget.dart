import 'dart:math' as math;
import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/id_card.dart';

/// Thẻ CCCD kỹ thuật số (Digital Vietnamese ID Card) mô phỏng chân thực thẻ Căn cước công dân.
///
/// Hỗ trợ lật mượt mà giữa Mặt trước và Mặt sau bằng hiệu ứng 3D Transform hoặc chọn qua tab.
class CccdCardWidget extends StatefulWidget {
  final IdCardData card;
  final VoidCallback? onEdit;
  final bool showFlipButton;

  const CccdCardWidget({
    super.key,
    required this.card,
    this.onEdit,
    this.showFlipButton = true,
  });

  @override
  State<CccdCardWidget> createState() => _CccdCardWidgetState();
}

class _CccdCardWidgetState extends State<CccdCardWidget>
    with SingleTickerProviderStateMixin {
  late final AnimationController _flipCtrl;
  late final Animation<double> _flipAnim;
  bool _isBack = false;

  @override
  void initState() {
    super.initState();
    _flipCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 500),
    );
    _flipAnim = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _flipCtrl, curve: Curves.easeInOutCubic),
    );
  }

  @override
  void dispose() {
    _flipCtrl.dispose();
    super.dispose();
  }

  void _toggleFlip() {
    if (_isBack) {
      _flipCtrl.reverse();
    } else {
      _flipCtrl.forward();
    }
    setState(() => _isBack = !_isBack);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        GestureDetector(
          onTap: _toggleFlip,
          child: AnimatedBuilder(
            animation: _flipAnim,
            builder: (context, _) {
              final val = _flipAnim.value;
              final isUnder = val >= 0.5;
              final angle = val * math.pi;

              return Transform(
                alignment: Alignment.center,
                transform: Matrix4.identity()
                  ..setEntry(3, 2, 0.001) // perspective
                  ..rotateY(angle),
                child: isUnder
                    ? Transform(
                        alignment: Alignment.center,
                        transform: Matrix4.identity()..rotateY(math.pi),
                        child: _buildBackCard(),
                      )
                    : _buildFrontCard(),
              );
            },
          ),
        ),
        if (widget.showFlipButton) ...[
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _sideSelector(
                label: 'Mặt trước',
                icon: Icons.credit_card,
                selected: !_isBack,
                onTap: () {
                  if (_isBack) _toggleFlip();
                },
              ),
              const SizedBox(width: 8),
              _sideSelector(
                label: 'Mặt sau',
                icon: Icons.flip,
                selected: _isBack,
                onTap: () {
                  if (!_isBack) _toggleFlip();
                },
              ),
              if (widget.onEdit != null) ...[
                const SizedBox(width: 8),
                InkWell(
                  onTap: widget.onEdit,
                  borderRadius: BorderRadius.circular(20),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: AppColors.line),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.edit_outlined,
                            size: 14, color: AppColors.cobalt),
                        SizedBox(width: 4),
                        Text('Sửa',
                            style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                color: AppColors.cobalt)),
                      ],
                    ),
                  ),
                ),
              ],
            ],
          ),
        ],
      ],
    );
  }

  Widget _sideSelector({
    required String label,
    required IconData icon,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(20),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? AppColors.navy : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
              color: selected ? AppColors.navy : AppColors.lineSoft),
          boxShadow: selected
              ? [
                  BoxShadow(
                    color: AppColors.navy.withValues(alpha: .2),
                    blurRadius: 8,
                    offset: const Offset(0, 3),
                  ),
                ]
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon,
                size: 14, color: selected ? Colors.white : AppColors.muted),
            const SizedBox(width: 6),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: selected ? Colors.white : AppColors.inkSoft,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// MẶT TRƯỚC THẺ CCCD
  Widget _buildFrontCard() {
    final c = widget.card;
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFFEAF2FD),
            Color(0xFFF6FAFF),
            Color(0xFFE2ECFC),
          ],
        ),
        border: Border.all(color: const Color(0xFFBED2F4), width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppColors.navy.withValues(alpha: .14),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
          BoxShadow(
            color: Colors.black.withValues(alpha: .04),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(15),
        child: Stack(
          children: [
            // Hoa văn nền chìm
            Positioned(
              right: -30,
              bottom: -30,
              child: Opacity(
                opacity: 0.05,
                child: Container(
                  width: 200,
                  height: 200,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                    color: AppColors.navy,
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Quốc hiệu & Tiêu ngữ
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Quốc huy cách điệu
                      Container(
                        width: 38,
                        height: 38,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: const LinearGradient(
                            colors: [AppColors.flagRed, Color(0xFFC01B14)],
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: AppColors.flagRed.withValues(alpha: .3),
                              blurRadius: 6,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        child: const Icon(Icons.star,
                            size: 22, color: AppColors.star),
                      ),
                      const SizedBox(width: 10),
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            Text(
                              'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM',
                              style: TextStyle(
                                fontSize: 10.5,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFFB01B15),
                                letterSpacing: .2,
                              ),
                            ),
                            Text(
                              'Độc lập - Tự do - Hạnh phúc',
                              style: TextStyle(
                                fontSize: 9.5,
                                fontWeight: FontWeight.w700,
                                color: AppColors.ink,
                              ),
                            ),
                            SizedBox(height: 2),
                            Text(
                              'CĂN CƯỚC CÔNG DÂN',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w900,
                                color: AppColors.navy,
                                letterSpacing: .5,
                              ),
                            ),
                            Text(
                              'IDENTITY CARD',
                              style: TextStyle(
                                fontSize: 8.5,
                                fontWeight: FontWeight.w600,
                                color: AppColors.muted,
                                fontStyle: FontStyle.italic,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  // Thân thẻ: Ảnh + Số + Thông tin
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Cột trái: Ảnh đại diện + Chip
                      Column(
                        children: [
                          Container(
                            width: 82,
                            height: 104,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(8),
                              color: const Color(0xFFD6E2F5),
                              border: Border.all(
                                  color: const Color(0xFFADC6EB), width: 1.5),
                            ),
                            child: Stack(
                              alignment: Alignment.center,
                              children: [
                                const Icon(Icons.person,
                                    size: 46, color: Color(0xFF7A97C2)),
                                Positioned(
                                  bottom: 4,
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color:
                                          Colors.black.withValues(alpha: .5),
                                      borderRadius: BorderRadius.circular(4),
                                    ),
                                    child: const Text('CCCD CHIP',
                                        style: TextStyle(
                                            color: Colors.white,
                                            fontSize: 7,
                                            fontWeight: FontWeight.w700)),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 8),
                          // Chip kim loại
                          Container(
                            width: 36,
                            height: 26,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(4),
                              gradient: const LinearGradient(
                                colors: [
                                  Color(0xFFE8C868),
                                  Color(0xFFD4AF37),
                                  Color(0xFFF5DE88),
                                ],
                              ),
                              border: Border.all(
                                  color: const Color(0xFFB89320), width: 1),
                            ),
                            child: const Center(
                              child: Icon(Icons.memory,
                                  size: 16, color: Color(0xFF6B5310)),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(width: 14),
                      // Cột phải: Các thông tin chi tiết
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Số CCCD
                            Row(
                              children: [
                                const Text('Số / No.: ',
                                    style: TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.w600,
                                        color: AppColors.muted)),
                                Expanded(
                                  child: Text(
                                    c.idNumber.isEmpty ? '—' : c.idNumber,
                                    style: const TextStyle(
                                      fontSize: 15,
                                      fontWeight: FontWeight.w900,
                                      color: Color(0xFFB01B15),
                                      fontFamily: 'monospace',
                                      letterSpacing: .5,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            // Họ và tên
                            _item(
                              'Họ và tên / Full name:',
                              c.fullName.isEmpty
                                  ? '—'
                                  : c.fullName.toUpperCase(),
                              isBold: true,
                              textColor: AppColors.navy,
                            ),
                            _item('Ngày sinh / Date of birth:',
                                c.dob.isEmpty ? '—' : c.dob),
                            Row(
                              children: [
                                Expanded(
                                  child: _item(
                                      'Giới tính / Sex:',
                                      c.sex.isEmpty ? '—' : c.sex),
                                ),
                                Expanded(
                                  child: _item(
                                      'Quốc tịch / Nat.:',
                                      c.nationality.isEmpty
                                          ? 'Việt Nam'
                                          : c.nationality),
                                ),
                              ],
                            ),
                            _item('Quê quán / Place of origin:',
                                c.origin.isEmpty ? '—' : c.origin,
                                maxLines: 2),
                            _item('Nơi thường trú / Residence:',
                                c.residence.isEmpty ? '—' : c.residence,
                                maxLines: 2),
                            _item('Có giá trị đến / Expiry:',
                                c.expiry.isEmpty ? 'Không thời hạn' : c.expiry),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// MẶT SAU THẺ CCCD
  Widget _buildBackCard() {
    final c = widget.card;
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFFE8F1FC),
            Color(0xFFF3F7FD),
            Color(0xFFDFECFA),
          ],
        ),
        border: Border.all(color: const Color(0xFFBED2F4), width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppColors.navy.withValues(alpha: .14),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(15),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Tiêu đề mặt sau
              const Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'ĐẶC ĐIỂM NHẬN DẠNG & THÔNG TIN CẤP',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                      color: AppColors.navy,
                      letterSpacing: .3,
                    ),
                  ),
                  Icon(Icons.shield_outlined,
                      size: 16, color: AppColors.cobalt),
                ],
              ),
              const Divider(color: Color(0xFFC8DAF3), height: 14),
              const SizedBox(height: 2),
              // Đặc điểm nhận dạng
              _item(
                'Đặc điểm nhận dạng / Personal identification:',
                c.features.isEmpty ? 'Không có' : c.features,
                maxLines: 2,
              ),
              const SizedBox(height: 4),
              // Ngày cấp & Nơi cấp
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    flex: 4,
                    child: _item(
                      'Ngày cấp / Date of issue:',
                      c.issueDate.isEmpty ? '—' : c.issueDate,
                    ),
                  ),
                  Expanded(
                    flex: 6,
                    child: _item(
                      'Nơi cấp / Place of issue:',
                      c.issuePlace.isEmpty ? '—' : c.issuePlace,
                      maxLines: 2,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              // Vùng mã vạch MRZ (Machine Readable Zone) mô phỏng
              Container(
                width: double.infinity,
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: .85),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: const Color(0xFFCAD8EE)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _formatMrzLine1(c),
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 9.5,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF2B3A55),
                        letterSpacing: 1.2,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _formatMrzLine2(c),
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 9.5,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF2B3A55),
                        letterSpacing: 1.2,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _formatMrzLine3(c),
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        fontSize: 9.5,
                        fontWeight: FontWeight.w700,
                        color: Color(0xFF2B3A55),
                        letterSpacing: 1.2,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _item(String label, String value,
      {bool isBold = false, Color? textColor, int maxLines = 1}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(
                  fontSize: 9.5,
                  fontWeight: FontWeight.w500,
                  color: AppColors.muted)),
          Text(
            value,
            maxLines: maxLines,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: isBold ? 12.5 : 11,
              fontWeight: isBold ? FontWeight.w800 : FontWeight.w600,
              color: textColor ?? AppColors.ink,
              height: 1.2,
            ),
          ),
        ],
      ),
    );
  }

  String _formatMrzLine1(IdCardData c) {
    final num = c.idNumber.padRight(12, '<');
    return 'IDVNM$num<<<<<<<<<<<<<<<<<<';
  }

  String _formatMrzLine2(IdCardData c) {
    final sexChar = c.sex.toLowerCase().contains('nam') ? 'M' : 'F';
    return '0000000${sexChar}0000000VNM<<<<<<<<<<<0';
  }

  String _formatMrzLine3(IdCardData c) {
    final rawName = c.fullName.toUpperCase().replaceAll(' ', '<');
    return rawName.padRight(30, '<').substring(0, 30);
  }
}
