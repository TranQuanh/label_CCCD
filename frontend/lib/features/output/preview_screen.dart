import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/section_label.dart';
import '../../data/models/form_type.dart';
import '../../data/models/id_card.dart';
import '../../data/models/submitted_record.dart';
import '../../data/session/session_store.dart';
import '../forms/templates/form_template_registry.dart';
import '../records/edit_record_screen.dart';
import 'pdf_service.dart';
import 'success_screen.dart';

/// Màn hình 6 — Biểu mẫu hoàn chỉnh dạng văn bản hành chính + tải PDF.
///
/// [readOnly] = true khi mở lại một hồ sơ đã gửi từ tab Hồ sơ.
/// [record] cần được truyền khi [readOnly]=true để bật nút Sửa.
class PreviewScreen extends StatefulWidget {
  final FormType formType;
  final IdCardData card;
  final Map<String, String> supp;
  final String code;
  final bool readOnly;
  /// Hồ sơ gốc — chỉ dùng khi [readOnly]=true (để mở màn hình sửa).
  final SubmittedRecord? record;

  const PreviewScreen({
    super.key,
    required this.formType,
    required this.card,
    required this.supp,
    required this.code,
    this.readOnly = false,
    this.record,
  });

  @override
  State<PreviewScreen> createState() => _PreviewScreenState();
}

class _PreviewScreenState extends State<PreviewScreen> {
  /// Chặn bấm "Gửi hồ sơ" hai lần.
  bool _submitting = false;

  /// Dữ liệu hiển thị hiện tại — có thể cập nhật sau khi sửa.
  late IdCardData _card;
  late Map<String, String> _supp;
  late SubmittedRecord? _record;

  @override
  void initState() {
    super.initState();
    _card = widget.card;
    _supp = widget.supp;
    _record = widget.record;
  }

  static String _two(int n) => n.toString().padLeft(2, '0');

