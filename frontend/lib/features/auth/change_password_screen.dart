import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/app_theme.dart';

/// Đổi mật khẩu: Bước 1 nhập mật khẩu -> Bước 2 xác thực OTP -> Thành công.
///
/// CẢNH BÁO PHẠM VI: luồng OTP ở đây là **demo cục bộ** — mã cố định `123456`,
/// so sánh ngay trên máy và còn được in ra màn hình. Không có giá trị bảo mật nào.
/// Khi nối backend: gọi API gửi OTP, xác thực phía server, và xoá cả hằng
/// `_demoOtp` lẫn dòng "Mã demo" trong giao diện.
class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

enum _PwStep { form, otp, done }

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  _PwStep _step = _PwStep.form;
  final _cur = TextEditingController();
  final _new = TextEditingController();
  final _confirm = TextEditingController();
  final _otp = TextEditingController();
  Map<String, String> _err = {};
  bool _resent = false;

  /// Mã OTP demo. Khi nối backend, xác thực qua API thay vì so sánh cứng.
  static const _demoOtp = '123456';

  @override
  void initState() {
    super.initState();
    // Lọc chữ số bằng `inputFormatters` ở chính TextField (xem bước 2) thay vì
    // sửa `_otp.text` bên trong listener của chính nó — cách cũ tự kích hoạt lại
    // listener và dễ thành vòng lặp khi thêm ràng buộc mới.
    _otp.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _cur.dispose();
    _new.dispose();
    _confirm.dispose();
    _otp.dispose();
    super.dispose();
  }

  void _submitForm() {
    final e = <String, String>{};
    if (_cur.text.length < 6) {
      e['cur'] = 'Mật khẩu hiện tại không đúng định dạng';
    }
    if (_new.text.length < 6) e['new'] = 'Mật khẩu mới tối thiểu 6 ký tự';
    if (_new.text.isNotEmpty && _confirm.text != _new.text) {
      e['confirm'] = 'Mật khẩu xác nhận không khớp';
    }
    setState(() => _err = e);
    if (e.isEmpty) {
      setState(() {
        _step = _PwStep.otp;
        _otp.clear();
        _resent = false;
      });
    }
  }

  void _confirmOtp() {
    if (_otp.text.length != 6) return;
    if (_otp.text != _demoOtp) {
      setState(() => _err = {'otp': 'Mã OTP không đúng'});
      return;
    }
    setState(() {
      _err = {};
      _step = _PwStep.done;
    });
  }

  void _back() {
    if (_step == _PwStep.otp) {
      setState(() => _step = _PwStep.form);
    } else {
      Navigator.of(context).maybePop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          // Header
          Container(
            width: double.infinity,
            color: AppColors.navy,
            padding: EdgeInsets.fromLTRB(
                18, MediaQuery.of(context).padding.top + 10, 18, 18),
            child: Row(children: [
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
                  child: const Icon(Icons.arrow_back,
                      size: 18, color: Colors.white),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Đổi mật khẩu',
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: Colors.white)),
                    Text(_stepLabel,
                        style: const TextStyle(
                            fontSize: 11.5, color: AppColors.onNavy)),
                  ],
                ),
              ),
            ]),
          ),
          if (_step != _PwStep.done) _stepIndicator(),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  String get _stepLabel {
    switch (_step) {
      case _PwStep.form:
        return 'Bước 1/2 · Nhập mật khẩu mới';
      case _PwStep.otp:
        return 'Bước 2/2 · Xác thực OTP';
      case _PwStep.done:
        return 'Hoàn tất';
    }
  }

  Widget _stepIndicator() {
    final onForm = _step == _PwStep.form;
    final c1 = onForm ? AppColors.navy : AppColors.valid;
    final c2 = onForm ? AppColors.inactive : AppColors.navy;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 14, 24, 4),
      child: Row(children: [
        _dot(onForm ? '1' : '✓', c1),
        const SizedBox(width: 7),
        Text('Mật khẩu mới',
            style: TextStyle(
                fontSize: 12.5, fontWeight: FontWeight.w700, color: c1)),
        Expanded(
          child: Container(
              height: 2,
              margin: const EdgeInsets.symmetric(horizontal: 8),
              color: const Color(0xFFDCE3EF)),
        ),
        _dot('2', c2),
        const SizedBox(width: 7),
        Text('Xác thực OTP',
            style: TextStyle(
                fontSize: 12.5, fontWeight: FontWeight.w700, color: c2)),
      ]),
    );
  }

  Widget _dot(String t, Color c) => Container(
        width: 24,
        height: 24,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: c, width: 2),
        ),
        child: Text(t,
            style: TextStyle(
                fontSize: 12, fontWeight: FontWeight.w800, color: c)),
      );

  Widget _body() {
    switch (_step) {
      case _PwStep.form:
        return _formStep();
      case _PwStep.otp:
        return _otpStep();
      case _PwStep.done:
        return _doneStep();
    }
  }

  // ---------- Bước 1 ----------
  Widget _formStep() {
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 18, 24, 18),
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: AppColors.tint,
                  borderRadius: BorderRadius.circular(11),
                ),
                child: const Row(children: [
                  Icon(Icons.lock_outline, size: 16, color: AppColors.cobalt),
                  SizedBox(width: 9),
                  Expanded(
                    child: Text(
                        'Mật khẩu mới tối thiểu 6 ký tự, nên gồm chữ và số.',
                        style: TextStyle(
                            fontSize: 12,
                            color: AppColors.inkSoft,
                            height: 1.4)),
                  ),
                ]),
              ),
              const SizedBox(height: 18),
              _pwField('Mật khẩu hiện tại', _cur, _err['cur']),
              const SizedBox(height: 15),
              _pwField('Mật khẩu mới', _new, _err['new']),
              const SizedBox(height: 15),
              _pwField('Xác nhận mật khẩu mới', _confirm, _err['confirm']),
            ],
          ),
        ),
        _bottomBar(
          child: SizedBox(
            height: 54,
            child: ElevatedButton(
              onPressed: _submitForm,
              style: _redBtn(),
              child: const Text('Gửi mã OTP',
                  style:
                      TextStyle(fontSize: 16.5, fontWeight: FontWeight.w700)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _pwField(String label, TextEditingController c, String? error) {
    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(AppRadius.field),
      borderSide: BorderSide(
          color: error != null
              ? AppColors.flagRed
              : (c.text.isNotEmpty ? AppColors.cobalt : AppColors.line),
          width: 1.5),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: AppColors.inkSoft)),
        const SizedBox(height: 7),
        TextField(
          controller: c,
          obscureText: true,
          onChanged: (_) => setState(() {}),
          style: const TextStyle(fontSize: 15, color: AppColors.ink),
          decoration: InputDecoration(
            isDense: true,
            hintText: '••••••••',
            hintStyle: const TextStyle(color: AppColors.hint),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
            filled: true,
            fillColor: Colors.white,
            enabledBorder: border,
            focusedBorder: border.copyWith(
                borderSide:
                    const BorderSide(color: AppColors.cobalt, width: 2)),
          ),
        ),
        if (error != null) ...[
          const SizedBox(height: 6),
          Text(error,
              style:
                  const TextStyle(fontSize: 11.5, color: AppColors.flagRed)),
        ],
      ],
    );
  }

  // ---------- Bước 2: OTP ----------
  Widget _otpStep() {
    final filled = _otp.text.length;
    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Center(
                child: Container(
                  width: 72,
                  height: 72,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: AppColors.tint,
                    borderRadius: BorderRadius.circular(18),
                  ),
                  child: const Icon(Icons.lock_person_outlined,
                      size: 34, color: AppColors.cobalt),
                ),
              ),
              const SizedBox(height: 16),
              const Center(
                child: Text('Nhập mã xác thực',
                    style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w800,
                        color: AppColors.ink)),
              ),
              const SizedBox(height: 6),
              const Center(
                child: Text('Mã OTP gồm 6 số đã được gửi tới\nsố điện thoại 0901 234 ***',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        fontSize: 13, color: AppColors.muted, height: 1.5)),
              ),
              const SizedBox(height: 22),
              // 6 ô OTP + input trong suốt phủ lên
              Center(
                child: SizedBox(
                  width: 6 * 44 + 5 * 9,
                  height: 56,
                  child: Stack(children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: List.generate(6, (i) {
                        final active = i == filled;
                        final has = i < filled;
                        final color = (has || active)
                            ? AppColors.cobalt
                            : AppColors.line;
                        return Container(
                          width: 44,
                          height: 56,
                          alignment: Alignment.center,
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: color, width: 2),
                            boxShadow: active
                                ? [
                                    BoxShadow(
                                        color:
                                            AppColors.cobalt.withValues(alpha: .14),
                                        spreadRadius: 3,
                                        blurRadius: 0)
                                  ]
                                : null,
                          ),
                          child: Text(has ? _otp.text[i] : '',
                              style: const TextStyle(
                                  fontSize: 24,
                                  fontWeight: FontWeight.w800,
                                  color: AppColors.navy)),
                        );
                      }),
                    ),
                    Positioned.fill(
                      child: TextField(
                        controller: _otp,
                        keyboardType: TextInputType.number,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                        ],
                        maxLength: 6,
                        showCursor: false,
                        autofocus: true,
                        style: const TextStyle(color: Colors.transparent),
                        decoration: const InputDecoration(
                          counterText: '',
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                  ]),
                ),
              ),
              if (_err['otp'] != null) ...[
                const SizedBox(height: 10),
                Center(
                  child: Text(_err['otp']!,
                      style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: AppColors.flagRed)),
                ),
              ],
              const SizedBox(height: 16),
              const Center(
                child: Text('Mã demo: 123456',
                    style: TextStyle(
                        fontSize: 12,
                        color: AppColors.hint,
                        fontFamily: 'monospace')),
              ),
              const SizedBox(height: 18),
              Center(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Text('Không nhận được mã? ',
                        style: TextStyle(
                            fontSize: 13, color: AppColors.inkSoft)),
                    GestureDetector(
                      onTap: () => setState(() {
                        _resent = true;
                        _otp.clear();
                        _err = {};
                      }),
                      child: const Text('Gửi lại',
                          style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w700,
                              color: AppColors.cobalt)),
                    ),
                  ],
                ),
              ),
              if (_resent) ...[
                const SizedBox(height: 10),
                const Center(
                  child: Text('✓ Đã gửi lại mã OTP mới',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: AppColors.valid)),
                ),
              ],
            ],
          ),
        ),
        _bottomBar(
          child: SizedBox(
            height: 54,
            child: ElevatedButton(
              onPressed: filled == 6 ? _confirmOtp : null,
              style: _redBtn(),
              child: const Text('Xác nhận',
                  style:
                      TextStyle(fontSize: 16.5, fontWeight: FontWeight.w700)),
            ),
          ),
        ),
      ],
    );
  }

  // ---------- Bước 3 ----------
  Widget _doneStep() => Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 96,
                height: 96,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.valid,
                  boxShadow: [
                    BoxShadow(
                        color: AppColors.valid.withValues(alpha: .4),
                        blurRadius: 30,
                        offset: const Offset(0, 14)),
                  ],
                ),
                child: const Icon(Icons.check, size: 48, color: Colors.white),
              ),
              const SizedBox(height: 24),
              const Text('Đổi mật khẩu thành công',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontSize: 21,
                      fontWeight: FontWeight.w900,
                      color: AppColors.ink)),
              const SizedBox(height: 10),
              const Text(
                  'Mật khẩu của bạn đã được cập nhật. Vui lòng dùng mật khẩu mới cho lần đăng nhập tiếp theo.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontSize: 13.5, color: AppColors.muted, height: 1.5)),
              const SizedBox(height: 32),
              SizedBox(
                width: double.infinity,
                height: 54,
                child: ElevatedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.navy,
                    foregroundColor: Colors.white,
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                        borderRadius:
                            BorderRadius.circular(AppRadius.button)),
                  ),
                  child: const Text('Hoàn tất',
                      style: TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w700)),
                ),
              ),
            ],
          ),
        ),
      );

  ButtonStyle _redBtn() => ElevatedButton.styleFrom(
        backgroundColor: AppColors.flagRed,
        disabledBackgroundColor: AppColors.flagRedSoft,
        foregroundColor: Colors.white,
        disabledForegroundColor: Colors.white,
        elevation: 0,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppRadius.button)),
      );

  Widget _bottomBar({required Widget child}) => Container(
        width: double.infinity,
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: AppColors.lineSoft)),
        ),
        padding: EdgeInsets.fromLTRB(
            24, 12, 24, MediaQuery.of(context).padding.bottom + 16),
        child: child,
      );
}
