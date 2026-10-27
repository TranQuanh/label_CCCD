import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/form_type.dart';
import '../../data/models/id_card.dart';
import '../shell/home_shell.dart';
import 'pdf_service.dart';

/// Màn hình cuối — Gửi hồ sơ thành công.
class SuccessScreen extends StatefulWidget {
  final FormType formType;
  final IdCardData card;
  final Map<String, String> supp;
  final String code;

  const SuccessScreen({
    super.key,
    required this.formType,
    required this.card,
    required this.supp,
    required this.code,
  });

  @override
  State<SuccessScreen> createState() => _SuccessScreenState();
}

class _SuccessScreenState extends State<SuccessScreen> {
  bool _exporting = false;

  /// Sinh PDF rồi mở native share sheet của hệ điều hành
  /// (Zalo, Messenger, email, in, lưu file…).
  Future<void> _share() async {
    if (_exporting) return;
    setState(() => _exporting = true);
    try {
      await PdfService.exportForm(
        formType: widget.formType,
        card: widget.card,
        supp: widget.supp,
        code: widget.code,
      );
    } on PdfExportException catch (e) {
      _snack(e.message);
    } catch (e) {
      _snack('Không chia sẻ được PDF: $e');
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        width: double.infinity,
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AppColors.navy, AppColors.navySoft],
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(40),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  width: 104,
                  height: 104,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: AppColors.valid,
                    boxShadow: [
                      BoxShadow(
                          color: AppColors.valid.withValues(alpha: .5),
                          blurRadius: 36,
                          offset: const Offset(0, 16)),
                    ],
                  ),
                  child:
                      const Icon(Icons.check, size: 52, color: Colors.white),
                ),
                const SizedBox(height: 28),
                const Text('Gửi hồ sơ thành công',
                    style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w900,
                        color: Colors.white)),
                const SizedBox(height: 10),
                Text(
                    '${widget.formType.title} của bạn đã được ghi nhận trên thiết bị.',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        fontSize: 14.5,
                        color: Color(0xFFB7C9EE),
                        height: 1.5)),
                const SizedBox(height: 22),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 18, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: .1),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: Colors.white.withValues(alpha: .2)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text('Mã hồ sơ: ',
                          style:
                              TextStyle(fontSize: 13, color: Colors.white)),
                      Text(widget.code,
                          style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: AppColors.star,
                              fontFamily: 'monospace')),
                    ],
                  ),
                ),
                const SizedBox(height: 30),
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: OutlinedButton.icon(
                    onPressed: _exporting ? null : _share,
                    icon: _exporting
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white),
                          )
                        : const Icon(Icons.share_rounded, size: 20),
                    label: Text(
                        _exporting ? 'Đang tạo PDF…' : 'Chia sẻ biểu mẫu PDF',
                        style: const TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w700)),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: BorderSide(
                          color: Colors.white.withValues(alpha: .4), width: 1.5),
                      shape: RoundedRectangleBorder(
                          borderRadius:
                              BorderRadius.circular(AppRadius.button)),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  height: 54,
                  child: ElevatedButton(
                    onPressed: () => Navigator.of(context).pushAndRemoveUntil(
                      MaterialPageRoute<void>(
                          builder: (_) => const HomeShell(initialIndex: 1)),
                      (r) => false,
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: AppColors.navy,
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                          borderRadius:
                              BorderRadius.circular(AppRadius.button)),
                    ),
                    child: const Text('Về trang chủ',
                        style: TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w700)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
