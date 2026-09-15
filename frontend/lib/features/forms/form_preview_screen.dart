import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/form_type.dart';
import '../../data/models/id_card.dart';
import '../forms/templates/form_template_registry.dart';
import '../scan/onboarding_screen.dart';

/// Màn hình xem trước biểu mẫu trước khi bắt đầu quét thẻ.
/// Thiết kế giống hệt PreviewScreen (output) nhưng các trường thông tin để trống.
class FormPreviewScreen extends StatelessWidget {
  final FormType formType;

  const FormPreviewScreen({
    super.key,
    required this.formType,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF33405C),
      body: Column(
        children: [
          _header(context),
          Expanded(
            child: FormTemplateRegistry.hasTemplate(formType.id)
                ? _buildTemplatePreview()
                : _buildGenericPreview(context),
          ),
          _actions(context),
        ],
      ),
    );
  }

  /// Preview bằng template riêng — trường để trống (mode = preview).
  Widget _buildTemplatePreview() {
    final emptyCard = IdCardData(
      fullName: '', idNumber: '', dob: '', sex: '',
      nationality: '', origin: '', residence: '',
      issueDate: '', expiry: '', issuePlace: '', features: '',
    );
    final template = FormTemplateRegistry.buildPreview(
      formType: formType,
      card: emptyCard,
      supp: const {},
      code: '',
    );
    return ListView(
      padding: const EdgeInsets.all(18),
      children: [
        // Banner giải thích
        Container(
          margin: const EdgeInsets.only(bottom: 14),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: AppColors.star.withValues(alpha: .15),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
                color: AppColors.star.withValues(alpha: .45), width: 1),
          ),
          child: const Row(children: [
            Icon(Icons.info_outline, size: 18, color: AppColors.navy),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                'Đây là biểu mẫu bạn sẽ điền sau khi quét CCCD. '
                'Thông tin sẽ được điền tự động từ thẻ.',
                style: TextStyle(
                    fontSize: 12,
                    color: AppColors.navy,
                    fontWeight: FontWeight.w600),
              ),
            ),
          ]),
        ),
        if (template != null) template,
        const SizedBox(height: 8),
      ],
    );
  }

  /// Preview generic (fallback).
  Widget _buildGenericPreview(BuildContext context) {
    final now = DateTime.now();
    final dateStr =
        'Ngày ${now.day.toString().padLeft(2, '0')} tháng ${now.month.toString().padLeft(2, '0')} năm ${now.year}';

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
                  Text(formType.title.toUpperCase(),
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                          fontSize: 16.5,
                          fontWeight: FontWeight.w900,
                          height: 1.3,
                          color: AppColors.ink)),
                  const SizedBox(height: 5),
                  const Text('Mã hồ sơ: (Cấp tự động sau khi gửi)',
                      style: TextStyle(
                          fontSize: 11,
                          color: AppColors.muted,
                          fontStyle: FontStyle.italic)),
                ]),
              ),
              const SizedBox(height: 18),
              _sectionTitle('I. THÔNG TIN CÔNG DÂN'),
              ...IdCardData.displayOrder.map((e) => _row(e[1], '—')),
              const SizedBox(height: 16),
              _sectionTitle('II. THÔNG TIN BỔ SUNG'),
              if (formType.supp.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 6),
                  child: Text('Không yêu cầu thông tin bổ sung.',
                      style: TextStyle(
                          fontSize: 12.5,
                          color: AppColors.muted,
                          fontStyle: FontStyle.italic)),
                )
              else
                ...formType.supp.map((s) => _row(s.label, '—')),
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
                    const SizedBox(height: 40),
                  ]),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _header(BuildContext context) => Container(
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
                Text('Xem trước biểu mẫu',
                    style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                        color: Colors.white)),
                Text('Yêu cầu thông tin cần quét',
                    style:
                        TextStyle(fontSize: 11.5, color: AppColors.onNavy)),
              ],
            ),
          ),
        ]),
      );

  Widget _actions(BuildContext context) => Container(
        color: AppColors.navy,
        padding: EdgeInsets.fromLTRB(
            18, 12, 18, MediaQuery.of(context).padding.bottom + 14),
        child: SizedBox(
          width: double.infinity,
          height: 54,
          child: ElevatedButton(
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => OnboardingScreen(formType: formType),
              ),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.star,
              foregroundColor: AppColors.navy,
              elevation: 0,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.button)),
            ),
            child: const Text('Bắt đầu quét CCCD',
                style: TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w800)),
          ),
        ),
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