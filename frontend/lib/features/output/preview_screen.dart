import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/form_type.dart';
import '../../data/models/id_card.dart';
import '../../data/session/session_store.dart';
import 'pdf_service.dart';
import 'success_screen.dart';

/// Màn hình 6 — Biểu mẫu hoàn chỉnh dạng văn bản hành chính + tải PDF.
///
/// [readOnly] = true khi mở lại một hồ sơ đã gửi từ tab Hồ sơ.
class PreviewScreen extends StatefulWidget {
  final FormType formType;
  final IdCardData card;
  final Map<String, String> supp;
  final String code;
  final bool readOnly;

  const PreviewScreen({
    super.key,
    required this.formType,
    required this.card,
    required this.supp,
    required this.code,
    this.readOnly = false,
  });

  @override
  State<PreviewScreen> createState() => _PreviewScreenState();
}

class _PreviewScreenState extends State<PreviewScreen> {
  /// Chặn bấm "Gửi hồ sơ" hai lần (nút bấm nhanh hoặc quay lại rồi gửi tiếp).
  bool _submitting = false;

  static String _two(int n) => n.toString().padLeft(2, '0');

  /// Xử lý lưu hồ sơ với review status do USER tự kiểm định.
  /// - Nếu user đã review xong → lưu là 'reviewed' (hiện toàn bộ cho user).
  /// - Nếu user chưa review → lưu là 'pending' (chưa review).
  Future<void> _submit() async {
    if (_submitting) return;
    setState(() => _submitting = true);

    // Hỏi user xem đã review xong chưa
    final reviewConfirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Xác nhận review'),
        content: const Text(
            'Bạn đã kiểm tra và sửa chữa thông tin trích xuất chưa?\n'
            'Bấm "Đồng ý" để lưu hồ sơ vào lịch sử (trạng thái: Đã duyệt).\n'
            'Bấm "Hủy" để quay lại review lại tiếp.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Hủy')),
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('Đồng ý', style: TextStyle(color: AppColors.valid))),
        ],
      ),
    );

    if (!mounted) return;
    setState(() => _submitting = false);

    if (reviewConfirmed == null || !reviewConfirmed) return;

