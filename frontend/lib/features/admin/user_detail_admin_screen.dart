import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/validation/validators.dart';
import '../../data/api/auth_api_client.dart';
import '../../data/session/session_store.dart';
import 'admin_common.dart';
import 'audit_logs_admin_tab.dart';
import 'records_admin_tab.dart';

/// Chi tiết TÀI KHOẢN (admin).
///
/// Chỉ thông tin tài khoản và hoạt động: tên đăng nhập, email, vai trò, trạng
/// thái, phiên đang mở, số hồ sơ, lần đăng nhập gần nhất. KHÔNG có Profile
/// CCCD hay nội dung hồ sơ của người dùng.
///
/// Hành động: đổi vai trò, khóa / mở khóa, gỡ khóa tạm, đặt lại mật khẩu, đăng
/// xuất mọi thiết bị, xem danh sách hồ sơ (chỉ thông tin quản lý) và nhật ký.
/// Pop trả `true` nếu đã thay đổi gì (để danh sách tải lại).
class UserDetailAdminScreen extends StatefulWidget {
  final String userId;

  const UserDetailAdminScreen({super.key, required this.userId});

  @override
  State<UserDetailAdminScreen> createState() => _UserDetailAdminScreenState();
}

class _UserDetailAdminScreenState extends State<UserDetailAdminScreen> {
  final AuthApiClient _auth = AuthApiClient();
  Map<String, dynamic>? _user;
  String? _error;
  bool _loading = true;
  bool _busy = false;
  bool _changed = false;
  int _roleFieldSeed = 0;

