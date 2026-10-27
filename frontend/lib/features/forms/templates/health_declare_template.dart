// ignore_for_file: prefer_const_constructors, prefer_const_literals_to_create_immutables
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import 'form_template_registry.dart';
import 'form_widgets.dart';

/// Template Tờ khai y tế — bố cục theo ảnh mẫu thực tế.
///
/// Bố cục:
///   1. Thông tin người khai y tế (họ tên, CCCD, địa chỉ, SĐT, phương tiện...)
///   2. Những địa phương đã đi trong 14 ngày (dòng trống nhiều dòng)
///   3. Các yếu tố liên quan dịch bệnh (checkbox Có/Không)
///   4. Hiện có mắc bệnh
///   5. Cam kết
///   6. Chữ ký 2 cột
class HealthDeclareTemplate extends StatelessWidget {
  final FormTemplateData data;

  const HealthDeclareTemplate({super.key, required this.data});

  String _v(String key) => data.cardValue(key);
  String _s(String key) => data.suppValue(key);
  bool get _p => data.isPreview;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final dateStr =
        'Ngày ${_two(now.day)} tháng ${_two(now.month)} năm ${now.year}';

    return FormPaperWrapper(children: [
      // ── Tiêu đề ──────────────────────────────────────────────────────────
      const FormNationalHeader(),
      const SizedBox(height: 14),
      const FormTitle(
        title: 'Tờ khai y tế',
        subtitle:
            '(Áp dụng cho đối tượng không sử dụng khai báo y tế điện tử\n'
            'và dùng để phục vụ công tác phòng chống dịch)',
      ),
      if (data.code.isNotEmpty) ...[
        const SizedBox(height: 4),
        Center(
          child: Text('Mã hồ sơ: ${data.code}',
              style: const TextStyle(
                  fontSize: 11,
                  color: AppColors.muted,
                  fontFamily: 'monospace')),
        ),
      ],
      const SizedBox(height: 16),

      // ── 1. Thông tin người khai ───────────────────────────────────────────
      const FormSectionTitle('1. Thông tin người khai báo y tế:'),

      // Dòng: Họ và tên + Nam/Nữ + Tuổi
      FormInlineRow(items: [
        InlineFieldItem(label: 'Họ và tên', value: _p ? '' : _v('fullName'), flex: 4),
        InlineFieldItem(label: 'Nam/Nữ', value: _p ? '' : _v('sex'), flex: 2),
        InlineFieldItem(
            label: 'Tuổi',
            value: _p ? '' : _calcAge(_v('dob')),
            flex: 1),
      ]),
      const SizedBox(height: 4),

      FormDottedLine(
          prefix: '- Số CMND/CCCD/Hộ chiếu: ',
          value: _p ? '' : _v('idNumber'),
          suffix: ',  Quốc tịch: '),
      FormDottedLine(
          prefix: '- Địa chỉ theo CMND/CCCD/Hộ chiếu: ',
          value: _p ? '' : _v('residence')),

      // Chỗ ở hiện tại (multi-part)
      _currentAddressRow(),
      const SizedBox(height: 3),

      FormDottedLine(
          prefix: '- Số điện thoại liên hệ: ',
          value: _p ? '' : _s('phone')),
      FormDottedLine(
          prefix: '- Loại phương tiện: ',
          value: '',
          suffix: ',  Biển số: ,  Số người đi cùng:     người.'),
      FormDottedLine(
          prefix: '- Nơi đi: ',
          value: '',
          suffix: '  Ngày đi: '),
      FormDottedLine(
          prefix: '- Nơi đến (ghi cụ thể ấp, xã, huyện): ',
          value: ''),
      FormDottedLine(
          prefix: '- Thời gian khai báo y tế tại chốt kiểm soát: ',
          value: ''),
      const SizedBox(height: 8),

      // ── 2. Địa phương đã đi ───────────────────────────────────────────────
      const FormSectionTitle(
          '2. Những địa phương (tỉnh/thành phố) đã đi qua trong vòng 14 ngày gần đây:'),
      FormBlankLines(
          count: 4,
          value: _p ? '' : _s('provinces_visited')),
      const SizedBox(height: 8),

      // ── 3. Các yếu tố dịch bệnh ───────────────────────────────────────────
      const FormSectionTitle(
          '3. Các yếu tố liên quan đến dịch bệnh trong vòng 14 ngày gần đây:'),
      FormCheckboxRow(
          label: 'Đi đến/ở/về từ vùng dịch:',
          value: _p ? '' : _s('from_outbreak_area')),
      FormCheckboxRow(
          label: 'Tiếp xúc người nghi ngờ mắc bệnh:',
          value: _p ? '' : _s('contact_suspected')),
      FormCheckboxRow(
          label: 'Tiếp xúc người có biểu hiện sốt, ho, khó thở:',
          value: _p ? '' : _s('contact_symptoms')),
      const SizedBox(height: 8),

      // ── 4. Biểu hiện sức khỏe ────────────────────────────────────────────
      const FormSectionTitle(
          '4. Hiện tại và những ngày gần đây có mắc các dấu hiệu sau:'),
      FormCheckboxRow(
          label: 'Sốt (trên 38°C), Ho, Khó thở, Đau họng',
          value: _p ? '' : _s('has_fever_cough')),
      const SizedBox(height: 6),

      // ── 5. Bệnh nền ──────────────────────────────────────────────────────
      FormDottedLine(
          prefix: '5. Hiện có mắc những bệnh gì: ',
          value: _p ? '' : _s('existing_conditions')),
      const SizedBox(height: 8),

      // ── 6. Cam kết ───────────────────────────────────────────────────────
      _commitmentSection(),
      const SizedBox(height: 6),

      // ── Địa điểm chốt kiểm soát ──────────────────────────────────────────
      _checkpointRow(),
      const SizedBox(height: 4),

      // ── Chữ ký 2 cột ─────────────────────────────────────────────────────
      FormSignatureRow(
        leftTitle: 'Người tiếp nhận tờ khai',
        leftName: null,
        rightTitle: 'Người khai',
        rightName: _p ? null : _v('fullName'),
        dateStr: dateStr,
      ),
    ]);
  }

  /// Dòng "Chỗ ở hiện nay" có cấu trúc phức tạp: số nhà / đường / xã phường / huyện / tỉnh
  Widget _currentAddressRow() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('- Chỗ ở hiện nay:',
            style: TextStyle(fontSize: 12, color: AppColors.ink)),
        const SizedBox(height: 3),
        const FormInlineRow(items: [
          InlineFieldItem(label: 'Số nhà', value: '', flex: 1),
          InlineFieldItem(label: 'Đường/ấp', value: '', flex: 2),
          InlineFieldItem(label: 'Xã/phường', value: '', flex: 2),
        ]),
        const SizedBox(height: 3),
        const FormInlineRow(items: [
          InlineFieldItem(label: 'Huyện/quận', value: '', flex: 2),
          InlineFieldItem(label: 'Tỉnh/thành phố', value: '', flex: 2),
        ]),
      ],
    );
  }

  /// Mục 6 — cam kết (đoạn văn bản tĩnh có viền)
  Widget _commitmentSection() {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.line),
        borderRadius: BorderRadius.circular(4),
      ),
      child: const FormStaticText(
        '6. Tôi xin cam kết những thông tin khai báo nêu trên là sự thật và '
        'đầy đủ. Nếu khai báo không đầy đủ hoặc sai sự thật tôi xin hoàn '
        'toàn chịu mọi trách nhiệm theo quy định của pháp luật.',
        italic: true,
        fontSize: 11.5,
      ),
    );
  }

  /// Dòng "Địa điểm chốt kiểm soát"
  Widget _checkpointRow() {
    return Row(children: [
      const Text('• Địa điểm Chốt Kiểm soát: ',
          style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: AppColors.ink)),
      Expanded(
        child: Container(
          height: 18,
          decoration: const BoxDecoration(
              border: Border(bottom: BorderSide(color: AppColors.ink))),
        ),
      ),
    ]);
  }

  /// Tính tuổi từ ngày sinh dạng dd/MM/yyyy
  static String _calcAge(String dob) {
    if (dob.isEmpty) return '';
    try {
      final parts = dob.split('/');
      if (parts.length != 3) return '';
      final year = int.parse(parts[2]);
      final age = DateTime.now().year - year;
      return age > 0 ? '$age' : '';
    } catch (_) {
      return '';
    }
  }

  static String _two(int n) => n.toString().padLeft(2, '0');
}