// User đã xác nhận review → lưu là 'reviewed' (hiện toàn bộ)
      // (chế độ mock vẫn lưu RAM như cũ)
      try {
        final saved = await sessionStore.submitRecord(
          formType: widget.formType,
          card: widget.card,
          supp: widget.supp,
        );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
        builder: (_) => SuccessScreen(
          formType: widget.formType,
          card: widget.card,
          supp: widget.supp,
          code: saved.code,
        ),
      ));
    } catch (e) {
      if (!mounted) return;
      setState(() => _submitting = false);
      _snack('Không gửi được hồ sơ: $e');
    }
  }

  Future<void> _download() async {
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
      _snack('Không xuất được PDF: $e');
    }
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final dateStr =
        'Ngày ${_two(now.day)} tháng ${_two(now.month)} năm ${now.year}';
    final cardMap = widget.card.toMap();

    return Scaffold(
      backgroundColor: const Color(0xFF33405C),
      body: Column(
        children: [
          _header(),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(18),
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 24, vertical: 26),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(6),
                    boxShadow: [
                      BoxShadow(
                          color: Colors.black.withValues(alpha: .4),
                          blurRadius: 30,
                          offset: const Offset(0, 14)),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Center(
                        child: Column(children: [
                          const Text('CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.ink)),
                          const SizedBox(height: 2),
                          const Text('Độc lập – Tự do – Hạnh phúc',
                              style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.ink)),
                          const SizedBox(height: 6),
                          Container(
                              width: 120, height: 1.5, color: AppColors.ink),
                        ]),
                      ),
                      const SizedBox(height: 16),
                      Center(
                        child: Column(children: [
                          Text(widget.formType.title.toUpperCase(),
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                  fontSize: 16.5,
                                  fontWeight: FontWeight.w900,
                                  height: 1.3,
                                  color: AppColors.ink)),
                          const SizedBox(height: 5),
                          Text('Mã hồ sơ: ${widget.code}',
                              style: const TextStyle(
                                  fontSize: 11,
                                  color: AppColors.muted,
                                  fontFamily: 'monospace')),
                        ]),
                      ),
                      const SizedBox(height: 18),
                      _sectionTitle('I. THÔNG TIN CÔNG DÂN'),
                      ...IdCardData.displayOrder.map((e) => _row(
                          e[1],
                          (cardMap[e[0]] ?? '').trim().isEmpty
                              ? '—'
                              : cardMap[e[0]]!)),
                      const SizedBox(height: 16),
                      _sectionTitle('II. THÔNG TIN BỔ SUNG'),
                      ...widget.formType.supp.map((s) => _row(
                          s.label,
                          (widget.supp[s.key] ?? '').trim().isEmpty
                              ? '—'
                              : widget.supp[s.key]!)),
                      const SizedBox(height: 20),
                      Align(
                        alignment: Alignment.centerRight,
                        child: SizedBox(
                          width: 180,
                          child: Column(children: [
                            Text(dateStr,
                                style: const TextStyle(
                                    fontSize: 11.5,
                                    fontStyle: FontStyle.italic,
                                    color: AppColors.inkSoft)),
                            const SizedBox(height: 4),
                            const Text('NGƯỜI KHAI',
                                style: TextStyle(
                                    fontSize: 12.5,
                                    fontWeight: FontWeight.w700,
                                    color: AppColors.ink)),
                            const Text('(Ký, ghi rõ họ tên)',
                                style: TextStyle(
                                    fontSize: 10.5, color: AppColors.muted)),
                            const SizedBox(height: 26),
                            Text(widget.card.fullName,
                                style: const TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w800,
                                    color: AppColors.navy)),
                          ]),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          _actions(),
        ],
      ),
    );
  }

  Widget _header() => Container(
        width: double.infinity,
        color: AppColors.navy,
        padding: EdgeInsets.fromLTRB(
            18, MediaQuery.of(context).padding.top + 12, 18, 12),
        child: Row(children: [
          InkWell(
            onTap: () => Navigator.of(context).maybePop(),
            borderRadius: BorderRadius.circular(10),
            child: Container(
              width: 34,
              height: 34,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: .12),
                borderRadius: BorderRadius.circular(10),
              ),
              child:
                  const Icon(Icons.arrow_back, size: 18, color: Colors.white),
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Biểu mẫu hoàn chỉnh',
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                        color: Colors.white)),
                Text('Xem trước trước khi tải PDF',
                    style:
                        TextStyle(fontSize: 11.5, color: AppColors.onNavy)),
              ],
            ),
          ),
        ]),
      );

  Widget _actions() => Container(
        color: AppColors.navy,
        padding: EdgeInsets.fromLTRB(
            18, 12, 18, MediaQuery.of(context).padding.bottom + 14),
        child: Row(children: [
          Expanded(
            child: SizedBox(
              height: 54,
              child: ElevatedButton.icon(
                onPressed: _download,
                icon: const Icon(Icons.picture_as_pdf_outlined, size: 20),
                label: const Text('Tải PDF',
                    style:
                        TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.star,
                  foregroundColor: AppColors.navy,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: SizedBox(
              height: 54,
              child: widget.readOnly
                  ? OutlinedButton(
                      onPressed: () => Navigator.of(context).maybePop(),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.white,
                        side: BorderSide(
                            color: Colors.white.withValues(alpha: .35), width: 1.5),
                        shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(AppRadius.button)),
                      ),
                      child: const Text('Xong',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w700)),
                    )
                  : ElevatedButton(
                      onPressed: _submitting ? null : _submit,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.flagRed,
                        disabledBackgroundColor: AppColors.flagRedSoft,
                        foregroundColor: Colors.white,
                        disabledForegroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(AppRadius.button)),
                      ),
                      child: const Text('Gửi hồ sơ',
                          style: TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w700)),
                    ),
            ),
          ),
        ]),
      );

  Widget _sectionTitle(String t) => Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.only(left: 8),
        decoration: const BoxDecoration(
          border: Border(left: BorderSide(color: AppColors.flagRed, width: 3)),
        ),
        child: Text(t,
            style: const TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w800,
                color: AppColors.navy)),
      );

  Widget _row(String label, String value) => Container(
        padding: const EdgeInsets.symmetric(vertical: 6),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: AppColors.lineSoft)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 120,
              child: Text(label,
                  style: const TextStyle(
                      fontSize: 12.5, color: AppColors.muted)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(value,
                  style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      color: AppColors.ink)),
            ),
          ],
        ),
      );
}
