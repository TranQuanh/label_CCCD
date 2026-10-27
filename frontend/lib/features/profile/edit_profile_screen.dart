import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/validation/validators.dart';
import '../../core/widgets/custom_textfield.dart';
import '../../core/widgets/section_label.dart';
import '../../data/api/api_exception.dart';
import '../../data/models/id_card.dart';
import '../../data/session/session_store.dart';
import '../../data/validation/card_rules.dart';

/// Màn hình chỉnh sửa hoặc thiết lập thủ công thông tin Profile CCCD.
class EditProfileScreen extends StatefulWidget {
  final IdCardData? initialCard;
  final bool isInitialScan;
  final int? profileIndex; // Index of profile being edited (null for new profile)

  const EditProfileScreen({
    super.key,
    this.initialCard,
    this.isInitialScan = false,
    this.profileIndex,
  });

  @override
  State<EditProfileScreen> createState() => _EditProfileScreenState();
}

class _EditProfileScreenState extends State<EditProfileScreen> {
  final Map<String, TextEditingController> _ctrls = {};
  bool _saving = false;
  bool _touched = false;
  Map<String, List<FieldIssue>> _issues = const {};

  /// Profile đang sửa (null = tạo mới). Giữ THAM CHIẾU thay vì chỉ số: lúc bấm
  /// Lưu mới tìm lại vị trí, phòng trường hợp danh sách đã nạp lại/đổi thứ tự.
  IdCardData? _target;

  static const _frontFields = <List<String>>[
    ['fullName', 'Họ và tên', 'NGUYỄN VĂN A'],
    ['idNumber', 'Số CCCD (12 chữ số)', '001201123456'],
    ['dob', 'Ngày sinh (DD/MM/YYYY)', '01/01/1990'],
    ['sex', 'Giới tính', 'Nam / Nữ'],
    ['nationality', 'Quốc tịch', 'Việt Nam'],
    ['origin', 'Quê quán', 'Xã/Huyện/Tỉnh'],
    ['residence', 'Nơi thường trú', 'Số nhà, Phường/Xã, Quận/Huyện, Tỉnh/TP'],
  ];

  static const _backFields = <List<String>>[
    ['issueDate', 'Ngày cấp (DD/MM/YYYY)', '01/01/2021'],
    ['expiry', 'Có giá trị đến (DD/MM/YYYY)', '01/01/2030 hoặc để trống'],
    ['issuePlace', 'Nơi cấp', 'Cục Cảnh sát QLHC về TTXH'],
    ['features', 'Đặc điểm nhận dạng', 'Nốt ruồi / Không có'],
  ];

  @override
  void initState() {
    super.initState();
    // Tạo mới (không initialCard, không profileIndex) → form TRỐNG; không điền
    // sẵn profile mặc định (trước đây làm lưu ra bản trùng).
    final idx = widget.profileIndex;
    final profiles = sessionStore.profiles;
    _target = (idx != null && idx >= 0 && idx < profiles.length)
        ? profiles[idx]
        : null;
    final base = widget.initialCard ?? _target ?? IdCardData();
    final map = base.toMap();

    for (final e in map.entries) {
      final c = TextEditingController(text: e.value);
      c.addListener(_revalidate);
      _ctrls[e.key] = c;
    }
    _issues = CardRules.byField(_currentCard());
  }

  @override
  void dispose() {
    for (final c in _ctrls.values) {
      c.dispose();
    }
    super.dispose();
  }

  IdCardData _currentCard() {
    return IdCardData(
      fullName: _ctrls['fullName']?.text.trim() ?? '',
      idNumber: _ctrls['idNumber']?.text.trim() ?? '',
      dob: _ctrls['dob']?.text.trim() ?? '',
      sex: _ctrls['sex']?.text.trim() ?? '',
      nationality: _ctrls['nationality']?.text.trim().isNotEmpty == true
          ? _ctrls['nationality']!.text.trim()
          : 'Việt Nam',
      origin: _ctrls['origin']?.text.trim() ?? '',
      residence: _ctrls['residence']?.text.trim() ?? '',
      issueDate: _ctrls['issueDate']?.text.trim() ?? '',
      expiry: _ctrls['expiry']?.text.trim() ?? '',
      issuePlace: _ctrls['issuePlace']?.text.trim() ?? '',
      features: _ctrls['features']?.text.trim() ?? '',
    );
  }

  void _revalidate() {
    setState(() => _issues = CardRules.byField(_currentCard()));
  }

  List<FieldIssue> _issuesOf(String key) => _issues[key] ?? const [];

