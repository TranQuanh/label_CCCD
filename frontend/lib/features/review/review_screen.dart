import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/validation/validators.dart';
import '../../core/widgets/custom_textfield.dart';
import '../../core/widgets/section_label.dart';
import '../../data/models/form_type.dart';
import '../../data/models/id_card.dart';
import '../../data/models/submitted_record.dart';
import '../../data/validation/card_rules.dart';
import '../forms/templates/form_template_registry.dart';
import '../output/preview_screen.dart';

/// Định nghĩa một trường trên thẻ.
class _Def {
  final String key;
  final String label;
  final bool multiline;
  final bool mono;

  const _Def(this.key, this.label, {this.multiline = false, this.mono = false});
}

/// Thanh tiến trình có animation.
class _ValidityBar extends StatelessWidget {
  final double value;
  final Color color;
  const _ValidityBar({required this.value, required this.color});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 7,
      child: LayoutBuilder(
        builder: (context, c) => Stack(children: [
          Container(color: const Color(0xFFD2DCEF)),
          AnimatedContainer(
            duration: const Duration(milliseconds: 400),
            width: c.maxWidth * value.clamp(0.0, 1.0),
            color: color,
          ),
        ]),
      ),
    );
  }
}

/// Màn hình 5 — Đối chiếu dữ liệu AI + bổ sung thông tin còn thiếu.
class ReviewScreen extends StatefulWidget {
  final FormType formType;
  final IdCardData card;

  /// Trường bị đánh dấu ngay sau khi trích xuất (kết quả `CardRules` lần đầu).
  final List<String> needsReview;
  final List<FieldIssue> issues;

  /// true khi dữ liệu đến từ ảnh chụp thẻ (ProcessingScreen). false khi vào từ
  /// "Dùng Profile" / "Nhập thủ công" → ẩn ô ảnh TRƯỚC/SAU và đổi nút camera
  /// thành nút quay lại (không có ảnh nào để chụp lại).
  final bool fromScan;

  const ReviewScreen({
    super.key,
    required this.formType,
    required this.card,
    this.needsReview = const [],
    this.issues = const [],
    this.fromScan = false,
  });

