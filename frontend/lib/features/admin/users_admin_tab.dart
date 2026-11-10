import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/validation/validators.dart';
import '../../data/api/auth_api_client.dart';
import '../../data/session/session_store.dart';
import 'admin_common.dart';
import 'user_detail_admin_screen.dart';

/// Tab quản lý người dùng (admin): danh sách, tìm kiếm, lọc, tạo tài khoản.
/// Bấm một tài khoản → màn chi tiết (đổi vai trò, khóa/mở khóa, gỡ khóa tạm,
/// đặt lại mật khẩu, đăng xuất mọi thiết bị, xem hồ sơ / nhật ký).
class UsersAdminTab extends StatefulWidget {
  const UsersAdminTab({super.key});

  @override
  State<UsersAdminTab> createState() => _UsersAdminTabState();
}

class _UsersAdminTabState extends State<UsersAdminTab> {
  static const _filters = {
    'all': 'Tất cả',
    'admin': 'Quản trị viên',
    'user': 'Người dùng',
    'locked': 'Bị khóa',
  };

  final AuthApiClient _auth = AuthApiClient();
  final TextEditingController _search = TextEditingController();
  List<Map<String, dynamic>>? _users;
  String? _error;
  bool _loading = true;
  String _filter = 'all';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _auth.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final users = await _auth.listUsers();
      if (mounted) setState(() => _users = users);
    } catch (e) {
      if (mounted) setState(() => _error = adminErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Khóa tạm do đăng nhập sai (locked_until còn hiệu lực).
  static bool _tempLocked(Map<String, dynamic> u) {
    final until = parseServerTime(u['locked_until']);
    return until != null && until.isAfter(DateTime.now());
  }

  List<Map<String, dynamic>> get _visible {
    final q = _search.text.trim().toLowerCase();
    return (_users ?? []).where((u) {
      final active = u['is_active'] != false;
      switch (_filter) {
        case 'admin':
          if (u['role'] != 'admin') return false;
        case 'user':
          if (u['role'] == 'admin') return false;
        case 'locked':
          if (active && !_tempLocked(u)) return false;
      }
      if (q.isEmpty) return true;
      return [u['username'], u['email'], u['full_name']]
          .map((e) => (e ?? '').toString().toLowerCase())
          .any((e) => e.contains(q));
    }).toList();
  }

  Future<void> _openDetail(Map<String, dynamic> user) async {
    final changed = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => UserDetailAdminScreen(userId: user['id'].toString()),
    ));
    if (changed == true) await _load();
  }

  Future<void> _createUser() async {
    final created = await showDialog<bool>(
      context: context,
      builder: (_) => _CreateUserDialog(auth: _auth),
    );
    if (created == true) {
      if (mounted) showAdminSnack(context, 'Đã tạo tài khoản.');
      await _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'admin_create_user',
        tooltip: 'Tạo tài khoản',
        backgroundColor: AppColors.flagRed,
        foregroundColor: Colors.white,
        onPressed: _createUser,
        icon: const Icon(Icons.person_add_alt),
        label: const Text('Tạo tài khoản'),
      ),
      body: Column(children: [
        _toolbar(),
        Expanded(child: RefreshIndicator(onRefresh: _load, child: _body())),
      ]),
    );
  }

  Widget _toolbar() => Container(
        color: Colors.white,
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
        child: Column(children: [
          TextField(
            controller: _search,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              isDense: true,
              prefixIcon: const Icon(Icons.search, size: 20),
              hintText: 'Tìm tên đăng nhập, email, họ tên',
              border:
                  OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
            ),
          ),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(children: [
              for (final e in _filters.entries) ...[
                ChoiceChip(
                  label: Text(e.value, style: const TextStyle(fontSize: 12.5)),
                  selected: _filter == e.key,
                  onSelected: (_) => setState(() => _filter = e.key),
                ),
                const SizedBox(width: 6),
              ],
            ]),
          ),
        ]),
      );

  Widget _body() {
    if (_loading && _users == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return AdminErrorView(message: _error!, onRetry: _load);
    }
    final users = _visible;
    if (users.isEmpty) {
      return ListView(children: const [
        SizedBox(height: 80),
        Center(child: Text('Không có tài khoản nào khớp.')),
      ]);
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 90),
      itemCount: users.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, i) => _userCard(users[i]),
    );
  }

  Widget _userCard(Map<String, dynamic> user) {
    final username = user['username']?.toString() ?? '';
    final fullName = user['full_name']?.toString() ?? '';
    final email = user['email']?.toString() ?? '';
    final role = user['role']?.toString() ?? 'user';
    final active = user['is_active'] != false;
    final isSelf = user['id'].toString() == sessionStore.user?.id;
    final records = (user['record_count'] as num?)?.toInt() ?? 0;
    final display = fullName.isNotEmpty ? fullName : username;

    return Material(
      color: Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.card),
        side: const BorderSide(color: AppColors.lineSoft),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => _openDetail(user),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(children: [
            CircleAvatar(
              radius: 19,
              backgroundColor:
                  active ? AppColors.navySoft : AppColors.inactive,
              child: Text(
                  display.isEmpty ? '?' : display.substring(0, 1).toUpperCase(),
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('$display${isSelf ? ' (bạn)' : ''}',
                      style: const TextStyle(
                          fontSize: 14.5, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text('@$username · $email',
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 12, color: AppColors.muted)),
                  const SizedBox(height: 6),
                  Wrap(spacing: 6, runSpacing: 4, children: [
                    StatusPill(roleLabel(role),
                        role == 'admin' ? AppColors.cobalt : AppColors.inkSoft),
                    if (!active) const StatusPill('KHÓA', AppColors.flagRed),
                    if (active && _tempLocked(user))
                      const StatusPill('KHÓA TẠM', AppColors.warn),
                    StatusPill('$records hồ sơ', AppColors.muted),
                  ]),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: AppColors.hint),
          ]),
        ),
      ),
    );
  }
}