  /// Xử lý lưu hồ sơ với review status do USER tự kiểm định.
  Future<void> _submit() async {
    if (_submitting) return;
    setState(() => _submitting = true);

    final reviewConfirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Xác nhận review'),
        content: const Text(
            'Bạn đã kiểm tra và sửa chữa thông tin trích xuất chưa?\n'
            'Bấm "Đồng ý" để lưu hồ sơ vào lịch sử (trạng thái: Đã duyệt).\n'
            'Bấm "Hủy" để quay lại review tiếp.'),
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

    try {
      final saved = await sessionStore.submitRecord(
        formType: widget.formType,
        card: _card,
        supp: _supp,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
        builder: (_) => SuccessScreen(
          formType: widget.formType,
          card: _card,
          supp: _supp,
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
        card: _card,
        supp: _supp,
        code: widget.code,
      );
    } on PdfExportException catch (e) {
      _snack(e.message);
    } catch (e) {
      _snack('Không xuất được PDF: $e');
    }
  }

  /// Mở màn hình sửa hồ sơ. Khi lưu thành công sẽ cập nhật dữ liệu hiển thị.
  Future<void> _openEdit() async {
    if (_record == null) return;
    // Tạo record tạm với dữ liệu hiện tại (phòng khi đã sửa trước đó).
    final currentRecord = SubmittedRecord(
      id: _record!.id,
      code: _record!.code,
      formId: _record!.formId,
      name: _card.fullName,
      date: _record!.date,
      card: _card,
      supp: _supp,
      reviewStatus: _record!.reviewStatus,
    );
    final result = await Navigator.of(context).push<SubmittedRecord>(
      MaterialPageRoute(
        builder: (_) => EditRecordScreen(
          formType: widget.formType,
          record: currentRecord,
        ),
      ),
    );
    if (result != null && mounted) {
      setState(() {
        _card = result.card;
        _supp = result.supp;
        _record = result;
      });
    }
  }

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  SuppField? _suppFieldByKey(String key) {
    try {
      return widget.formType.supp.firstWhere((sf) => sf.key == key);
    } catch (e) {
      return null;
    }
  }

  List<Widget> _buildSuppFields() {
    final layout = widget.formType.layout;
    if (layout.isEmpty) {
      return widget.formType.supp.map((s) => _suppRow(s)).toList();
    }

    final List<Widget> children = [];
    for (final block in layout) {
      if (block is! Map<String, dynamic>) continue;
      final map = block;
      final type = map['type'] as String?;
      if (type == 'section') {
        final title = (map['title'] as String?) ?? 'Thông tin bổ sung';
        children.add(const SizedBox(height: 6));
        children.add(SectionLabel(
          text: title,
          barColor: AppColors.flagRed,
          textColor: const Color(0xFFB01B15),
        ));
        children.add(const SizedBox(height: 6));
        final fieldsList = map['fields'] as List<dynamic>?;
        if (fieldsList != null) {
          for (final keyObj in fieldsList) {
            final key = keyObj.toString();
            final suppField = _suppFieldByKey(key);
            if (suppField != null) {
              children.add(_suppRow(suppField));
            }
          }
        }
        children.add(const SizedBox(height: 10));
      } else if (type == 'field') {
        final key = (map['key'] as String?) ?? '';
        if (key.isNotEmpty) {
          final suppField = _suppFieldByKey(key);
          if (suppField != null) {
            final labelOverride = map['label'] as String?;
            children.add(_suppRow(suppField, overrideLabel: labelOverride));
          }
        }
      }
    }
    return children;
  }

  Widget _suppRow(SuppField s, {String? overrideLabel}) {
    final value = _supp[s.key] ?? '';
    final isEmpty = value.trim().isEmpty;
    final labelText = overrideLabel ?? s.label;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 6),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.lineSoft)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(labelText,
                style: const TextStyle(
                    fontSize: 12.5, color: AppColors.muted)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(isEmpty ? '—' : value,
                style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: AppColors.ink)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF33405C),
      body: Column(
        children: [
          _header(),
          Expanded(
            child: FormTemplateRegistry.hasTemplate(widget.formType.id)
                ? _buildTemplateOutput()
                : _buildGenericOutput(),
          ),
          _actions(),
        ],
      ),
    );
  }

  /// Render bằng template riêng — bọc trong ListView + padding giống generic.
  Widget _buildTemplateOutput() {
    final template = FormTemplateRegistry.buildOutput(
      formType: widget.formType,
      card: _card,
      supp: _supp,
      code: widget.code,
    );
    return ListView(
      padding: const EdgeInsets.all(18),
      children: [
        if (template != null) template,
        const SizedBox(height: 8),
      ],
    );
  }

  /// Render generic (fallback) cho form chưa có template riêng.
  Widget _buildGenericOutput() {
    final now = DateTime.now();
    final dateStr =
        'Ngày ${_two(now.day)} tháng ${_two(now.month)} năm ${now.year}';
    final cardMap = _card.toMap();

    return ListView(
      padding: const EdgeInsets.all(18),
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 26),
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
              ..._buildSuppFields(),
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
                    Text(_card.fullName,
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
    );
  }

  Widget _header() {
    return Container(
      width: double.infinity,
      color: AppColors.navy,
      padding: EdgeInsets.fromLTRB(
          18, MediaQuery.of(context).padding.top + 12, 18, 12),
      child: Row(
        children: [
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
              child: const Icon(Icons.arrow_back, size: 18, color: Colors.white),
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
                    style: TextStyle(
                        fontSize: 11.5,
                        fontStyle: FontStyle.italic,
                        color: AppColors.onNavy)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _actions() {
    return Container(
      color: AppColors.navy,
      padding: EdgeInsets.fromLTRB(
          18, 12, 18, MediaQuery.of(context).padding.bottom + 14),
      child: widget.readOnly ? _readOnlyActions() : _submitActions(),
    );
  }

  /// Thanh hành động chế độ xem hồ sơ đã tạo: Tải PDF · Sửa · Xong.
  Widget _readOnlyActions() {
    return Row(
      children: [
        // Nút Tải PDF
        SizedBox(
          height: 54,
          child: ElevatedButton.icon(
            onPressed: _download,
            icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
            label: const Text('Tải PDF',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.star,
              foregroundColor: AppColors.navy,
              elevation: 0,
              padding: const EdgeInsets.symmetric(horizontal: 14),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.button)),
            ),
          ),
        ),
        const SizedBox(width: 8),
        // Nút Sửa (chỉ hiển thị nếu có record gốc)
        if (_record != null) ...[
          SizedBox(
            height: 54,
            child: ElevatedButton.icon(
              onPressed: _openEdit,
              icon: const Icon(Icons.edit_outlined, size: 18),
              label: const Text('Sửa',
                  style:
                      TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.cobalt,
                foregroundColor: Colors.white,
                elevation: 0,
                padding: const EdgeInsets.symmetric(horizontal: 14),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadius.button)),
              ),
            ),
          ),
          const SizedBox(width: 8),
        ],
        // Nút Xong
        Expanded(
          child: SizedBox(
            height: 54,
            child: OutlinedButton(
              onPressed: () => Navigator.of(context).maybePop(),
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                side:
                    BorderSide(color: Colors.white.withValues(alpha: .35), width: 1.5),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadius.button)),
              ),
              child: const Text('Xong',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
        ),
      ],
    );
  }

  /// Thanh hành động chế độ gửi hồ sơ mới: Tải PDF · Gửi hồ sơ.
  Widget _submitActions() {
    return Row(
      children: [
        Expanded(
          child: SizedBox(
            height: 54,
            child: ElevatedButton.icon(
              onPressed: _download,
              icon: const Icon(Icons.picture_as_pdf_outlined, size: 20),
              label: const Text('Tải PDF',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
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
            child: ElevatedButton(
              onPressed: _submitting ? null : _submit,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.flagRed,
                disabledBackgroundColor: AppColors.flagRedSoft,
                foregroundColor: Colors.white,
                disabledForegroundColor: Colors.white,
                elevation: 0,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadius.button)),
              ),
              child: const Text('Gửi hồ sơ',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            ),
          ),
        ),
      ],
    );
  }


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