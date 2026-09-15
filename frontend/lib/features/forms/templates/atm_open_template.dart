import 'package:flutter/material.dart';

import 'form_template_registry.dart';
import 'form_widgets.dart';

/// Template biểu mẫu Đăng ký mở thẻ ATM.
///
/// Bố cục:
///   - Tiêu đề quốc gia + tên biểu mẫu
///   - Phần I: Thông tin cá nhân (từ CCCD mặt trước + sau)
///   - Phần II: Thông tin tài khoản (nghề nghiệp, SĐT)
///   - Phần III: Cam kết
///   - Chữ ký
class AtmOpenTemplate extends StatelessWidget {
  final FormTemplateData data;

  const AtmOpenTemplate({super.key, required this.data});

  String _v(String key) => data.cardValue(key);
  String _s(String key) => data.suppValue(key);
  bool get _isPreview => data.isPreview;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final dateStr =
        'Ngày ${_two(now.day)} tháng ${_two(now.month)} năm ${now.year}';

    return FormPaperWrapper(children: [
      // ── Tiêu đề ──────────────────────────────────────────────────────────
      const FormNationalHeader(),
      const SizedBox(height: 14),
      FormTitle(
        title: 'Giấy đề nghị mở tài khoản thanh toán',
        subtitle: '(Đăng ký thẻ ATM)',
        code: data.code,
      ),
      const SizedBox(height: 16),

      // ── I. Thông tin cá nhân ──────────────────────────────────────────────
      const FormSectionTitle('I. THÔNG TIN CÁ NHÂN'),

      FormInlineRow(items: [
        InlineFieldItem(
            label: 'Họ và tên',
            value: _isPreview ? '' : _v('fullName'),
            flex: 3),
        InlineFieldItem(
            label: 'Giới tính',
            value: _isPreview ? '' : _v('sex'),
            flex: 1),
      ]),
      const SizedBox(height: 5),

      FormDottedLine(
          prefix: '- Số CCCD/CMND: ',
          value: _isPreview ? '' : _v('idNumber')),
      FormDottedLine(
          prefix: '- Ngày sinh: ',
          value: _isPreview ? '' : _v('dob')),
      FormDottedLine(
          prefix: '- Quốc tịch: ',
          value: _isPreview ? '' : _v('nationality')),
      FormDottedLine(
          prefix: '- Quê quán: ',
          value: _isPreview ? '' : _v('origin')),
      FormDottedLine(
          prefix: '- Nơi thường trú: ',
          value: _isPreview ? '' : _v('residence')),

      const SizedBox(height: 6),
      const FormSectionTitle('Thông tin thẻ căn cước (mặt sau)'),
      FormDottedLine(
          prefix: '- Ngày cấp: ',
          value: _isPreview ? '' : _v('issueDate')),
      FormDottedLine(
          prefix: '- Có giá trị đến: ',
          value: _isPreview ? '' : _v('expiry')),
      FormDottedLine(
          prefix: '- Nơi cấp: ',
          value: _isPreview ? '' : _v('issuePlace')),

      const SizedBox(height: 10),

      // ── II. Thông tin tài khoản ───────────────────────────────────────────
      const FormSectionTitle('II. THÔNG TIN ĐĂNG KÝ TÀI KHOẢN'),

      FormDottedLine(
          prefix: '- Số điện thoại liên hệ: ',
          value: _isPreview ? '' : _s('phone')),
      FormDottedLine(
          prefix: '- Nghề nghiệp hiện tại: ',
          value: _isPreview ? '' : _s('occupation')),

      const SizedBox(height: 6),
      const FormSectionTitle('Loại tài khoản đăng ký:'),
      _accountTypeRow(),

      const SizedBox(height: 10),

      // ── III. Cam kết ──────────────────────────────────────────────────────
      const FormSectionTitle('III. CAM KẾT'),
      const FormStaticText(
        'Tôi cam kết những thông tin trên là đúng sự thật và chịu trách nhiệm '
        'trước pháp luật về nội dung khai báo. Tôi đã đọc, hiểu và đồng ý với '
        'các điều khoản, điều kiện sử dụng dịch vụ tài khoản của ngân hàng.',
        italic: true,
        fontSize: 11.5,
      ),

      const SizedBox(height: 4),

      // ── Chữ ký ───────────────────────────────────────────────────────────
      FormSignatureRow(
        leftTitle: 'Cán bộ tiếp nhận',
        rightTitle: 'Người đề nghị',
        rightName: _isPreview ? null : _v('fullName'),
        dateStr: dateStr,
      ),
    ]);
  }

  /// Hàng checkbox loại tài khoản
  Widget _accountTypeRow() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        _checkOption('Tài khoản thanh toán', true),
        const SizedBox(width: 20),
        _checkOption('Tài khoản tiết kiệm', false),
      ]),
    );
  }

  Widget _checkOption(String label, bool checked) {
    return Row(children: [
      Container(
        width: 14,
        height: 14,
        margin: const EdgeInsets.only(right: 5),
        decoration: BoxDecoration(
          border: Border.all(color: const Color(0xFF1A2438), width: 1),
          color: checked ? const Color(0xFF0A2A66) : Colors.transparent,
        ),
        child: checked
            ? const Icon(Icons.check, size: 10, color: Colors.white)
            : null,
      ),
      Text(label,
          style: const TextStyle(fontSize: 12, color: Color(0xFF1A2438))),
    ]);
  }

  static String _two(int n) => n.toString().padLeft(2, '0');
}
