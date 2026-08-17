import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/validation/validators.dart';
import '../../data/session/session_store.dart';
import '../shell/home_shell.dart';

/// Màn hình 1 — Đăng nhập / Đăng ký.
///
/// Lưu ý phạm vi: đây là form **cục bộ**, chưa có xác thực thật. Không có token,
/// không có phiên phía server, mật khẩu không rời khỏi máy. Trước khi đưa vào sử
/// dụng thật phải nối vào một dịch vụ xác thực và bỏ dòng cam kết bảo mật ở dưới
/// nếu chưa triển khai đúng như cam kết.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  bool _register = false;
  bool _showPw = false;
  final _user = TextEditingController();
  final _email = TextEditingController();
  final _pw = TextEditingController();
  final _dob = TextEditingController();
  Map<String, String> _err = {};

  @override
  void dispose() {
    _user.dispose();
    _email.dispose();
    _pw.dispose();
    _dob.dispose();
    super.dispose();
  }

  void _submit() {
    final e = <String, String>{};
    if (_user.text.trim().isEmpty) e['user'] = 'Vui lòng nhập tên đăng nhập';
    if (_pw.text.length < 6) e['pw'] = 'Mật khẩu tối thiểu 6 ký tự';
    if (_register) {
      if (!Validators.email(_email.text)) e['email'] = 'Email không hợp lệ';
      if (!Validators.pastDate(_dob.text)) {
        e['dob'] = 'Ngày sinh phải có thật, định dạng DD/MM/YYYY';
      }
    }
    setState(() => _err = e);
    if (e.isNotEmpty) return;

    sessionStore.login(AuthUser(
      username: _user.text.trim(),
      email: _register ? _email.text.trim() : sessionStore.email,
      dob: _register ? _dob.text.trim() : sessionStore.dob,
    ));
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const HomeShell()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          _header(context),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(24, 22, 24, 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Container(
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE7ECF5),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(children: [
                      _tab('Đăng nhập', !_register, () => _switch(false)),
                      _tab('Đăng ký', _register, () => _switch(true)),
                    ]),
                  ),
                  const SizedBox(height: 22),
                  _field('Tên đăng nhập', _user,
                      hint: 'nguyenvana', error: _err['user']),
                  if (_register) ...[
                    const SizedBox(height: 15),
                    _field('Email', _email,
                        hint: 'email@example.com',
                        error: _err['email'],
                        keyboardType: TextInputType.emailAddress),
                  ],
                  const SizedBox(height: 15),
                  _field('Mật khẩu', _pw,
                      hint: '••••••••',
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
                  if (_register) ...[
                    const SizedBox(height: 15),
                    _field('Ngày sinh', _dob,
                        hint: 'DD / MM / YYYY', error: _err['dob']),
                  ],
                  const SizedBox(height: 22),
                  SizedBox(
                    height: 56,
                    child: ElevatedButton(
                      onPressed: _submit,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.flagRed,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(AppRadius.button)),
                      ),
                      child: Text(_register ? 'Tạo tài khoản' : 'Đăng nhập',
                          style: const TextStyle(
                              fontSize: 17, fontWeight: FontWeight.w700)),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Center(
                    child: GestureDetector(
                      onTap: () => _switch(!_register),
                      child: Text(
                          _register
                              ? 'Đã có tài khoản? Đăng nhập'
                              : 'Chưa có tài khoản? Đăng ký',
                          style: const TextStyle(
                              fontSize: 13.5, color: AppColors.inkSoft)),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 12),
                    decoration: BoxDecoration(
                      color: AppColors.tint,
                      borderRadius: BorderRadius.circular(11),
                    ),
                    child: const Row(children: [
                      Icon(Icons.lock_outline,
                          size: 16, color: AppColors.cobalt),
                      SizedBox(width: 9),
                      Expanded(
                        child: Text(
                            'Ảnh thẻ chỉ được gửi tới máy chủ trích xuất và bị xoá '
                            'khỏi thiết bị ngay sau khi đọc xong.',
                            style: TextStyle(
                                fontSize: 12, color: AppColors.inkSoft)),
                      ),
                    ]),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _switch(bool register) => setState(() {
        _register = register;
        _err = {};
      });

  Widget _header(BuildContext context) => Container(
        width: double.infinity,
        padding: EdgeInsets.fromLTRB(
            28, MediaQuery.of(context).padding.top + 26, 28, 30),
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AppColors.navy, AppColors.navySoft],
          ),
        ),
        child: Column(
          children: [
            Container(
              width: 66,
              height: 66,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withOpacity(.10),
                border:
                    Border.all(color: AppColors.star.withOpacity(.7), width: 2),
              ),
              child: const Text('★',
                  style: TextStyle(color: AppColors.star, fontSize: 32)),
            ),
            const SizedBox(height: 14),
            const Text('CỔNG DỊCH VỤ CÔNG',
                style: TextStyle(
                    fontSize: 11.5,
                    letterSpacing: 2,
                    fontWeight: FontWeight.w700,
                    color: AppColors.onNavy)),
            const SizedBox(height: 5),
            const Text('Định danh SmartID',
                style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w900,
                    color: Colors.white)),
          ],
        ),
      );

  Widget _tab(String label, bool active, VoidCallback onTap) => Expanded(
        child: GestureDetector(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 11),
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: active ? Colors.white : Colors.transparent,
              borderRadius: BorderRadius.circular(9),
              boxShadow: active
                  ? [
                      BoxShadow(
                          color: AppColors.navy.withOpacity(.12),
                          blurRadius: 6,
                          offset: const Offset(0, 2))
                    ]
                  : null,
            ),
            child: Text(label,
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: active ? FontWeight.w700 : FontWeight.w600,
                    color: active ? AppColors.navy : const Color(0xFF5A6785))),
          ),
        ),
      );

  Widget _field(
    String label,
    TextEditingController c, {
    String? hint,
    String? error,
    bool obscure = false,
    Widget? trailing,
    TextInputType? keyboardType,
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
          style: const TextStyle(fontSize: 15, color: AppColors.ink),
          decoration: InputDecoration(
            isDense: true,
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
}
