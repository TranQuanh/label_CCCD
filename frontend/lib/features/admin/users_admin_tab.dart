import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/api/api_exception.dart';
import '../../data/api/auth_api_client.dart';
import '../../data/session/session_store.dart';

/// Tab quản lý người dùng (admin): danh sách, đổi vai trò, khóa/mở khóa.
class UsersAdminTab extends StatefulWidget {
  const UsersAdminTab({super.key});

  @override
  State<UsersAdminTab> createState() => _UsersAdminTabState();
}

class _UsersAdminTabState extends State<UsersAdminTab> {
  final AuthApiClient _auth = AuthApiClient();
  List<Map<String, dynamic>>? _users;
  String? _error;
  bool _loading = true;

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
      final users = await _auth.listUsers();
      if (mounted) setState(() => _users = users);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.userMessage);
    } catch (_) {
      if (mounted) setState(() => _error = 'Không kết nối được máy chủ.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _changeRole(Map<String, dynamic> user, String newRole) async {
    try {
      await _auth.updateUser(user['id'].toString(), {'role': newRole});
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(
              'Đã đổi vai trò của ${user['username']} sang $newRole — người dùng phải đăng nhập lại.')));
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.userMessage)));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Lỗi máy chủ.')));
      }
    }
  }

  Future<void> _toggleActive(Map<String, dynamic> user) async {
    final target = !(user['is_active'] as bool? ?? true);
    final label = target ? 'khóa' : 'mở khóa';
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('${target ? 'Khóa' : 'Mở khóa'} tài khoản?'),
        content: Text('Tài khoản "${user['username']}" sẽ bị ${target ? 'khóa' : 'mở'}.\n'
            'Phiên hiện tại của người dùng bị vô hiệu hóa.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Huỷ')),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(label,
                style: const TextStyle(color: AppColors.flagRed)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _auth.updateUser(user['id'].toString(), {'is_active': target});
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Đã $label tài khoản "${user['username']}".')));
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.userMessage)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: _load,
      child: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return ListView(
        children: [
          const SizedBox(height: 60),
          const Icon(Icons.cloud_off, size: 42, color: AppColors.muted),
          const SizedBox(height: 12),
          Center(
            child: Text(_error!,
                style: const TextStyle(color: AppColors.inkSoft)),
          ),
          const SizedBox(height: 16),
          Center(
            child: OutlinedButton(
                onPressed: _load, child: const Text('Thử lại')),
          ),
        ],
      );
    }
    final users = _users ?? [];
    if (users.isEmpty) {
      return const Center(child: Text('Chưa có tài khoản nào.'));
    }
    return ListView.separated(
      padding: const EdgeInsets.all(14),
      itemCount: users.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, i) => _userCard(users[i]),
    );
  }

  Widget _userCard(Map<String, dynamic> user) {
    final username = user['username']?.toString() ?? '';
    final fullName = user['full_name']?.toString() ?? '';
    final email = user['email']?.toString() ?? '';
    final role = user['role']?.toString() ?? 'operator';
    final active = user['is_active'] as bool? ?? true;
    final isSelf = user['id'].toString() == sessionStore.user?.id;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.lineSoft),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            CircleAvatar(
              radius: 18,
              backgroundColor: AppColors.navySoft,
              child: Text(
                  (fullName.isNotEmpty ? fullName : username)
                          .substring(0, 1)
                          .toUpperCase(),
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(fullName.isEmpty ? username : fullName,
                      style: const TextStyle(
                          fontSize: 14.5, fontWeight: FontWeight.w700)),
                  Text(email.isEmpty ? username : email,
                      style: const TextStyle(
                          fontSize: 12, color: AppColors.muted)),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
              decoration: BoxDecoration(
                color: role == 'admin'
                    ? const Color(0xFFEAF0FF)
                    : AppColors.tint,
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(role,
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: role == 'admin'
                          ? AppColors.cobalt
                          : AppColors.inkSoft)),
            ),
            const SizedBox(width: 8),
            if (!active)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFFFDECEA),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Text('KHÓA',
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        color: AppColors.flagRed)),
              ),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                initialValue: role,
                decoration: InputDecoration(
                  isDense: true,
                  labelText: 'Vai trò',
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
                items: const [
                  DropdownMenuItem(value: 'admin', child: Text('admin')),
                  DropdownMenuItem(value: 'operator', child: Text('operator')),
                  DropdownMenuItem(value: 'viewer', child: Text('viewer')),
                ],
                onChanged: isSelf
                    ? null
                    : (v) {
                        if (v != null && v != role) _changeRole(user, v);
                      },
              ),
            ),
            const SizedBox(width: 10),
            if (!isSelf)
              OutlinedButton(
                onPressed: () => _toggleActive(user),
                style: OutlinedButton.styleFrom(
                  foregroundColor:
                      active ? AppColors.flagRed : AppColors.cobalt,
                  side: BorderSide(
                      color: active
                          ? const Color(0xFFF3C6C3)
                          : AppColors.lineSoft),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
                child: Text(active ? 'Khóa' : 'Mở khóa',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
          ]),
        ],
      ),
    );
  }
}