  bool get _isSelf => widget.userId == sessionStore.user?.id;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _auth.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final u = await _auth.getUser(widget.userId);
      if (mounted) setState(() => _user = u);
    } catch (e) {
      if (mounted) setState(() => _error = adminErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Chạy một hành động admin, báo kết quả, rồi tải lại chi tiết.
  Future<void> _run(Future<void> Function() action, String success) async {
    setState(() => _busy = true);
    try {
      await action();
      _changed = true;
      if (!mounted) return;
      showAdminSnack(context, success);
      await _load();
    } catch (e) {
      if (mounted) showAdminSnack(context, adminErrorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<bool> _confirm(String title, String message, String action,
      {bool danger = true}) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Huỷ')),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(action,
                style: TextStyle(
                    color: danger ? AppColors.flagRed : AppColors.cobalt)),
          ),
        ],
      ),
    );
    return ok == true;
  }

  String get _name => _user?['username']?.toString() ?? '';

  Future<void> _changeRole(String role) async {
    if (role == _user?['role']) return;
    final ok = await _confirm(
        'Đổi vai trò?',
        'Tài khoản @$_name sẽ thành "${roleLabel(role)}". Người này phải đăng '
            'nhập lại.',
        'Đổi vai trò',
        danger: false);
    if (ok) {
      await _run(() => _auth.updateUser(widget.userId, {'role': role}),
          'Đã đổi vai trò của @$_name sang ${roleLabel(role)}.');
    }
    // Huỷ hoặc lỗi: dựng lại ô chọn theo vai trò thật (FormField giữ giá trị
    // vừa chọn nếu không đổi key).
    if (mounted) setState(() => _roleFieldSeed++);
  }

  Future<void> _toggleActive() async {
    final lock = _user?['is_active'] != false;
    final ok = await _confirm(
        lock ? 'Khóa tài khoản?' : 'Mở khóa tài khoản?',
        lock
            ? 'Tài khoản @$_name sẽ không đăng nhập được và bị đăng xuất khỏi '
                'mọi thiết bị.'
            : 'Tài khoản @$_name sẽ đăng nhập lại được.',
        lock ? 'Khóa' : 'Mở khóa',
        danger: lock);
    if (!ok) return;
    await _run(() => _auth.updateUser(widget.userId, {'is_active': !lock}),
        lock ? 'Đã khóa tài khoản @$_name.' : 'Đã mở khóa tài khoản @$_name.');
  }

  Future<void> _unlock() async {
    await _run(() => _auth.unlockUser(widget.userId),
        'Đã gỡ khóa đăng nhập tạm thời cho @$_name.');
  }

  Future<void> _revokeSessions() async {
    final ok = await _confirm(
        'Đăng xuất mọi thiết bị?',
        'Mọi phiên đăng nhập của @$_name sẽ bị thu hồi. Người này phải đăng '
            'nhập lại.',
        'Đăng xuất');
    if (!ok) return;
    await _run(() => _auth.revokeUserSessions(widget.userId),
        'Đã đăng xuất @$_name khỏi mọi thiết bị.');
  }

  Future<void> _resetPassword() async {
    final password = await showDialog<String>(
      context: context,
      builder: (_) => const _ResetPasswordDialog(),
    );
    if (password == null) return;
    await _run(
        () => _auth.updateUser(widget.userId, {'password': password}),
        'Đã đặt lại mật khẩu cho @$_name. Mọi phiên cũ đã bị thu hồi.');
  }

  void _openRecords() {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => AdminSubpage(
        title: 'Hồ sơ của @$_name',
        child: RecordsAdminTab(userId: widget.userId),
      ),
    ));
  }

  void _openLogs() {
    Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => AdminSubpage(
        title: 'Hoạt động của @$_name',
        child: AuditLogsAdminTab(userId: widget.userId),
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.of(context).pop(_changed);
      },
      child: Scaffold(
        backgroundColor: AppColors.bg,
        appBar: AppBar(
          backgroundColor: AppColors.navy,
          foregroundColor: Colors.white,
          title: Text(_name.isEmpty ? 'Chi tiết tài khoản' : '@$_name',
              style:
                  const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        ),
        body: _body(),
      ),
    );
  }

  Widget _body() {
    if (_loading && _user == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && _user == null) {
      return AdminErrorView(message: _error!, onRetry: _load);
    }
    final u = _user!;
    final active = u['is_active'] != false;
    final role = u['role']?.toString() ?? 'user';
    final lockedUntil = parseServerTime(u['locked_until']);
    final tempLocked =
        lockedUntil != null && lockedUntil.isAfter(DateTime.now());
    final fails = (u['failed_login_count'] as num?)?.toInt() ?? 0;

    return AbsorbPointer(
      absorbing: _busy,
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(14),
          children: [
            if (_busy) const LinearProgressIndicator(),
            _section('THÔNG TIN TÀI KHOẢN', [
              _row('Tên đăng nhập', '@${u['username'] ?? ''}'),
              _row('Họ tên tài khoản',
                  (u['full_name']?.toString() ?? '').isEmpty ? '—' : u['full_name'].toString()),
              _row('Email', u['email']?.toString() ?? '—'),
              _row('Vai trò', roleLabel(role)),
              _row('Trạng thái', active ? 'Đang hoạt động' : 'Đã bị khóa',
                  color: active ? AppColors.valid : AppColors.flagRed),
              _row('Ngày tạo', formatDateTime(u['created_at'])),
            ]),
            _section('HOẠT ĐỘNG', [
              _row('Đăng nhập gần nhất',
                  u['last_login_at'] == null ? 'Chưa có' : formatDateTime(u['last_login_at'])),
              _row('Phiên đang mở', '${u['active_sessions'] ?? 0} thiết bị'),
              _row('Đăng nhập sai liên tiếp', '$fails lần'),
              if (tempLocked)
                _row('Khóa tạm đến', formatDateTime(u['locked_until']),
                    color: AppColors.warn),
              _row('Số hồ sơ',
                  '${u['record_count'] ?? 0} (đang ẩn: ${u['hidden_record_count'] ?? 0})'),
            ]),
            _section('XEM THÊM', [
              _action(Icons.folder_open_outlined, 'Danh sách hồ sơ của tài khoản',
                  _openRecords),
              _action(Icons.history, 'Nhật ký hoạt động của tài khoản', _openLogs),
            ]),
            if (_isSelf)
              const Padding(
                padding: EdgeInsets.fromLTRB(4, 4, 4, 12),
                child: Text(
                    'Đây là tài khoản của bạn — không đổi vai trò, khóa hay đăng '
                    'xuất mọi thiết bị ở đây. Đổi mật khẩu ở tab Tài khoản.',
                    style: TextStyle(fontSize: 12.5, color: AppColors.muted)),
              )
            else
              _section('QUẢN LÝ', [
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 10, 14, 6),
                  child: DropdownButtonFormField<String>(
                    key: ValueKey('role-$role-$_roleFieldSeed'),
                    initialValue: role,
                    decoration: InputDecoration(
                      isDense: true,
                      labelText: 'Vai trò',
                      border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10)),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'user', child: Text('Người dùng')),
                      DropdownMenuItem(
                          value: 'admin', child: Text('Quản trị viên')),
                    ],
                    onChanged: (v) {
                      if (v != null) _changeRole(v);
                    },
                  ),
                ),
                if (tempLocked || fails > 0)
                  _action(Icons.lock_open, 'Gỡ khóa đăng nhập tạm thời', _unlock),
                _action(Icons.password, 'Đặt lại mật khẩu', _resetPassword),
                _action(Icons.devices_other, 'Đăng xuất khỏi mọi thiết bị',
                    _revokeSessions),
                _action(active ? Icons.block : Icons.check_circle_outline,
                    active ? 'Khóa tài khoản' : 'Mở khóa tài khoản', _toggleActive,
                    color: active ? AppColors.flagRed : AppColors.valid),
              ]),
          ],
        ),
      ),
    );
  }

  Widget _section(String title, List<Widget> children) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 8),
              child: Text(title,
                  style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                      color: AppColors.muted,
                      letterSpacing: .6)),
            ),
            Material(
              color: Colors.white,
              clipBehavior: Clip.antiAlias,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppRadius.card),
                side: const BorderSide(color: AppColors.lineSoft),
              ),
              child: Column(children: children),
            ),
          ],
        ),
      );

  Widget _row(String label, String value, {Color? color}) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 150,
              child: Text(label,
                  style: const TextStyle(fontSize: 13, color: AppColors.muted)),
            ),
            Expanded(
              child: Text(value,
                  textAlign: TextAlign.right,
                  style: TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w600,
                      color: color ?? AppColors.ink)),
            ),
          ],
        ),
      );

  Widget _action(IconData icon, String label, VoidCallback onTap,
          {Color color = AppColors.cobalt}) =>
      ListTile(
        leading: Icon(icon, color: color, size: 21),
        title: Text(label,
            style: TextStyle(
                fontSize: 13.5, fontWeight: FontWeight.w600, color: color)),
        trailing: const Icon(Icons.chevron_right, color: AppColors.hint),
        onTap: onTap,
      );
}

