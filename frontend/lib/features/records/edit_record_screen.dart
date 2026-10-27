import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/validation/validators.dart';
import '../../core/widgets/custom_textfield.dart';
import '../../core/widgets/section_label.dart';
import '../../data/models/form_type.dart';
import '../../data/models/id_card.dart';
import '../../data/models/submitted_record.dart';
import '../../data/session/session_store.dart';
import '../../data/validation/card_rules.dart';
import '../forms/templates/form_template_registry.dart';

/// Định nghĩa một trường thẻ CCCD dùng trong màn hình sửa.
class _Def {
  final String key;
  final String label;
  final bool multiline;
  final bool mono;

  const _Def(this.key, this.label, {this.multiline = false, this.mono = false});
}

/// Thanh tiến trình hợp lệ (tái sử dụng từ ReviewScreen).
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

/// Màn hình sửa hồ sơ đã tạo.
///
/// Mở từ [PreviewScreen] khi người dùng bấm nút **Sửa** trên hồ sơ `readOnly`.
/// Không có nút quay lại phần chụp ảnh.
/// Kết quả: pop trả về [SubmittedRecord] mới nếu đã lưu, hoặc `null` nếu hủy.
class EditRecordScreen extends StatefulWidget {
  final FormType formType;
  final SubmittedRecord record;

  const EditRecordScreen({
    super.key,
    required this.formType,
    required this.record,
  });

  @override
  State<EditRecordScreen> createState() => _EditRecordScreenState();
}

class _EditRecordScreenState extends State<EditRecordScreen> {
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

  // Dữ liệu gốc bất biến — dùng để hoàn lại.
  late final IdCardData _originalCard;
  late final Map<String, String> _originalSupp;

  final Map<String, TextEditingController> _card = {};
  final Map<String, TextEditingController> _supp = {};

  bool _touched = false;
  bool _saving = false;

  Map<String, List<FieldIssue>> _issues = const {};

  @override
  void initState() {
    super.initState();
    // Lưu bản gốc bất biến.
    _originalCard = widget.record.card.clone();
    _originalSupp = Map.unmodifiable(Map<String, String>.from(widget.record.supp));

    // Khởi tạo controllers thẻ CCCD từ dữ liệu record hiện tại.
    for (final e in widget.record.card.toMap().entries) {
      final c = TextEditingController(text: e.value);
      c.addListener(_revalidate);
      _card[e.key] = c;
    }

    // Khởi tạo controllers supp từ dữ liệu record hiện tại.
    for (final s in widget.formType.supp) {
      final c = TextEditingController(text: widget.record.supp[s.key] ?? '');
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
    final card = _originalCard.clone();
    card.applyMap({for (final e in _card.entries) e.key: e.value.text});
    return card;
  }

  void _revalidate() {
    setState(() => _issues = CardRules.byField(_currentCard()));
  }

  List<FieldIssue> _issuesOf(String key) => _issues[key] ?? const [];
  bool _blocks(String key) => _issuesOf(key).any((i) => i.blocks);
  bool _warns(String key) => _issuesOf(key).isNotEmpty;

  bool get _canSave {
    final cardOk = _allDefs.every((d) => !_blocks(d.key));
    final suppOk = _supp.values.every((c) => c.text.trim().isNotEmpty);
    return cardOk && suppOk;
  }

  int get _validPercent {
    final ok = _allDefs.where((d) => !_warns(d.key)).length;
    return ((ok / _allDefs.length) * 100).round();
  }

  /// Hoàn lại toàn bộ giá trị về dữ liệu gốc, ở lại trang sửa.
  void _reset() {
    setState(() {
      _touched = false;
      final origMap = _originalCard.toMap();
      for (final e in _card.entries) {
        e.value.text = origMap[e.key] ?? '';
      }
      for (final e in _supp.entries) {
        e.value.text = _originalSupp[e.key] ?? '';
      }
      _issues = CardRules.byField(_currentCard());
    });
  }

  /// Lưu hồ sơ — gọi updateRecord, pop trả về record mới.
  Future<void> _save() async {
    if (!_canSave) {
      setState(() => _touched = true);
      return;
    }
    if (_saving) return;
    setState(() => _saving = true);

    try {
      final card = _currentCard()
        ..idNumber = Validators.normalizeIdNumber(_card['idNumber']!.text)
        ..sex = Validators.normalizeSex(_card['sex']!.text);

      final supp = {
        for (final e in _supp.entries) e.key: e.value.text.trim(),
      };

      final updated = await sessionStore.updateRecord(
        original: widget.record,
        card: card,
        supp: supp,
      );

      if (!mounted) return;
      Navigator.of(context).pop(updated);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Không lưu được hồ sơ: $e')),
      );
    }
  }

