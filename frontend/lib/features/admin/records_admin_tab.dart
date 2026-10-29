import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/api/api_exception.dart';
import '../../data/api/auth_api_client.dart';

/// Tab hồ sơ (admin): xem hồ sơ của MỌI người dùng và ẩn / hiện từng hồ sơ.
///
/// Hồ sơ bị ẩn không còn hiện trong tab "Hồ sơ" của chủ hồ sơ (backend lọc
/// `is_hidden`); dữ liệu vẫn giữ nguyên và admin hiện lại được bất cứ lúc nào.
class RecordsAdminTab extends StatefulWidget {
  const RecordsAdminTab({super.key});

  @override
  State<RecordsAdminTab> createState() => _RecordsAdminTabState();
}

/// Bộ lọc hiển thị danh sách.
enum _Filter { all, visible, hidden }

class _RecordsAdminTabState extends State<RecordsAdminTab> {
  final AuthApiClient _auth = AuthApiClient();
  List<Map<String, dynamic>>? _records;
  String? _error;
  bool _loading = true;
  _Filter _filter = _Filter.all;
  String _query = '';

  /// Id các hồ sơ đang gửi yêu cầu ẩn/hiện (khoá công tắc, tránh bấm 2 lần).
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
      final records = await _auth.listAllRecords();
      if (mounted) setState(() => _records = records);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.userMessage);
    } catch (_) {
      if (mounted) setState(() => _error = 'Không kết nối được máy chủ.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggleHidden(Map<String, dynamic> record, bool hidden) async {
    final id = record['id'].toString();
    final code = record['code']?.toString() ?? '';
    setState(() => _busy.add(id));
    try {
      final updated = await _auth.setRecordHidden(id, hidden);
      if (!mounted) return;
      setState(() {
        final list = _records ?? [];
        final i = list.indexWhere((r) => r['id'].toString() == id);
        if (i >= 0) list[i] = updated;
      });
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(hidden
              ? 'Đã ẩn hồ sơ $code với người dùng.'
              : 'Đã hiện lại hồ sơ $code cho người dùng.')));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.userMessage)));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Không kết nối được máy chủ.')));
      }
    } finally {
      if (mounted) setState(() => _busy.remove(id));
    }
  }

  /// Họ tên công dân trên thẻ (extracted_data là map snake_case).
  static String _citizenName(Map<String, dynamic> r) {
    final data = r['extracted_data'];
    if (data is Map) {
      final v = data['ho_va_ten']?.toString() ?? '';
      if (v.trim().isNotEmpty) return v.trim();
    }
    return 'Chưa có tên';
  }

  static String _date(Map<String, dynamic> r) {
    final raw = r['created_at']?.toString();
    final d = raw == null ? null : DateTime.tryParse(raw);
    if (d == null) return '';
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(d.day)}/${two(d.month)}/${d.year} ${two(d.hour)}:${two(d.minute)}';
  }

  List<Map<String, dynamic>> get _visibleList {
    final q = _query.trim().toLowerCase();
    return (_records ?? []).where((r) {
      final hidden = r['is_hidden'] == true;
      if (_filter == _Filter.visible && hidden) return false;
      if (_filter == _Filter.hidden && !hidden) return false;
      if (q.isEmpty) return true;
      final haystack = [
        r['code'],
        _citizenName(r),
        r['owner_username'],
        r['owner_name'],
        r['form_name'],
      ].map((e) => (e ?? '').toString().toLowerCase()).join(' ');
      return haystack.contains(q);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _toolbar(),
        Expanded(
          child: RefreshIndicator(onRefresh: _load, child: _buildBody()),
        ),
      ],
    );
  }

  Widget _toolbar() {
    final all = _records ?? [];
    final hiddenCount = all.where((r) => r['is_hidden'] == true).length;
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            onChanged: (v) => setState(() => _query = v),
            decoration: InputDecoration(
              isDense: true,
              prefixIcon: const Icon(Icons.search, size: 20),
              hintText: 'Tìm theo mã hồ sơ, họ tên, người tạo, biểu mẫu',
              border:
                  OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
            ),
          ),
          const SizedBox(height: 10),
          Wrap(spacing: 8, children: [
            _chip('Tất cả (${all.length})', _Filter.all),
            _chip('Đang hiện (${all.length - hiddenCount})', _Filter.visible),
            _chip('Đã ẩn ($hiddenCount)', _Filter.hidden),
          ]),
        ],
      ),
    );
  }

  Widget _chip(String label, _Filter value) => ChoiceChip(
        label: Text(label, style: const TextStyle(fontSize: 12.5)),
        selected: _filter == value,
        onSelected: (_) => setState(() => _filter = value),
      );

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
    final list = _visibleList;
    if (list.isEmpty) {
      // ListView để vẫn kéo xuống làm mới được khi danh sách trống.
      return ListView(children: const [
        SizedBox(height: 80),
        Center(child: Text('Không có hồ sơ nào.')),
      ]);
    }
    return ListView.separated(
      padding: const EdgeInsets.all(14),
      itemCount: list.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, i) => _recordCard(list[i]),
    );
  }

  Widget _recordCard(Map<String, dynamic> r) {
    final id = r['id'].toString();
    final hidden = r['is_hidden'] == true;
    final busy = _busy.contains(id);
    final owner = (r['owner_name']?.toString().trim().isNotEmpty ?? false)
        ? '${r['owner_name']} (@${r['owner_username'] ?? ''})'
        : '@${r['owner_username'] ?? 'không rõ'}';

    return Opacity(
      opacity: hidden ? .6 : 1,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppRadius.card),
          border: Border.all(
              color: hidden ? const Color(0xFFF3C6C3) : AppColors.lineSoft),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Flexible(
                      child: Text(r['code']?.toString() ?? '',
                          style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w800,
                              fontFamily: 'monospace',
                              color: AppColors.navy)),
                    ),
                    if (hidden) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFDECEA),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: const Text('ĐÃ ẨN',
                            style: TextStyle(
                                fontSize: 10.5,
                                fontWeight: FontWeight.w800,
                                color: AppColors.flagRed)),
                      ),
                    ],
                  ]),
                  const SizedBox(height: 4),
                  Text(_citizenName(r),
                      style: const TextStyle(
                          fontSize: 14.5,
                          fontWeight: FontWeight.w700,
                          color: AppColors.ink)),
                  const SizedBox(height: 2),
                  Text(r['form_name']?.toString() ?? '—',
                      style: const TextStyle(
                          fontSize: 12.5, color: AppColors.inkSoft)),
                  const SizedBox(height: 2),
                  Text('Người tạo: $owner · ${_date(r)}',
                      style: const TextStyle(
                          fontSize: 11.5, color: AppColors.muted)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Column(children: [
              busy
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2.5)),
                    )
                  : Switch(
                      value: !hidden,
                      onChanged: (show) => _toggleHidden(r, !show),
                    ),
              Text(hidden ? 'Đang ẩn' : 'Đang hiện',
                  style: const TextStyle(
                      fontSize: 11, color: AppColors.muted)),
            ]),
          ],
        ),
      ),
    );
  }
}
