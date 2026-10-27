/// Shared widgets dùng chung cho tất cả form templates.
///
/// Các widget này mô phỏng đúng giao diện giấy tờ hành chính Việt Nam:
/// dòng kẻ chấm, ô checkbox, trường nằm ngang, chữ ký 2 cột, v.v.
library form_widgets;

import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

// ─────────────────────────────────────────────────────────────────────────────
// Tiêu đề quốc gia (phần đầu mọi biểu mẫu hành chính)
// ─────────────────────────────────────────────────────────────────────────────

class FormNationalHeader extends StatelessWidget {
  const FormNationalHeader({super.key});

  @override
  Widget build(BuildContext context) {
    return Center(
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
        const SizedBox(height: 5),
        Container(width: 130, height: 1.5, color: AppColors.ink),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tiêu đề biểu mẫu
// ─────────────────────────────────────────────────────────────────────────────

class FormTitle extends StatelessWidget {
  final String title;
  final String? subtitle;
  final String? code;

  const FormTitle({
    super.key,
    required this.title,
    this.subtitle,
    this.code,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(children: [
        Text(title.toUpperCase(),
            textAlign: TextAlign.center,
            style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w900,
                height: 1.35,
                color: AppColors.ink)),
        if (subtitle != null) ...[
          const SizedBox(height: 4),
          Text(subtitle!,
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 11,
                  fontStyle: FontStyle.italic,
                  color: AppColors.inkSoft)),
        ],
        if (code != null && code!.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text('Mã hồ sơ: $code',
              style: const TextStyle(
                  fontSize: 11,
                  color: AppColors.muted,
                  fontFamily: 'monospace')),
        ],
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Tiêu đề section (số thứ tự + chữ đậm)
// ─────────────────────────────────────────────────────────────────────────────

class FormSectionTitle extends StatelessWidget {
  final String text;
  final bool bold;

  const FormSectionTitle(this.text, {super.key, this.bold = true});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 10, bottom: 5),
      child: Text(text,
          style: TextStyle(
              fontSize: 13,
              fontWeight: bold ? FontWeight.w700 : FontWeight.w400,
              color: AppColors.ink)),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Dòng dữ liệu label + value (kiểu bảng 2 cột)
// ─────────────────────────────────────────────────────────────────────────────

class FormDataRow extends StatelessWidget {
  final String label;
  final String value;
  final double labelWidth;

  const FormDataRow({
    super.key,
    required this.label,
    required this.value,
    this.labelWidth = 110,
  });

  @override
  Widget build(BuildContext context) {
    final display = value.trim().isEmpty ? '—' : value;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 5),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.lineSoft)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: labelWidth,
          child: Text(label,
              style:
                  const TextStyle(fontSize: 12, color: AppColors.muted)),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(display,
              style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: AppColors.ink)),
        ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Dòng văn bản với dấu chấm điền (kiểu form giấy)
// ─────────────────────────────────────────────────────────────────────────────

class FormDottedLine extends StatelessWidget {
  /// Nhãn đứng trước giá trị (ví dụ: "- Họ và tên: ")
  final String? prefix;

  /// Giá trị điền vào (nếu có). Nếu rỗng thì hiện đường kẻ trống.
  final String value;

  /// Nhãn đứng sau giá trị trên cùng dòng (dùng khi giá trị ngắn + suffix ngắn)
  final String? suffix;

  const FormDottedLine({
    super.key,
    this.prefix,
    this.value = '',
    this.suffix,
  });

  @override
  Widget build(BuildContext context) {
    final hasValue = value.trim().isNotEmpty;

    // Ước tính số ký tự có thể chứa trên 1 dòng dựa vào chiều rộng màn hình.
    // Nếu tổng text có thể dài → dùng layout dọc để tránh bị cắt lệch dòng.
    final combinedLen = (prefix?.length ?? 0) + value.length + (suffix?.length ?? 0);
    final isLong = combinedLen > 40 || value.contains('\n');

    if (isLong && hasValue) {
      // Layout dọc: prefix trên, value bên dưới có border-bottom
      return Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (prefix != null)
              Text(prefix!,
                  style: const TextStyle(fontSize: 12, color: AppColors.ink)),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.only(bottom: 2),
              decoration: const BoxDecoration(
                border: Border(
                    bottom: BorderSide(color: AppColors.ink)),
              ),
              child: Text(
                value + (suffix ?? ''),
                style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppColors.ink),
              ),
            ),
          ],
        ),
      );
    }

    // Layout ngang mặc định: prefix + value + suffix trên một dòng
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (prefix != null)
            Text(prefix!,
                style: const TextStyle(fontSize: 12, color: AppColors.ink)),
          Expanded(
            child: hasValue
                ? Container(
                    padding: const EdgeInsets.only(bottom: 2),
                    decoration: const BoxDecoration(
                      border: Border(
                          bottom: BorderSide(color: AppColors.ink)),
                    ),
                    child: Text(value,
                        style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: AppColors.ink)),
                  )
                : Container(
                    height: 16,
                    decoration: const BoxDecoration(
                      border: Border(
                          bottom: BorderSide(
                              color: AppColors.ink,
                              style: BorderStyle.solid)),
                    ),
                  ),
          ),
          if (suffix != null)
            Text(suffix!,
                style: const TextStyle(fontSize: 12, color: AppColors.ink)),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Nhiều dòng trống liên tiếp (ví dụ: mục khai địa phương đã đến)
// ─────────────────────────────────────────────────────────────────────────────

class FormBlankLines extends StatelessWidget {
  final int count;
  final String value;

