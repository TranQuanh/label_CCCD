// ignore_for_file: prefer_const_constructors, prefer_const_literals_to_create_immutables
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import 'form_template_registry.dart';
import 'form_widgets.dart';

/// Template Hợp đồng dịch vụ.
///
/// Bố cục:
///   - Tiêu đề quốc gia + tên hợp đồng
///   - Số hợp đồng + ngày ký
///   - Bên A (đơn vị cung cấp dịch vụ — thông tin cố định)
///   - Bên B (khách hàng — thông tin từ CCCD)
///   - Điều 1: Nội dung dịch vụ
///   - Điều 2: Thời hạn hợp đồng
///   - Điều 3: Giá trị hợp đồng
///   - Điều 4: Cam kết
///   - Chữ ký 2 cột (Đại diện bên A + Bên B)
class ServiceContractTemplate extends StatelessWidget {
  final FormTemplateData data;

  const ServiceContractTemplate({super.key, required this.data});

  String _v(String key) => data.cardValue(key);
  String _s(String key) => data.suppValue(key);
  bool get _p => data.isPreview;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final dateStr =
        'Ngày ${_two(now.day)} tháng ${_two(now.month)} năm ${now.year}';
    final dateLineStr =
        'ngày .... tháng .... năm ${now.year}';

    return FormPaperWrapper(children: [
      // ── Tiêu đề ──────────────────────────────────────────────────────────
      const FormNationalHeader(),
      const SizedBox(height: 14),
      FormTitle(
        title: 'Hợp đồng cung cấp dịch vụ',
        code: data.code,
      ),
      const SizedBox(height: 4),
      Center(
        child: Text('Số: ....../${ now.year}/HĐDV',
            style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.ink)),
      ),
      const SizedBox(height: 4),
      const Center(
        child: Text(
            'Căn cứ Bộ luật Dân sự năm 2015; Luật Thương mại năm 2005\n'
            'và các quy định của pháp luật hiện hành.',
            textAlign: TextAlign.center,
            style: TextStyle(
                fontSize: 11.5,
                fontStyle: FontStyle.italic,
                color: AppColors.inkSoft)),
      ),
      Center(
        child: Text(
            'Hôm $dateLineStr, chúng tôi gồm:',
            style: const TextStyle(fontSize: 12, color: AppColors.ink)),
      ),
      const SizedBox(height: 12),

      // ── Bên A ─────────────────────────────────────────────────────────────
      _partyHeader('BÊN A (ĐƠN VỊ CUNG CẤP DỊCH VỤ)', AppColors.navy),
      FormDottedLine(prefix: '- Tên đơn vị: ', value: _p ? '' : _s('company')),
      const FormDottedLine(prefix: '- Địa chỉ: ', value: ''),
      const FormDottedLine(prefix: '- Điện thoại: ', value: ''),
      const FormDottedLine(prefix: '- Đại diện bởi: ', value: ''),
      const SizedBox(height: 10),

      // ── Bên B ─────────────────────────────────────────────────────────────
      _partyHeader('BÊN B (KHÁCH HÀNG)', const Color(0xFF0B6E4F)),
      FormDottedLine(
          prefix: '- Họ và tên: ',
          value: _p ? '' : _v('fullName')),
      FormDottedLine(
          prefix: '- Số CCCD/CMND: ',
          value: _p ? '' : _v('idNumber')),
      FormInlineRow(items: [
        InlineFieldItem(
            label: 'Ngày sinh', value: _p ? '' : _v('dob'), flex: 2),
        InlineFieldItem(
            label: 'Giới tính', value: _p ? '' : _v('sex'), flex: 1),
        InlineFieldItem(
            label: 'Quốc tịch', value: _p ? '' : _v('nationality'), flex: 2),
      ]),
      const SizedBox(height: 4),
      FormDottedLine(
          prefix: '- Địa chỉ thường trú: ',
          value: _p ? '' : _v('residence')),
      FormDottedLine(
          prefix: '- Điện thoại liên hệ: ',
          value: _p ? '' : _s('phone')),
      FormDottedLine(
          prefix: '- CCCD cấp ngày: ',
          value: _p ? '' : _v('issueDate'),
          suffix: '  tại: '),
      const SizedBox(height: 12),

      // ── Các điều khoản ────────────────────────────────────────────────────
      _articleTitle('Điều 1: Nội dung dịch vụ'),
      const FormDottedLine(
          prefix: '1.1 Bên A đồng ý cung cấp dịch vụ: ',
          value: ''),
      const FormDottedLine(prefix: '1.2 Địa điểm thực hiện: ', value: ''),
      const SizedBox(height: 6),

      _articleTitle('Điều 2: Thời hạn hợp đồng'),
      const FormDottedLine(prefix: '2.1 Hợp đồng có hiệu lực từ ngày: ', value: ''),
      const FormDottedLine(prefix: '2.2 Thời hạn hợp đồng: ', value: ''),
      const SizedBox(height: 6),

      _articleTitle('Điều 3: Giá trị hợp đồng và phương thức thanh toán'),
      const FormStaticText(
          '3.1 Giá trị hợp đồng: .....................................................  đồng '
          '(Bằng chữ: .......................................................................)',
          fontSize: 12),
      const FormDottedLine(prefix: '3.2 Phương thức thanh toán: ', value: ''),
      const SizedBox(height: 6),

      _articleTitle('Điều 4: Cam kết của các bên'),
      const FormStaticText(
        '4.1 Hai bên cam kết thực hiện đúng các điều khoản đã ký kết.\n'
        '4.2 Mọi tranh chấp phát sinh được giải quyết theo quy định pháp luật\n'
        'hiện hành của nước Cộng hòa xã hội chủ nghĩa Việt Nam.\n'
        '4.3 Hợp đồng được lập thành 02 bản có giá trị pháp lý như nhau, '
        'mỗi bên giữ 01 bản.',
        fontSize: 11.5,
        italic: true,
      ),
      const SizedBox(height: 6),

      // ── Chữ ký 2 cột ─────────────────────────────────────────────────────
      FormSignatureRow(
        leftTitle: 'Đại diện bên A',
        leftName: null,
        rightTitle: 'Bên B',
        rightName: _p ? null : _v('fullName'),
        dateStr: dateStr,
      ),
    ]);
  }

  /// Header bên ký kết (màu nền nhẹ)
  Widget _partyHeader(String title, Color color) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(4),
        border: Border(left: BorderSide(color: color, width: 3)),
      ),
      child: Text(title,
          style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: color)),
    );
  }

  /// Tiêu đề điều khoản in đậm
  Widget _articleTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 4),
      child: Text(title,
          style: const TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: AppColors.ink)),
    );
  }

  static String _two(int n) => n.toString().padLeft(2, '0');
}
