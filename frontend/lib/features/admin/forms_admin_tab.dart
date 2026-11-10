import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/api/auth_api_client.dart';
import 'admin_common.dart';

/// Tab Biểu mẫu (admin): xem mọi biểu mẫu và ẨN / HIỆN từng biểu mẫu.
///
/// Admin KHÔNG được tạo hay sửa nội dung biểu mẫu (nội dung định nghĩa trong
/// `backend/schema.sql`). Ẩn một biểu mẫu:
///   - người dùng không thấy biểu mẫu trong danh mục, không tạo hồ sơ mới;
///   - hồ sơ cũ của biểu mẫu đó bị ẩn khỏi lịch sử của chủ hồ sơ.
/// Dữ liệu không bị xoá — hiện lại biểu mẫu thì hồ sơ hiện lại.
class FormsAdminTab extends StatefulWidget {
  const FormsAdminTab({super.key});

  @override
  State<FormsAdminTab> createState() => _FormsAdminTabState();
}

class _FormsAdminTabState extends State<FormsAdminTab> {
  final AuthApiClient _auth = AuthApiClient();
  List<Map<String, dynamic>>? _forms;
  String? _error;
  bool _loading = true;
  final Set<String> _busy = {};

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
      final forms = await _auth.listAllForms();
      if (mounted) setState(() => _forms = forms);
    } catch (e) {
      if (mounted) setState(() => _error = adminErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggle(Map<String, dynamic> form, bool active) async {
    final slug = form['slug']?.toString() ?? '';
    final name = form['name']?.toString() ?? slug;
    final count = (form['record_count'] as num?)?.toInt() ?? 0;
    if (!active) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Ẩn biểu mẫu?'),
          content: Text(
              'Biểu mẫu "$name" sẽ không còn hiện với người dùng và không tạo '
              'được hồ sơ mới.\n\n$count hồ sơ đã tạo từ biểu mẫu này cũng bị '
              'ẩn khỏi lịch sử của chủ hồ sơ (dữ liệu không bị xoá, hiện lại '
              'biểu mẫu thì hồ sơ hiện lại).'),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Huỷ')),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('Ẩn biểu mẫu',
                  style: TextStyle(color: AppColors.flagRed)),
            ),
          ],
        ),
      );
      if (ok != true) return;
    }

    setState(() => _busy.add(slug));
    try {
      final updated = await _auth.setFormActive(slug, active);
      if (!mounted) return;
      setState(() {
        final list = _forms ?? [];
        final i = list.indexWhere((f) => f['slug'] == slug);
        if (i >= 0) {
          // Server trả biểu mẫu không kèm record_count → giữ số cũ.
          list[i] = {...list[i], ...updated};
        }
      });
      showAdminSnack(context,
          active ? 'Đã hiện lại biểu mẫu "$name".' : 'Đã ẩn biểu mẫu "$name".');
    } catch (e) {
      if (mounted) showAdminSnack(context, adminErrorMessage(e));
    } finally {
      if (mounted) setState(() => _busy.remove(slug));
    }
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(onRefresh: _load, child: _body());
  }

  Widget _body() {
    if (_loading && _forms == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return AdminErrorView(message: _error!, onRetry: _load);
    }
    final forms = _forms ?? [];
    if (forms.isEmpty) {
      return ListView(children: const [
        SizedBox(height: 80),
        Center(child: Text('Chưa có biểu mẫu nào.')),
      ]);
    }
    final hidden = forms.where((f) => f['is_active'] != true).length;
    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: AppColors.tint,
            borderRadius: BorderRadius.circular(AppRadius.card),
          ),
          child: Text(
              '${forms.length} biểu mẫu · ${forms.length - hidden} đang hiện · '
              '$hidden đang ẩn\nNội dung biểu mẫu không sửa được trên app — '
              'chỉ ẩn / hiện.',
              style: const TextStyle(
                  fontSize: 12.5, color: AppColors.inkSoft, height: 1.4)),
        ),
        const SizedBox(height: 12),
        for (final f in forms) ...[
          _formCard(f),
          const SizedBox(height: 10),
        ],
      ],
    );
  }

  Widget _formCard(Map<String, dynamic> f) {
    final slug = f['slug']?.toString() ?? '';
    final active = f['is_active'] == true;
    final busy = _busy.contains(slug);
    final count = (f['record_count'] as num?)?.toInt() ?? 0;
    final fields = f['required_fields'] is List
        ? (f['required_fields'] as List).whereType<Map>().toList()
        : const <Map>[];
    final sides = [
      if (f['requires_front'] == true) 'mặt trước',
      if (f['requires_back'] == true) 'mặt sau',
    ].join(' + ');

    return Opacity(
      opacity: active ? 1 : .65,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppRadius.card),
          border: Border.all(
              color: active ? AppColors.lineSoft : const Color(0xFFF3C6C3)),
        ),
        child: Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            tilePadding: const EdgeInsets.fromLTRB(14, 6, 8, 6),
            childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            title: Row(children: [
              Flexible(
                child: Text(f['name']?.toString() ?? slug,
                    style: const TextStyle(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w700,
                        color: AppColors.ink)),
              ),
              const SizedBox(width: 8),
              StatusPill(active ? 'ĐANG HIỆN' : 'ĐÃ ẨN',
                  active ? AppColors.valid : AppColors.flagRed),
            ]),
            subtitle: Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text('$count hồ sơ đã tạo · mã: $slug',
                  style:
                      const TextStyle(fontSize: 12, color: AppColors.muted)),
            ),
            trailing: busy
                ? const Padding(
                    padding: EdgeInsets.all(12),
                    child: SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2.5)),
                  )
                : Semantics(
                    label: active ? 'Ẩn biểu mẫu' : 'Hiện biểu mẫu',
                    child: Switch(
                      value: active,
                      onChanged: (v) => _toggle(f, v),
                    ),
                  ),
            children: [
              if ((f['description']?.toString() ?? '').isNotEmpty) ...[
                Text(f['description'].toString(),
                    style: const TextStyle(
                        fontSize: 12.5, color: AppColors.inkSoft)),
                const SizedBox(height: 8),
              ],
              if (sides.isNotEmpty)
                Text('Cần chụp: $sides',
                    style: const TextStyle(
                        fontSize: 12.5, color: AppColors.inkSoft)),
              const SizedBox(height: 8),
              Text('Trường bổ sung (${fields.length})',
                  style: const TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      color: AppColors.ink)),
              const SizedBox(height: 4),
              if (fields.isEmpty)
                const Text('Không có',
                    style: TextStyle(fontSize: 12, color: AppColors.muted))
              else
                for (final field in fields)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                        '• ${field['label'] ?? field['key']}'
                        '${(field['hint']?.toString() ?? '').isNotEmpty ? ' — ${field['hint']}' : ''}',
                        style: const TextStyle(
                            fontSize: 12, color: AppColors.inkSoft)),
                  ),
            ],
          ),
        ),
      ),
    );
  }
}
