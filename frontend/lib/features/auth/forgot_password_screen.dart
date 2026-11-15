import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/validation/validators.dart';
import '../../data/api/api_exception.dart';
import '../../data/session/session_store.dart';

/// Quên mật khẩu — xác thực qua email bằng mã OTP 6 số.
///
/// Bước 1: nhập email → `POST /api/v1/auth/forgot-password` (server luôn trả
/// cùng một thông báo, không tiết lộ email có tài khoản hay không).
/// Bước 2: nhập mã + mật khẩu mới (x2) → `POST /api/v1/auth/reset-password`.
///
/// Thành công → `Navigator.pop(email)` để màn đăng nhập điền sẵn email.
class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key, this.initialEmail = ''});

  final String initialEmail;

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  /// Khớp `RESET_RESEND_SECONDS` trong backend/config.py.
  static const _resendSeconds = 60;

  late final TextEditingController _email =
      TextEditingController(text: widget.initialEmail);
  final _code = TextEditingController();
  final _pw = TextEditingController();
  final _pwConfirm = TextEditingController();

  int _step = 0; // 0 = nhập email, 1 = nhập mã + mật khẩu mới
  bool _busy = false;
  bool _showPw = false;
  Map<String, String> _err = {};
  String? _apiError;
  String? _sentMessage;
  int _cooldown = 0;
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    _email.dispose();
    _code.dispose();
    _pw.dispose();
    _pwConfirm.dispose();
    super.dispose();
  }

  void _startCooldown() {
    _timer?.cancel();
    setState(() => _cooldown = _resendSeconds);
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) {
        t.cancel();
        return;
      }
      setState(() => _cooldown--);
      if (_cooldown <= 0) t.cancel();
    });
  }

  String _errorText(Object err) => err is ApiException
      ? err.userMessage
      : 'Không kết nối được máy chủ. Thử lại sau.';

  /// Bước 1 (và nút "Gửi lại mã").
  Future<void> _sendCode() async {
    final email = _email.text.trim();
    if (!Validators.email(email)) {
      setState(() => _err = {'email': 'Email không hợp lệ'});
      return;
    }
    setState(() {
      _err = {};
      _apiError = null;
      _busy = true;
    });
    try {
      final msg = await sessionStore.forgotPassword(email);
      if (!mounted) return;
      setState(() {
        _sentMessage = msg;
        _step = 1;
        _code.clear();
      });
      _startCooldown();
    } catch (err) {
      if (mounted) setState(() => _apiError = _errorText(err));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Bước 2.
  Future<void> _reset() async {
    final e = <String, String>{};
    if (!RegExp(r'^\d{6}$').hasMatch(_code.text.trim())) {
      e['code'] = 'Mã xác thực gồm 6 chữ số';
    }
    if (!Validators.strongPassword(_pw.text)) {
      e['pw'] = 'Mật khẩu tối thiểu 8 ký tự, có chữ và số';
    }
    if (_pwConfirm.text.isEmpty) {
      e['pwConfirm'] = 'Vui lòng nhập lại mật khẩu';
    } else if (_pwConfirm.text != _pw.text) {
      e['pwConfirm'] = 'Mật khẩu nhập lại không khớp';
    }
    setState(() {
      _err = e;
      _apiError = null;
    });
    if (e.isNotEmpty) return;

    setState(() => _busy = true);
    try {
      await sessionStore.resetPassword(
        email: _email.text.trim(),
        code: _code.text.trim(),
        newPassword: _pw.text,
      );
      if (!mounted) return;
      Navigator.of(context).pop(_email.text.trim());
    } catch (err) {
      if (mounted) setState(() => _apiError = _errorText(err));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _back() {
    if (_step == 1 && !_busy) {
      setState(() {
        _step = 0;
        _err = {};
        _apiError = null;
      });
    } else {
      Navigator.of(context).maybePop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      // Ở bước 2, nút Back hệ thống quay về bước 1 thay vì thoát màn.
      canPop: _step == 0,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: Scaffold(
        backgroundColor: AppColors.bg,
        body: Column(
          children: [
            _header(context),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(24, 18, 24, 18),
                children: _step == 0 ? _emailStep() : _resetStep(),
              ),
            ),
            _bottomBar(
              child: SizedBox(
                height: 54,
                child: ElevatedButton(
                  onPressed: _busy ? null : (_step == 0 ? _sendCode : _reset),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.flagRed,
                    disabledBackgroundColor: AppColors.flagRedSoft,
                    foregroundColor: Colors.white,
                    disabledForegroundColor: Colors.white,
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                        borderRadius:
                            BorderRadius.circular(AppRadius.button)),
                  ),
                  child: _busy
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                              color: Colors.white, strokeWidth: 2.5))
                      : Text(_step == 0 ? 'Gửi mã xác thực' : 'Đặt lại mật khẩu',
                          style: const TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w700)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _emailStep() => [
        _note(Icons.mail_outline,
            'Nhập email đã dùng để đăng ký. Chúng tôi sẽ gửi mã xác thực gồm '
            '6 chữ số tới email này.'),
        const SizedBox(height: 18),
        _field('Email', _email,
            hint: 'email@example.com',
            error: _err['email'],
            keyboardType: TextInputType.emailAddress),
        ..._apiErrorBox(),
      ];

  List<Widget> _resetStep() => [
        _note(Icons.mark_email_read_outlined,
            '${_sentMessage ?? ''}\nEmail: ${_email.text.trim()}'),
        const SizedBox(height: 18),
        _field('Mã xác thực', _code,
            hint: '6 chữ số trong email',
            error: _err['code'],
            keyboardType: TextInputType.number,
            maxLength: 6),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(
            onPressed: (_busy || _cooldown > 0) ? null : _sendCode,
            child: Text(
                _cooldown > 0 ? 'Gửi lại mã sau ${_cooldown}s' : 'Gửi lại mã',
                style: const TextStyle(
                    fontSize: 13, fontWeight: FontWeight.w600)),
          ),
        ),
        _field('Mật khẩu mới', _pw,
            hint: 'Tối thiểu 8 ký tự, có chữ và số',
            error: _err['pw'],
            obscure: !_showPw,
            trailing: GestureDetector(
              onTap: () => setState(() => _showPw = !_showPw),
              child: Padding(
                padding: const EdgeInsets.only(right: 14),
                child: Text(_showPw ? 'Ẩn' : 'Hiện',
                    style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: AppColors.cobalt)),
              ),
            )),
        const SizedBox(height: 15),
        _field('Nhập lại mật khẩu mới', _pwConfirm,
            hint: 'Nhập lại mật khẩu ở trên',
            error: _err['pwConfirm'],
            obscure: !_showPw),
        const SizedBox(height: 12),
        const Text(
            'Sau khi đặt lại, mọi phiên đăng nhập trên các thiết bị khác sẽ bị '
            'đăng xuất.',
            style: TextStyle(fontSize: 12, color: AppColors.muted)),
        ..._apiErrorBox(),
      ];

  List<Widget> _apiErrorBox() => _apiError == null
      ? const []
      : [
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            decoration: BoxDecoration(
              color: const Color(0xFFFDECEA),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFF3C6C3), width: 1),
            ),
            child: Row(children: [
              const Icon(Icons.error_outline,
                  size: 17, color: AppColors.flagRed),
              const SizedBox(width: 9),
              Expanded(
                child: Text(_apiError!,
                    style: const TextStyle(
                        fontSize: 12.5, color: AppColors.flagRed)),
              ),
            ]),
          ),
        ];

  Widget _note(IconData icon, String text) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: AppColors.tint,
          borderRadius: BorderRadius.circular(11),
        ),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 16, color: AppColors.cobalt),
          const SizedBox(width: 9),
          Expanded(
            child: Text(text,
                style: const TextStyle(
                    fontSize: 12, color: AppColors.inkSoft, height: 1.4)),
          ),
        ]),
      );

  Widget _header(BuildContext context) => Container(
        width: double.infinity,
        color: AppColors.navy,
        padding: EdgeInsets.fromLTRB(
            18, MediaQuery.of(context).padding.top + 10, 18, 18),
        child: Row(children: [
          Semantics(
            button: true,
            label: 'Quay lại',
            child: InkWell(
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
                child:
                    const Icon(Icons.arrow_back, size: 18, color: Colors.white),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
                _step == 0 ? 'Quên mật khẩu' : 'Đặt lại mật khẩu',
                style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: Colors.white)),
          ),
        ]),
      );

  Widget _field(
    String label,
    TextEditingController c, {
    String? hint,
    String? error,
    bool obscure = false,
    Widget? trailing,
    TextInputType? keyboardType,
    int? maxLength,
  }) {
    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(AppRadius.field),
      borderSide: BorderSide(
          color: error != null ? AppColors.flagRed : AppColors.line,
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
          obscureText: obscure,
          keyboardType: keyboardType,
          maxLength: maxLength,
          enabled: !_busy,
          style: const TextStyle(fontSize: 15, color: AppColors.ink),
          decoration: InputDecoration(
            isDense: true,
            counterText: '',
            hintText: hint,
            hintStyle: const TextStyle(color: AppColors.hint),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
            filled: true,
            fillColor: Colors.white,
            suffixIcon: trailing,
            suffixIconConstraints:
                const BoxConstraints(minWidth: 0, minHeight: 0),
            enabledBorder: border,
            disabledBorder: border,
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