  const FormBlankLines({super.key, this.count = 3, this.value = ''});

  @override
  Widget build(BuildContext context) {
    final lines = value.trim().isEmpty
        ? List.filled(count, '')
        : value.split('\n').take(count).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: List.generate(count, (i) {
        final v = i < lines.length ? lines[i] : '';
        return Padding(
          padding: const EdgeInsets.only(bottom: 5),
          child: Container(
            width: double.infinity,
            height: 18,
            decoration: const BoxDecoration(
              border: Border(
                  bottom: BorderSide(color: AppColors.ink)),
            ),
            alignment: Alignment.bottomLeft,
            child: v.isNotEmpty
                ? Text(v,
                    style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: AppColors.ink))
                : null,
          ),
        );
      }),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Dòng checkbox Có / Không
// ─────────────────────────────────────────────────────────────────────────────

class FormCheckboxRow extends StatelessWidget {
  final String label;

  /// Giá trị: 'co', 'khong', hoặc rỗng (chưa chọn — chỉ mode preview/review)
  final String value;

  const FormCheckboxRow({
    super.key,
    required this.label,
    this.value = '',
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Expanded(
              child: Text('- $label',
                  style: const TextStyle(
                      fontSize: 12, color: AppColors.ink))),
          _box('có', value == 'co'),
          const SizedBox(width: 14),
          _box('không', value == 'khong'),
        ],
      ),
    );
  }