  @override
  State<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends State<ReviewScreen> {
  static const _frontDefs = <_Def>[
    _Def('fullName', 'Họ và tên'),
    _Def('idNumber', 'Số CCCD', mono: true),
    _Def('dob', 'Ngày sinh'),
    _Def('sex', 'Giới tính'),
    _Def('nationality', 'Quốc tịch'),
    _Def('origin', 'Quê quán'),
    _Def('residence', 'Nơi thường trú', multiline: true),
  ];

  static const _backDefs = <_Def>[
    _Def('issueDate', 'Ngày cấp'),
    _Def('expiry', 'Có giá trị đến'),
    _Def('issuePlace', 'Nơi cấp', multiline: true),
    _Def('features', 'Đặc điểm nhận dạng', multiline: true),
  ];

  static const _allDefs = <_Def>[..._frontDefs, ..._backDefs];

  final Map<String, TextEditingController> _card = {};
  final Map<String, TextEditingController> _supp = {};
  bool _touched = false;

  /// Kết quả kiểm tra của giá trị đang hiển thị, tính lại mỗi lần gõ.
  Map<String, List<FieldIssue>> _issues = const {};

  @override
  void initState() {
    super.initState();
    for (final e in widget.card.toMap().entries) {
      final c = TextEditingController(text: e.value);
      c.addListener(_revalidate);
      _card[e.key] = c;
    }
    for (final s in widget.formType.supp) {
      final c = TextEditingController();
      c.addListener(_revalidate);
      _supp[s.key] = c;
    }
    _issues = CardRules.byField(_currentCard());
  }

  @override
  void dispose() {
    for (final c in _card.values) {
      c.dispose();
    }
    for (final c in _supp.values) {
      c.dispose();
    }
    super.dispose();
  }

  IdCardData _currentCard() {
    final card = widget.card.clone();
    card.applyMap({for (final e in _card.entries) e.key: e.value.text});
    return card;
  }

  void _revalidate() {
    setState(() => _issues = CardRules.byField(_currentCard()));
  }

  List<FieldIssue> _issuesOf(String key) => _issues[key] ?? const [];

  bool _blocks(String key) => _issuesOf(key).any((i) => i.blocks);

  bool _warns(String key) => _issuesOf(key).isNotEmpty;

  bool get _canContinue {
    final cardOk = _allDefs.every((d) => !_blocks(d.key));
    final suppOk = _supp.values.every((c) => c.text.trim().isNotEmpty);
    return cardOk && suppOk;
  }

  /// Tỉ lệ trường không còn vướng quy tắc nào.
  int get _validPercent {
    final ok = _allDefs.where((d) => !_warns(d.key)).length;
    return ((ok / _allDefs.length) * 100).round();
  }

  void _continue() {
    if (!_canContinue) {
      setState(() => _touched = true);
      return;
    }
    final card = _currentCard()
      ..idNumber = Validators.normalizeIdNumber(_card['idNumber']!.text)
      ..sex = Validators.normalizeSex(_card['sex']!.text);

    // Thẻ quét cho biểu mẫu KHÔNG được ghi vào Profile CCCD (có thể là thẻ
    // của khách) — Profile chỉ đổi khi người dùng lưu ở tab Profile.
    final supp = {
      for (final e in _supp.entries) e.key: e.value.text.trim(),
    };

    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => PreviewScreen(
        formType: widget.formType,
        card: card,
        supp: supp,
        code: SubmittedRecord.newCode(),
      ),
    ));
  }

  /// Helper to get SuppField by key
  SuppField? _suppFieldByKey(String key) {
    try {
      return widget.formType.supp.firstWhere((sf) => sf.key == key);
    } catch (e) {
      return null;
    }
  }

  /// Build widgets for supplemental fields based on layout
  List<Widget> _buildSuppFields() {
    final layout = widget.formType.layout;
    if (layout.isEmpty) {
      return widget.formType.supp.map(_suppField).toList();
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
            textColor: const Color(0xFFB01B15)));
        children.add(const SizedBox(height: 6));
        final fieldsList = map['fields'] as List<dynamic>?;
        if (fieldsList != null) {
          for (final keyObj in fieldsList) {
            final key = keyObj.toString();
            final suppField = _suppFieldByKey(key);
            if (suppField != null) {
              final labelOverride = map['label'] as String?;
              final hintOverride = map['hint'] as String?;
              final effectiveField = SuppField(
                key: suppField.key,
                label: labelOverride ?? suppField.label,
                hint: hintOverride ?? suppField.hint,
              );
              children.add(_suppField(effectiveField));
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
            final hintOverride = map['hint'] as String?;
            final effectiveField = SuppField(
              key: suppField.key,
              label: labelOverride ?? suppField.label,
              hint: hintOverride ?? suppField.hint,
            );
            children.add(_suppField(effectiveField));
          }
        }
      }
    }
    return children;
  }

  @override
  Widget build(BuildContext context) {
    // Nếu form có template riêng → dùng template trong ListView, giữ nguyên
    // header + validity bar + bottom bar của màn hình review.
    final hasTemplate = FormTemplateRegistry.hasTemplate(widget.formType.id);

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          _header(),
          _validityBar(),
          Expanded(
            child: hasTemplate
                ? _buildTemplateReview()
                : _buildGenericReview(),
          ),
          _bottomBar(),
        ],
      ),
    );
  }

  /// Render màn hình review cho form có template riêng.
  /// CHỈ hiển thị các panel nhập liệu (supp + CCCD) — KHÔNG hiển thị preview form.
  /// Template sẽ xuất hiện ở PreviewScreen (output mode) sau khi user xác nhận.
  Widget _buildTemplateReview() {
    // Gom tất cả controllers thành một Listenable hợp nhất.
    final allListenables = Listenable.merge([
      ..._card.values,
      ..._supp.values,
    ]);

    return ListenableBuilder(
      listenable: allListenables,
      builder: (context, _) {
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // Panel nhập tay supp fields
            if (widget.formType.supp.isNotEmpty) ...[
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: AppColors.lineSoft),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SectionLabel(
                        text: 'ĐIỀN THÔNG TIN BỔ SUNG',
                        barColor: AppColors.flagRed,
                        textColor: Color(0xFFB01B15)),
                    const SizedBox(height: 6),
                    const Text(
                        'Nhập các thông tin dưới đây.',
                        style: TextStyle(fontSize: 12, color: AppColors.muted)),
                    const SizedBox(height: 11),
                    ..._buildSuppFields(),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],
            // Panel chỉnh sửa thông tin CCCD
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppColors.lineSoft),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SectionLabel(
                      text: 'KIỂM TRA THÔNG TIN CCCD',
                      barColor: AppColors.cobalt,
                      textColor: AppColors.navy),
                  const SizedBox(height: 6),
                  const Text(
                      'Sửa nếu AI trích xuất sai.',
                      style: TextStyle(fontSize: 12, color: AppColors.muted)),
                  const SizedBox(height: 11),
                  ..._frontDefs.map(_cardField),
                  ..._backDefs.map(_cardField),
                ],
              ),
            ),
            const SizedBox(height: 16),
          ],
        );
      }, // builder
    ); // ListenableBuilder
  }

  /// Render generic (fallback) cho form chưa có template riêng.
  Widget _buildGenericReview() {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 10),
      children: [
        const SectionLabel(
            text: 'THÔNG TIN MẶT TRƯỚC',
            barColor: AppColors.cobalt,
            textColor: AppColors.navy),
        const SizedBox(height: 11),
        ..._frontDefs.map(_cardField),
        const SizedBox(height: 5),
        const SectionLabel(
            text: 'THÔNG TIN MẶT SAU',
            barColor: Color(0xFF7C4DB8),
            textColor: Color(0xFF5B3A94)),
        const SizedBox(height: 11),
        ..._backDefs.map(_cardField),
        const SizedBox(height: 5),
        const SectionLabel(
            text: 'THÔNG TIN CẦN BỔ SUNG',
            barColor: AppColors.flagRed,
            textColor: Color(0xFFB01B15)),
        const SizedBox(height: 6),
        const Text(
            'Các trường không có trên thẻ — vui lòng nhập tay.',
            style: TextStyle(fontSize: 12, color: AppColors.muted)),
        const SizedBox(height: 11),
        ..._buildSuppFields(),
      ],
    );
  }

  Widget _header() {
    return Container(
      width: double.infinity,
      color: AppColors.navy,
      padding: EdgeInsets.fromLTRB(
          20, MediaQuery.of(context).padding.top + 12, 20, 16),
      child: Row(children: [
        // Nút quay lại màn trước.
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
        // Ô ảnh TRƯỚC/SAU chỉ có nghĩa khi dữ liệu đến từ ảnh chụp thẻ.
        if (widget.fromScan) ...[
          Row(children: [
            _thumb('TRƯỚC', const Color(0xFF334063)),
            const SizedBox(width: 6),
            _thumb('SAU', const Color(0xFF3A3550)),
          ]),
          const SizedBox(width: 14),
        ],
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Đối chiếu & bổ sung',
                  style: TextStyle(
                      fontSize: 15.5,
                      fontWeight: FontWeight.w800,
                      color: Colors.white)),
              const SizedBox(height: 2),
              Text(widget.formType.title,
                  style:
                      const TextStyle(fontSize: 12, color: AppColors.onNavy)),
            ],
          ),
        ),
      ]),
    );
  }

  Widget _thumb(String label, Color bg) => Container(
        width: 62,
        height: 40,
        alignment: Alignment.bottomLeft,
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(7),
          border: Border.all(color: AppColors.star.withValues(alpha: .55), width: 1.5),
        ),
        child: Text(label,
            style: const TextStyle(
                fontSize: 8,
                fontWeight: FontWeight.w700,
                color: AppColors.star)),
      );

  Widget _validityBar() {
    final pct = _validPercent;
    final color = pct >= 90
        ? AppColors.valid
        : (pct >= 70 ? AppColors.warn : AppColors.flagRed);
    return Container(
      color: AppColors.tint,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      child: Row(children: [
        const Text('Trường đã hợp lệ',
            style: TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
                color: AppColors.inkSoft)),
        const SizedBox(width: 10),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(5),
            child: _ValidityBar(value: pct / 100, color: color),
          ),
        ),
        const SizedBox(width: 10),
        Text('$pct%',
            style: TextStyle(
                fontSize: 12.5, fontWeight: FontWeight.w800, color: color)),
      ]),
    );
  }

  Widget _cardField(_Def d) {
    final issues = _issuesOf(d.key);
    final blocking = issues.any((i) => i.blocks);
    final warning = issues.isNotEmpty;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: CustomTextField(
        label: d.label,
        controller: _card[d.key]!,
        status: warning ? FieldStatus.warning : FieldStatus.valid,
        statusText: blocking
            ? '⚠ Chưa hợp lệ'
            : (warning ? '⚠ Cần kiểm tra' : '✓ Hợp lệ'),
        helper: issues.isEmpty ? null : issues.map((i) => i.message).join('\n'),
        multiline: d.multiline,
        mono: d.mono,
        keyboardType: d.mono ? TextInputType.number : null,
      ),
    );
  }

  Widget _suppField(SuppField s) {
    final c = _supp[s.key]!;
    final filled = c.text.trim().isNotEmpty;
    final errored = !filled && _touched;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: CustomTextField(
        label: s.label,
        controller: c,
        hint: s.hint,
        status: filled
            ? FieldStatus.valid
            : (errored ? FieldStatus.warning : FieldStatus.pending),
        statusText:
            filled ? '✓ Đã nhập' : (errored ? '⚠ Bắt buộc' : 'Cần nhập'),
        helper: errored ? 'Trường bắt buộc — vui lòng nhập.' : null,
      ),
    );
  }

  Widget _bottomBar() {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: AppColors.lineSoft)),
      ),
      padding: EdgeInsets.fromLTRB(
          20, 11, 20, MediaQuery.of(context).padding.bottom + 14),
      child: Column(children: [
        if (_touched && !_canContinue)
          const Padding(
            padding: EdgeInsets.only(bottom: 9),
            child: Text(
                '⚠ Còn trường chưa hợp lệ hoặc chưa nhập — vui lòng kiểm tra lại',
                style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppColors.flagRed)),
          ),
        Row(children: [
          SizedBox(
            width: 56,
            height: 54,
            child: OutlinedButton(
              onPressed: () => Navigator.of(context).maybePop(),
              style: OutlinedButton.styleFrom(
                padding: EdgeInsets.zero,
                side: const BorderSide(color: AppColors.line, width: 1.5),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadius.button)),
              ),
              // Từ luồng quét: nút này = chụp lại; còn lại: chỉ là quay lại.
              child: Icon(
                  widget.fromScan
                      ? Icons.camera_alt_outlined
                      : Icons.arrow_back,
                  color: AppColors.navy,
                  size: 20),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: SizedBox(
              height: 54,
              child: ElevatedButton(
                onPressed: _continue,
                style: ElevatedButton.styleFrom(
                  backgroundColor:
                      _canContinue ? AppColors.flagRed : AppColors.flagRedSoft,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
                child: const Text('Xem biểu mẫu hoàn chỉnh',
                    style: TextStyle(
                        fontSize: 16.5, fontWeight: FontWeight.w700)),
              ),
            ),
          ),
        ]),
      ]),
    );
  }
}