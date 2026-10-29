import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/form_type.dart';
import '../../data/models/id_card.dart';
import '../../data/session/session_store.dart';
import '../forms/templates/form_template_registry.dart';
import '../review/review_screen.dart';
import '../scan/onboarding_screen.dart';

/// Màn hình xem trước biểu mẫu trước khi bắt đầu quét thẻ hoặc áp dụng Profile.
/// Thiết kế giống hệt PreviewScreen (output) nhưng các trường thông tin để trống.
class FormPreviewScreen extends StatelessWidget {
  final FormType formType;

  const FormPreviewScreen({
    super.key,
    required this.formType,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionStore,
      builder: (context, _) => Scaffold(
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
                'Đây là biểu mẫu bạn sẽ điền. Thông tin CCCD lấy từ ảnh chụp '
                'thẻ, từ Profile đã lưu hoặc nhập thủ công.',
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

  /// 3 cách lấy thông tin CCCD cho hồ sơ mới: quét thẻ, dùng Profile CCCD đã
  /// lưu, hoặc nhập thủ công. Cả 3 đều tới [ReviewScreen] để đối chiếu và
  /// bổ sung trường còn thiếu trước khi xem biểu mẫu hoàn chỉnh.
  Widget _actions(BuildContext context) => Container(
        color: AppColors.navy,
        padding: EdgeInsets.fromLTRB(
            18, 12, 18, MediaQuery.of(context).padding.bottom + 14),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: double.infinity,
              height: 54,
              child: ElevatedButton.icon(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => OnboardingScreen(
                        formType: formType, isForNewProfile: false),
                  ),
                ),
                icon: const Icon(Icons.camera_alt, size: 20),
                label: const Text('Chụp ảnh CCCD',
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
            const SizedBox(height: 10),
            Row(children: [
              Expanded(
                child: _secondaryButton(
                  icon: Icons.badge_outlined,
                  label: 'Dùng Profile',
                  onPressed: () => _chooseProfile(context),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _secondaryButton(
                  icon: Icons.edit_note,
                  label: 'Nhập thủ công',
                  onPressed: () => _openReview(
                    context,
                    // Form trống; quốc tịch điền sẵn giá trị phổ biến nhất.
                    IdCardData(nationality: 'Việt Nam'),
                  ),
                ),
              ),
            ]),
          ],
        ),
      );

  Widget _secondaryButton({
    required IconData icon,
    required String label,
    required VoidCallback onPressed,
  }) =>
      SizedBox(
        height: 50,
        child: OutlinedButton.icon(
          onPressed: onPressed,
          icon: Icon(icon, size: 19),
          label: Text(label,
              style:
                  const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
          style: OutlinedButton.styleFrom(
            foregroundColor: Colors.white,
            side: BorderSide(
                color: Colors.white.withValues(alpha: .4), width: 1.5),
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppRadius.button)),
          ),
        ),
      );

  /// Mở màn đối chiếu với dữ liệu thẻ đã có (từ Profile hoặc form trống).
  void _openReview(BuildContext context, IdCardData card) {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => ReviewScreen(formType: formType, card: card),
    ));
  }

  /// Chọn một Profile CCCD đã lưu để điền hồ sơ. Chỉ ĐỌC profile — sửa ở màn
  /// đối chiếu không làm thay đổi profile gốc.
  void _chooseProfile(BuildContext context) {
    final profiles = sessionStore.profiles;
    if (profiles.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text(
            'Chưa có Profile CCCD nào. Hãy tạo profile ở tab Profile trước.'),
      ));
      return;
    }

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      // `sheetContext` chỉ dùng để đóng sheet; điều hướng dùng `context` của
      // màn xem trước (vẫn còn sống bên dưới sheet).
      builder: (sheetContext) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(
              maxHeight: MediaQuery.of(sheetContext).size.height * .7),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(24, 22, 24, 6),
                child: Text('Chọn Profile CCCD',
                    style: TextStyle(
                        fontSize: 19,
                        fontWeight: FontWeight.w800,
                        color: AppColors.ink)),
              ),
              const Padding(
                padding: EdgeInsets.fromLTRB(24, 0, 24, 10),
                child: Text(
                    'Thông tin profile sẽ được điền sẵn, bạn vẫn có thể sửa trước khi tạo hồ sơ.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12.5, color: AppColors.muted)),
              ),
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                  itemCount: profiles.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (_, i) {
                    final p = profiles[i];
                    return Material(
                      color: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                        side: const BorderSide(color: AppColors.lineSoft),
                      ),
                      child: ListTile(
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14)),
                        leading: CircleAvatar(
                          backgroundColor:
                              AppColors.cobalt.withValues(alpha: .2),
                          child: Text(
                            p.fullName.isNotEmpty
                                ? p.fullName[0].toUpperCase()
                                : '?',
                            style: const TextStyle(
                                fontWeight: FontWeight.w700,
                                color: AppColors.cobalt),
                          ),
                        ),
                        title: Text(
                          p.fullName.isNotEmpty ? p.fullName : 'Chưa có tên',
                          style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              color: AppColors.ink),
                        ),
                        subtitle: Text(
                          p.idNumber.isNotEmpty
                              ? p.idNumber
                              : 'Chưa có số CCCD',
                          style: const TextStyle(color: AppColors.muted),
                        ),
                        trailing: const Icon(Icons.chevron_right,
                            color: AppColors.muted),
                        onTap: () {
                          Navigator.of(sheetContext).pop(); // Đóng sheet
                          // clone() để màn đối chiếu không sửa profile gốc.
                          _openReview(context, p.clone());
                        },
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
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