  /// Quay lại — không lưu gì.
  void _back() => Navigator.of(context).pop(null);

  // ── Helper SuppField ──────────────────────────────────────────────────────

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

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final hasTemplate = FormTemplateRegistry.hasTemplate(widget.formType.id);

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          _header(),
          _validityBar(),
          Expanded(
            child: hasTemplate ? _buildTemplateEdit() : _buildGenericEdit(),
          ),
          _bottomBar(),
        ],
      ),
    );
  }

  Widget _buildTemplateEdit() {
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
                        text: 'THÔNG TIN BỔ SUNG',
                        barColor: AppColors.flagRed,
                        textColor: Color(0xFFB01B15)),
                    const SizedBox(height: 6),
                    const Text(
                        'Kiểm tra và chỉnh sửa thông tin bổ sung.',
                        style: TextStyle(fontSize: 12, color: AppColors.muted)),
                    const SizedBox(height: 11),
                    ..._buildSuppFields(),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],
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
                      text: 'THÔNG TIN CCCD',
                      barColor: AppColors.cobalt,
                      textColor: AppColors.navy),
                  const SizedBox(height: 6),
                  const Text(
                      'Sửa nếu cần điều chỉnh.',
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
      },
    );
  }

  Widget _buildGenericEdit() {
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
            text: 'THÔNG TIN BỔ SUNG',
            barColor: AppColors.flagRed,
            textColor: Color(0xFFB01B15)),
        const SizedBox(height: 6),
        const Text(
            'Kiểm tra và chỉnh sửa nếu cần.',
            style: TextStyle(fontSize: 12, color: AppColors.muted)),
        const SizedBox(height: 11),
        ..._buildSuppFields(),
      ],
    );
  }

  // ── Header ────────────────────────────────────────────────────────────────

  Widget _header() {
    return Container(
      width: double.infinity,
      color: AppColors.navy,
      padding: EdgeInsets.fromLTRB(
          20, MediaQuery.of(context).padding.top + 12, 20, 16),
      child: Row(
        children: [
          InkWell(
            onTap: _back,
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
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Sửa hồ sơ',
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
          // Mã hồ sơ hiển thị góc phải
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: .10),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              widget.record.code,
              style: const TextStyle(
                  fontSize: 10,
                  color: AppColors.onNavy,
                  fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }

  // ── Validity bar ──────────────────────────────────────────────────────────

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

  // ── Bottom bar ────────────────────────────────────────────────────────────

  Widget _bottomBar() {
    return Container(
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: AppColors.lineSoft)),
      ),
      padding: EdgeInsets.fromLTRB(
          16, 11, 16, MediaQuery.of(context).padding.bottom + 14),
      child: Column(children: [
        if (_touched && !_canSave)
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
          // Nút Hoàn lại
          SizedBox(
            height: 54,
            child: OutlinedButton.icon(
              onPressed: _reset,
              icon: const Icon(Icons.history, size: 18),
              label: const Text('Hoàn lại',
                  style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w700)),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.inkSoft,
                side: const BorderSide(color: AppColors.line, width: 1.5),
                padding: const EdgeInsets.symmetric(horizontal: 14),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadius.button)),
              ),
            ),
          ),
          const SizedBox(width: 8),
          // Nút Quay lại
          SizedBox(
            height: 54,
            child: OutlinedButton(
              onPressed: _back,
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.navy,
                side: const BorderSide(color: AppColors.line, width: 1.5),
                padding: const EdgeInsets.symmetric(horizontal: 14),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppRadius.button)),
              ),
              child: const Text('Quay lại',
                  style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w700)),
            ),
          ),
          const SizedBox(width: 8),
          // Nút Lưu (chiếm phần còn lại)
          Expanded(
            child: SizedBox(
              height: 54,
              child: ElevatedButton.icon(
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                            color: Colors.white, strokeWidth: 2))
                    : const Icon(Icons.save_outlined, size: 20),
                label: Text(
                  _saving ? 'Đang lưu...' : 'Lưu',
                  style: const TextStyle(
                      fontSize: 15.5, fontWeight: FontWeight.w800),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor:
                      _canSave ? AppColors.flagRed : AppColors.flagRedSoft,
                  disabledBackgroundColor: AppColors.flagRedSoft,
                  foregroundColor: Colors.white,
                  disabledForegroundColor: Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
          ),
        ]),
      ]),
    );
  }

  // ── Field widgets ─────────────────────────────────────────────────────────

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
}