  Widget _box(String label, bool checked) {
    return Row(children: [
      Container(
        width: 14,
        height: 14,
        margin: const EdgeInsets.only(right: 4),
        decoration: BoxDecoration(
          border: Border.all(color: AppColors.ink, width: 1),
          color: checked ? AppColors.navy : Colors.transparent,
        ),
        child: checked
            ? const Icon(Icons.check, size: 10, color: Colors.white)
            : null,
      ),
      Text(label,
          style: const TextStyle(fontSize: 12, color: AppColors.ink)),
    ]);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Hàng các trường nằm ngang (ví dụ: Họ tên + Nam/Nữ + Tuổi)
// ─────────────────────────────────────────────────────────────────────────────

/// Một ô trong hàng ngang
class InlineFieldItem {
  final String label;
  final String value;

  /// flex = tỉ lệ chiều rộng
  final int flex;

  const InlineFieldItem({
    required this.label,
    required this.value,
    this.flex = 1,
  });
}

class FormInlineRow extends StatelessWidget {
  final List<InlineFieldItem> items;

  const FormInlineRow({super.key, required this.items});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: items.asMap().entries.map((entry) {
          final i = entry.key;
          final item = entry.value;
          final hasValue = item.value.trim().isNotEmpty;
          return Expanded(
            flex: item.flex,
            child: Padding(
              padding: EdgeInsets.only(right: i < items.length - 1 ? 8 : 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.label,
                      style: const TextStyle(
                          fontSize: 11, color: AppColors.muted)),
                  const SizedBox(height: 2),
                  Container(
                    width: double.infinity,
                    height: 18,
                    decoration: const BoxDecoration(
                      border: Border(
                          bottom: BorderSide(color: AppColors.ink)),
                    ),
                    alignment: Alignment.bottomLeft,
                    child: hasValue
                        ? Text(item.value,
                            style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: AppColors.ink))
                        : null,
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Đoạn văn bản tĩnh (ghi chú, cam kết, điều khoản)
// ─────────────────────────────────────────────────────────────────────────────

class FormStaticText extends StatelessWidget {
  final String text;
  final bool italic;
  final bool bold;
  final double fontSize;
  final TextAlign align;

  const FormStaticText(
    this.text, {
    super.key,
    this.italic = false,
    this.bold = false,
    this.fontSize = 12,
    this.align = TextAlign.left,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Text(text,
          textAlign: align,
          style: TextStyle(
              fontSize: fontSize,
              fontStyle: italic ? FontStyle.italic : FontStyle.normal,
              fontWeight: bold ? FontWeight.w700 : FontWeight.w400,
              color: AppColors.ink,
              height: 1.5)),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Đường kẻ ngang phân cách
// ─────────────────────────────────────────────────────────────────────────────

class FormDivider extends StatelessWidget {
  const FormDivider({super.key});

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 8),
      child: Divider(color: AppColors.line, height: 1),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Hàng chữ ký (1 hoặc 2 cột)
// ─────────────────────────────────────────────────────────────────────────────

class FormSignatureRow extends StatelessWidget {
  final String? leftTitle;
  final String? leftName;
  final String rightTitle;
  final String? rightName;
  final String dateStr;

  const FormSignatureRow({
    super.key,
    this.leftTitle,
    this.leftName,
    required this.rightTitle,
    this.rightName,
    required this.dateStr,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (leftTitle != null) ...[
            Expanded(child: _sig(leftTitle!, leftName)),
            const SizedBox(width: 12),
          ],
          Expanded(
            child: Column(children: [
              Text(dateStr,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                      fontSize: 11,
                      fontStyle: FontStyle.italic,
                      color: AppColors.inkSoft)),
              const SizedBox(height: 4),
              _sig(rightTitle, rightName),
            ]),
          ),
        ],
      ),
    );
  }

  Widget _sig(String title, String? name) {
    return Column(children: [
      Text(title.toUpperCase(),
          textAlign: TextAlign.center,
          style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: AppColors.ink)),
      const Text('(Ký và ghi rõ họ tên)',
          textAlign: TextAlign.center,
          style: TextStyle(
              fontSize: 10.5,
              fontStyle: FontStyle.italic,
              color: AppColors.muted)),
      const SizedBox(height: 36),
      if (name != null && name.isNotEmpty)
        Text(name,
            textAlign: TextAlign.center,
            style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w800,
                color: AppColors.navy)),
    ]);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Bảng dữ liệu đơn giản
// ─────────────────────────────────────────────────────────────────────────────

class FormTable extends StatelessWidget {
  final List<String> headers;
  final List<List<String>> rows;

  const FormTable({
    super.key,
    required this.headers,
    required this.rows,
  });

  @override
  Widget build(BuildContext context) {
    return Table(
      border: TableBorder.all(color: AppColors.ink, width: 0.8),
      columnWidths: {
        for (int i = 0; i < headers.length; i++)
          i: const FlexColumnWidth(),
      },
      children: [
        TableRow(
          decoration: const BoxDecoration(color: AppColors.tint),
          children: headers
              .map((h) => _cell(h, bold: true))
              .toList(),
        ),
        ...rows.map((row) => TableRow(
              children: row.map((c) => _cell(c)).toList(),
            )),
      ],
    );
  }

  Widget _cell(String text, {bool bold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 5),
      child: Text(text,
          style: TextStyle(
              fontSize: 11.5,
              fontWeight: bold ? FontWeight.w700 : FontWeight.w400,
              color: AppColors.ink)),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Wrapper bọc ngoài mọi template (nền trắng, bo góc, shadow)
// ─────────────────────────────────────────────────────────────────────────────

class FormPaperWrapper extends StatelessWidget {
  final List<Widget> children;

  const FormPaperWrapper({super.key, required this.children});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(6),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: .35),
              blurRadius: 28,
              offset: const Offset(0, 12)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: children,
      ),
    );
  }
}