  Future<void> _save() async {
    setState(() => _touched = true);
    final card = _currentCard();

    // Chuẩn hóa họ tên, số cccd và giới tính
    if (card.fullName.isNotEmpty) {
      card.fullName = card.fullName.toUpperCase();
    }
    if (card.idNumber.isNotEmpty) {
      card.idNumber = Validators.normalizeIdNumber(card.idNumber);
    }
    if (card.sex.isNotEmpty) {
      card.sex = Validators.normalizeSex(card.sex);
    }

    if (card.fullName.isEmpty || card.idNumber.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Vui lòng nhập tối thiểu Họ và tên và Số CCCD.'),
          backgroundColor: AppColors.flagRed,
        ),
      );
      return;
    }

    setState(() => _saving = true);
    try {
      final target = _target;
      if (target != null) {
        final index = sessionStore.indexOfProfile(target);
        if (index < 0) {
          throw const ApiException(
              'Profile này không còn tồn tại (có thể đã bị xoá).');
        }
        await sessionStore.updateProfileAt(index, card);
      } else {
        await sessionStore.addProfile(card);
      }
      if (!mounted) return;
      // Lấy messenger/navigator trước khi rời màn để snackbar vẫn hiện.
      final messenger = ScaffoldMessenger.of(context);
      final navigator = Navigator.of(context);
      messenger.showSnackBar(
        const SnackBar(
          content: Text('✓ Đã lưu Profile CCCD thành công!'),
          backgroundColor: AppColors.valid,
        ),
      );
      if (widget.isInitialScan) {
        // Luồng quét: quay thẳng về màn chính (tab Profile), bỏ qua
        // Onboarding/Camera đang nằm dưới.
        navigator.popUntil((r) => r.isFirst);
      } else {
        navigator.pop(true);
      }
    } on ApiException catch (e) {
      // Trùng số CCCD (client/409 server) hoặc lỗi kết nối — giữ màn để sửa.
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.userMessage),
          backgroundColor: AppColors.flagRed,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Không lưu được Profile: $e'),
          backgroundColor: AppColors.flagRed,
        ),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        backgroundColor: AppColors.navy,
        foregroundColor: Colors.white,
        elevation: 0,
        title: Text(
          widget.isInitialScan
              ? 'Xác nhận Profile CCCD'
              : (widget.profileIndex != null
                  ? 'Chỉnh sửa Profile CCCD'
                  : 'Tạo Profile CCCD'),
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
        ),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
              children: [
                // Banner thông báo
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: AppColors.cobalt.withValues(alpha: .08),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                        color: AppColors.cobalt.withValues(alpha: .2)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.info_outline,
                          size: 20, color: AppColors.cobalt),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          widget.isInitialScan
                              ? 'Dữ liệu đã được AI trích xuất từ 2 mặt thẻ. Vui lòng kiểm tra và bấm "Lưu Profile".'
                              : 'Thông tin lưu tại đây sẽ dùng để tự động điền các biểu mẫu dịch vụ mà không cần chụp lại thẻ.',
                          style: const TextStyle(
                              fontSize: 12.5,
                              color: AppColors.inkSoft,
                              height: 1.35),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),

                // THÔNG TIN MẶT TRƯỚC
                const SectionLabel(
                  text: 'THÔNG TIN MẶT TRƯỚC THẺ CCCD',
                  barColor: AppColors.flagRed,
                  textColor: Color(0xFFB01B15),
                ),
                const SizedBox(height: 10),
                ..._frontFields.map((f) => _fieldWidget(f[0], f[1], f[2])),

                const SizedBox(height: 16),

                // THÔNG TIN MẶT SAU
                const SectionLabel(
                  text: 'THÔNG TIN MẶT SAU THẺ CCCD',
                  barColor: AppColors.navy,
                  textColor: AppColors.navy,
                ),
                const SizedBox(height: 10),
                ..._backFields.map((f) => _fieldWidget(f[0], f[1], f[2])),
              ],
            ),
          ),
          _bottomBar(),
        ],
      ),
    );
  }

  Widget _fieldWidget(String key, String label, String hint) {
    final c = _ctrls[key]!;
    final issues = _issuesOf(key);
    final warning = issues.isNotEmpty && _touched;
    final isMulti = key == 'residence' || key == 'features' || key == 'issuePlace';
    final isMono = key == 'idNumber';

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: CustomTextField(
        label: label,
        controller: c,
        hint: hint,
        multiline: isMulti,
        mono: isMono,
        keyboardType: isMono ? TextInputType.number : null,
        status: warning ? FieldStatus.warning : FieldStatus.valid,
        statusText: warning ? '⚠ Cần xem lại' : '',
        helper: warning ? issues.map((i) => i.message).join('\n') : null,
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
          20, 12, 20, MediaQuery.of(context).padding.bottom + 14),
      child: SizedBox(
        width: double.infinity,
        height: 52,
        child: ElevatedButton.icon(
          onPressed: _saving ? null : _save,
          icon: _saving
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.white),
                )
              : const Icon(Icons.check_circle_outline, size: 20),
          label: Text(
            _saving ? 'Đang lưu…' : 'Lưu thông tin Profile',
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          style: ElevatedButton.styleFrom(
            backgroundColor: AppColors.flagRed,
            foregroundColor: Colors.white,
            elevation: 0,
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppRadius.button)),
          ),
        ),
      ),
    );
  }
}