/// Hộp thoại admin tạo tài khoản mới (cùng quy tắc với đăng ký).
class _CreateUserDialog extends StatefulWidget {
  final AuthApiClient auth;

  const _CreateUserDialog({required this.auth});

  @override
  State<_CreateUserDialog> createState() => _CreateUserDialogState();
}

class _CreateUserDialogState extends State<_CreateUserDialog> {
  final _username = TextEditingController();
  final _fullName = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  String _role = 'user';
  bool _saving = false;
  Map<String, String> _err = const {};
  String? _apiError;

  @override
  void dispose() {
    _username.dispose();
    _fullName.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final e = <String, String>{};
    if (!Validators.username(_username.text)) {
      e['username'] = 'Tên đăng nhập 3–32 ký tự (chữ/số/_), bắt đầu bằng chữ';
    }
    if (!Validators.email(_email.text)) e['email'] = 'Email không hợp lệ';
    if (!Validators.strongPassword(_password.text)) {
      e['password'] = 'Mật khẩu tối thiểu 8 ký tự, có chữ và số';
    }
    setState(() {
      _err = e;
      _apiError = null;
    });
    if (e.isNotEmpty) return;

    setState(() => _saving = true);
    try {
      await widget.auth.createUser(
        username: _username.text.trim(),
        email: _email.text.trim(),
        password: _password.text,
        fullName: _fullName.text.trim(),
        role: _role,
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (err) {
      if (mounted) setState(() => _apiError = adminErrorMessage(err));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _field(String label, TextEditingController c, String key,
          {bool obscure = false, TextInputType? keyboard}) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: TextField(
          controller: c,
          obscureText: obscure,
          keyboardType: keyboard,
          decoration: InputDecoration(
            isDense: true,
            labelText: label,
            errorText: _err[key],
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Tạo tài khoản'),
      content: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          _field('Tên đăng nhập', _username, 'username'),
          _field('Họ và tên (tuỳ chọn)', _fullName, 'fullName'),
          _field('Email', _email, 'email', keyboard: TextInputType.emailAddress),
          _field('Mật khẩu', _password, 'password', obscure: true),
          DropdownButtonFormField<String>(
            initialValue: _role,
            decoration: InputDecoration(
              isDense: true,
              labelText: 'Vai trò',
              border:
                  OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
            ),
            items: const [
              DropdownMenuItem(value: 'user', child: Text('Người dùng')),
              DropdownMenuItem(value: 'admin', child: Text('Quản trị viên')),
            ],
            onChanged: (v) => setState(() => _role = v ?? 'user'),
          ),
          if (_apiError != null) ...[
            const SizedBox(height: 10),
            Text(_apiError!,
                style: const TextStyle(color: AppColors.flagRed, fontSize: 12.5)),
          ],
        ]),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(false),
          child: const Text('Huỷ'),
        ),
        ElevatedButton(
          onPressed: _saving ? null : _submit,
          child: _saving
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('Tạo'),
        ),
      ],
    );
  }
}
