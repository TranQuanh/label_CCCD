import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/api/api_exception.dart';
import '../../data/api/auth_api_client.dart';

/// Tab nhật ký kiểm toán (admin): xem các sự kiện quan trọng từ `/api/v1/audit-logs`.
class AuditLogsAdminTab extends StatefulWidget {
  const AuditLogsAdminTab({super.key});

  @override
  State<AuditLogsAdminTab> createState() => _AuditLogsAdminTabState();
}

class _AuditLogsAdminTabState extends State<AuditLogsAdminTab> {
  final AuthApiClient _auth = AuthApiClient();
  List<Map<String, dynamic>>? _logs;
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
      final logs = await _auth.listAuditLogs(limit: 100);
      if (mounted) setState(() => _logs = logs);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.userMessage);
    } catch (_) {
      if (mounted) setState(() => _error = 'Không kết nối được máy chủ.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
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
    final logs = _logs ?? [];
    if (logs.isEmpty) {
      return const Center(child: Text('Chưa có nhật ký.'));
    }
    return ListView.separated(
      padding: const EdgeInsets.all(14),
      itemCount: logs.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, i) => _logCard(logs[i]),
    );
  }

  Widget _logCard(Map<String, dynamic> log) {
    final action = log['action']?.toString() ?? '';
    final username = log['username']?.toString() ?? '';
    final email = log['email']?.toString() ?? '';
    final created = log['created_at']?.toString() ?? '';
    final meta = log['metadata'] is Map ? log['metadata'] as Map : null;

    final isAuth = action.startsWith('auth.');
    final icon = isAuth ? Icons.login : Icons.admin_panel_settings_outlined;
    final color = isAuth ? AppColors.cobalt : const Color(0xFFB08900);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.lineSoft),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(
            radius: 16,
            backgroundColor: color.withValues(alpha: .12),
            child: Icon(icon, size: 18, color: color),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Expanded(
                    child: Text(action,
                        style: const TextStyle(
                            fontSize: 13, fontWeight: FontWeight.w800)),
                  ),
                  Text(_formatTime(created),
                      style: const TextStyle(
                          fontSize: 11, color: AppColors.hint)),
                ]),
                const SizedBox(height: 3),
                Text(
                    username.isNotEmpty
                        ? '$username${email.isNotEmpty ? ' ($email)' : ''}'
                        : email.isEmpty
                            ? '(hệ thống)'
                            : email,
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.muted)),
                if (meta != null && meta.isNotEmpty) ...[
                  const SizedBox(height: 5),
                  Text(meta.toString(),
                      style: const TextStyle(
                          fontSize: 11.5, color: AppColors.inkSoft)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _formatTime(String iso) {
    final t = DateTime.tryParse(iso);
    if (t == null) return iso;
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(t.day)}/${two(t.month)}/${t.year} '
        '${two(t.hour)}:${two(t.minute)}';
  }
}