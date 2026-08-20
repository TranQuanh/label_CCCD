import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/session/session_store.dart';

/// Đổi mật khẩu (P2): một bước — nhập mật khẩu hiện tại + mật khẩu mới (x2) rồi
/// gọi `POST /api/v1/auth/change-password`. Không còn OTP demo.
///
/// Backend xác thực `current_password` trước, sau đó đổi mật khẩu và thu hồi
/// toàn bộ phiên khác (bump `token_version` + xoá refresh token).
class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _cur = TextEditingController();
  final _new = TextEditingController();
  final _confirm = TextEditingController();
  Map<String, String> _err = {};
  bool _busy = false;
  bool _done = false;

  @override
  void dispose() {
    _cur.dispose();
    _new.dispose();
    _confirm.dispose();
    super.dispose();
  }

  /// Kiểm tra ngay trên máy theo đúng ràng buộc của backend.
  static String? _validateNew(String v) {
    if (v.length < 8) return 'Mật khẩu mới tối thiểu 8 ký tự';
    if (!RegExp(r'[A-Za-z]').hasMatch(v) || !RegExp(r'[0-9]').hasMatch(v)) {
      return 'Mật khẩu mới phải gồm cả chữ và số';
    }
    return null;
  }

  Future<void> _submit() async {
    final e = <String, String>{};
    if (_cur.text.isEmpty) e['cur'] = 'Nhập mật khẩu hiện tại';
    final vErr = _validateNew(_new.text);
    if (vErr != null) e['new'] = vErr;
    if (_new.text.isNotEmpty && _confirm.text != _new.text) {
      e['confirm'] = 'Mật khẩu xác nhận không khớp';
    }
    setState(() => _err = e);
    if (e.isNotEmpty) return;

    setState(() => _busy = true);
    try {
      await sessionStore.changePassword(
        currentPassword: _cur.text,
        newPassword: _new.text,
      );
      if (!mounted) return;
      setState(() {
        _busy = false;
        _done = true;
      });
    } catch (err) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _err = {'cur': '$err'};
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          Container(
            width: double.infinity,
            color: AppColors.navy,
            padding: EdgeInsets.fromLTRB(
                18, MediaQuery.of(context).padding.top + 10, 18, 18),
            child: Row(children: [
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
                  child: const Icon(Icons.arrow_back,
                      size: 18, color: Colors.white),
                ),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Text('Đổi mật khẩu',
                    style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                        color: Colors.white)),
              ),
            ]),
          ),
          Expanded(
            child: _done
                ? _doneStep()
                : Column(
                    children: [
                      Expanded(
                        child: ListView(
                          padding: const EdgeInsets.fromLTRB(24, 18, 24, 18),
                          children: [
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
                                      'Mật khẩu mới tối thiểu 8 ký tự và phải gồm cả chữ lẫn số. '
                                      'Sau khi đổi, các phiên đăng nhập khác sẽ bị thu hồi.',
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
                            _pwField(
                                'Xác nhận mật khẩu mới', _confirm, _err['confirm']),
                          ],
                        ),
                      ),
                      _bottomBar(
                        child: SizedBox(
                          height: 54,
                          child: ElevatedButton(
                            onPressed: _busy ? null : _submit,
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
                                : const Text('Đổi mật khẩu',
                                    style: TextStyle(
                                        fontSize: 16,
                                        fontWeight: FontWeight.w700)),
                          ),
                        ),
                      ),
                    ],
                  ),
          ),
        ],
      ),
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