/// Hộp thoại nhập mật khẩu mới (admin đặt lại cho người dùng).
class _ResetPasswordDialog extends StatefulWidget {
  const _ResetPasswordDialog();

  @override
  State<_ResetPasswordDialog> createState() => _ResetPasswordDialogState();
}

class _ResetPasswordDialogState extends State<_ResetPasswordDialog> {
  final _pw = TextEditingController();
  final _confirm = TextEditingController();
  String? _err;

  @override
  void dispose() {
    _pw.dispose();
    _confirm.dispose();
    super.dispose();
  }

  void _submit() {
    if (!Validators.strongPassword(_pw.text)) {
      setState(() => _err = 'Mật khẩu tối thiểu 8 ký tự, có chữ và số');
      return;
    }
    if (_pw.text != _confirm.text) {
      setState(() => _err = 'Mật khẩu xác nhận không khớp');
      return;
    }
    Navigator.of(context).pop(_pw.text);
  }

  @override
  Widget build(BuildContext context) {
    InputDecoration deco(String label) => InputDecoration(
          isDense: true,
          labelText: label,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
        );
    return AlertDialog(
      title: const Text('Đặt lại mật khẩu'),
      content: Column(mainAxisSize: MainAxisSize.min, children: [
        TextField(controller: _pw, obscureText: true, decoration: deco('Mật khẩu mới')),
        const SizedBox(height: 10),
        TextField(
            controller: _confirm,
            obscureText: true,
            decoration: deco('Nhập lại mật khẩu mới')),
        if (_err != null) ...[
          const SizedBox(height: 10),
          Text(_err!,
              style: const TextStyle(color: AppColors.flagRed, fontSize: 12.5)),
        ],
        const SizedBox(height: 10),
        const Text(
            'Người dùng sẽ bị đăng xuất khỏi mọi thiết bị và phải đăng nhập bằng '
            'mật khẩu mới.',
            style: TextStyle(fontSize: 12, color: AppColors.muted)),
      ]),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Huỷ')),
        ElevatedButton(onPressed: _submit, child: const Text('Đặt lại')),
      ],
    );
  }
}
