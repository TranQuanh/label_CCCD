import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/api/auth_api_client.dart';
import 'admin_common.dart';

/// Tab Hồ sơ (admin): QUẢN LÝ hồ sơ của mọi người dùng.
///
/// Admin KHÔNG được xem thông tin người dùng: danh sách chỉ có mã hồ sơ, biểu
/// mẫu, tên đăng nhập người tạo, thời gian và trạng thái. Không mở được chi
/// tiết, không có họ tên / số CCCD / trường bổ sung (server cũng không trả).
///
/// Admin làm được: ẩn / hiện từng hồ sơ, lọc (trạng thái, biểu mẫu, khoảng
/// ngày), tìm theo mã hồ sơ / tên đăng nhập, tải thêm.
/// [userId] (tuỳ chọn): chỉ hồ sơ của một tài khoản (mở từ chi tiết người dùng).
class RecordsAdminTab extends StatefulWidget {
  final String? userId;

  const RecordsAdminTab({super.key, this.userId});

  @override
  State<RecordsAdminTab> createState() => _RecordsAdminTabState();
}

class _RecordsAdminTabState extends State<RecordsAdminTab> {
  static const _pageSize = 30;
  static const _statusLabels = {
    'all': 'Tất cả',
    'visible': 'Đang hiện',
    'hidden': 'Đã ẩn',
    'form_hidden': 'Biểu mẫu ẩn',
  };

  final AuthApiClient _auth = AuthApiClient();
  final TextEditingController _search = TextEditingController();

  final List<Map<String, dynamic>> _records = [];
  int _total = 0;
  String? _error;
  bool _loading = true;
  bool _loadingMore = false;

  String _status = 'all';
  String? _formId;
  DateTimeRange? _range;
  List<Map<String, dynamic>> _forms = const [];

  /// Id các hồ sơ đang gửi yêu cầu ẩn/hiện (khoá công tắc, tránh bấm 2 lần).
  final Set<String> _busy = {};

  @override
  void initState() {
    super.initState();
    _loadForms();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _auth.dispose();
    super.dispose();
  }

  Future<void> _loadForms() async {
    try {
      final forms = await _auth.listAllForms();
      if (mounted) setState(() => _forms = forms);
    } catch (_) {
      // Không có danh sách biểu mẫu thì chỉ mất bộ lọc theo biểu mẫu.
    }
  }

  Future<AdminPage> _fetch(int offset) => _auth.listAllRecords(
        userId: widget.userId,
        formId: _formId,
        status: _status,
        query: _search.text,
        startDate: _range == null ? null : apiDate(_range!.start),
        endDate: _range == null ? null : apiDate(_range!.end),
        limit: _pageSize,
        offset: offset,
      );

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await _fetch(0);
      if (!mounted) return;
      setState(() {
        _records
          ..clear()
          ..addAll(page.items);
        _total = page.total;
      });
    } catch (e) {
      if (mounted) setState(() => _error = adminErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore) return;
    setState(() => _loadingMore = true);
    try {
      final page = await _fetch(_records.length);
      if (!mounted) return;
      setState(() {
        _records.addAll(page.items);
        _total = page.total;
      });
    } catch (e) {
      if (mounted) showAdminSnack(context, adminErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  Future<void> _pickRange() async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 5),
      lastDate: DateTime(now.year, now.month, now.day),
      initialDateRange: _range,
      helpText: 'Chọn khoảng ngày tạo hồ sơ',
    );
    if (picked == null) return;
    setState(() => _range = picked);
    await _load();
  }

  Future<void> _toggleHidden(Map<String, dynamic> record, bool hidden) async {
    final id = record['id'].toString();
    final code = record['code']?.toString() ?? '';
    setState(() => _busy.add(id));
    try {
      final updated = await _auth.setRecordHidden(id, hidden);
      if (!mounted) return;
      setState(() {
        final i = _records.indexWhere((r) => r['id'].toString() == id);
        if (i >= 0) _records[i] = {..._records[i], ...updated};
      });
      showAdminSnack(
          context,
          hidden
              ? 'Đã ẩn hồ sơ $code với người dùng.'
              : 'Đã hiện lại hồ sơ $code cho người dùng.');
    } catch (e) {
      if (mounted) showAdminSnack(context, adminErrorMessage(e));
    } finally {
      if (mounted) setState(() => _busy.remove(id));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _toolbar(),
        Expanded(
          child: RefreshIndicator(onRefresh: _load, child: _body()),
        ),
      ],
    );
  }

  Widget _toolbar() {
    final hasDate = _range != null;
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _search,
            textInputAction: TextInputAction.search,
            onChanged: (_) => setState(() {}), // cập nhật nút xoá
            onSubmitted: (_) => _load(),
            decoration: InputDecoration(
              isDense: true,
              prefixIcon: const Icon(Icons.search, size: 20),
              suffixIcon: _search.text.isEmpty
                  ? null
                  : IconButton(
                      tooltip: 'Xoá tìm kiếm',
                      icon: const Icon(Icons.close, size: 18),
                      onPressed: () {
                        _search.clear();
                        _load();
                      },
                    ),
              hintText: 'Tìm mã hồ sơ hoặc tên đăng nhập',
              border:
                  OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
            ),
          ),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(children: [
              for (final e in _statusLabels.entries) ...[
                ChoiceChip(
                  label: Text(e.value, style: const TextStyle(fontSize: 12.5)),
                  selected: _status == e.key,
                  onSelected: (_) {
                    setState(() => _status = e.key);
                    _load();
                  },
                ),
                const SizedBox(width: 6),
              ],
            ]),
          ),
          const SizedBox(height: 6),
          Row(children: [
            Expanded(
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String?>(
                  isExpanded: true,
                  value: _formId,
                  hint: const Text('Mọi biểu mẫu',
                      style: TextStyle(fontSize: 13)),
                  items: [
                    const DropdownMenuItem<String?>(
                        value: null,
                        child: Text('Mọi biểu mẫu',
                            style: TextStyle(fontSize: 13))),
                    for (final f in _forms)
                      DropdownMenuItem<String?>(
                        value: f['slug']?.toString(),
                        child: Text(
                            '${f['name']}${f['is_active'] == true ? '' : ' (đã ẩn)'}',
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 13)),
                      ),
                  ],
                  onChanged: (v) {
                    setState(() => _formId = v);
                    _load();
                  },
                ),
              ),
            ),
            const SizedBox(width: 8),
            TextButton.icon(
              onPressed: _pickRange,
              icon: const Icon(Icons.date_range, size: 18),
              label: Text(
                  hasDate
                      ? '${displayDate(_range!.start)} – ${displayDate(_range!.end)}'
                      : 'Khoảng ngày',
                  style: const TextStyle(fontSize: 12.5)),
            ),
            if (hasDate)
              IconButton(
                tooltip: 'Bỏ lọc ngày',
                icon: const Icon(Icons.close, size: 18),
                onPressed: () {
                  setState(() => _range = null);
                  _load();
                },
              ),
          ]),
        ],
      ),
    );
  }

  Widget _body() {
    if (_loading && _records.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return AdminErrorView(message: _error!, onRetry: _load);
    }
    if (_records.isEmpty) {
      // ListView để vẫn kéo xuống làm mới được khi danh sách trống.
      return ListView(children: const [
        SizedBox(height: 80),
        Center(child: Text('Không có hồ sơ nào khớp bộ lọc.')),
      ]);
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 0),
      itemCount: _records.length + 1,
      itemBuilder: (context, i) {
        if (i == _records.length) {
          return LoadMoreFooter(
            shown: _records.length,
            total: _total,
            loading: _loadingMore,
            onLoadMore: _loadMore,
          );
        }
        return Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: _recordCard(_records[i]),
        );
      },
    );
  }

  Widget _recordCard(Map<String, dynamic> r) {
    final id = r['id'].toString();
    final hidden = r['is_hidden'] == true;
    final formActive = r['form_active'] != false;
    final busy = _busy.contains(id);
    // Hồ sơ hiện với chủ khi CẢ hồ sơ lẫn biểu mẫu đang hiện.
    final visibleToOwner = !hidden && formActive;

    return Opacity(
      opacity: visibleToOwner ? 1 : .6,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppRadius.card),
          border: Border.all(
              color: visibleToOwner
                  ? AppColors.lineSoft
                  : const Color(0xFFF3C6C3)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(spacing: 6, runSpacing: 4, children: [
                    Text(r['code']?.toString() ?? '',
                        style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w800,
                            fontFamily: 'monospace',
                            color: AppColors.navy)),
                    if (hidden) const StatusPill('ĐÃ ẨN', AppColors.flagRed),
                    if (!formActive)
                      const StatusPill('BIỂU MẪU ẨN', AppColors.warn),
                    if (r['is_edited'] == true)
                      const StatusPill('ĐÃ SỬA', AppColors.cobalt),
                  ]),
                  const SizedBox(height: 5),
                  Text(r['form_name']?.toString() ?? '—',
                      style: const TextStyle(
                          fontSize: 13.5,
                          fontWeight: FontWeight.w700,
                          color: AppColors.ink)),
                  const SizedBox(height: 3),
                  Text(
                      'Người tạo: @${r['owner_username'] ?? 'không rõ'} · '
                      '${formatDateTime(r['created_at'])}',
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
                  : Semantics(
                      label: hidden ? 'Hiện hồ sơ' : 'Ẩn hồ sơ',
                      child: Switch(
                        value: !hidden,
                        onChanged: (show) => _toggleHidden(r, !show),
                      ),
                    ),
              Text(hidden ? 'Đang ẩn' : 'Đang hiện',
                  style:
                      const TextStyle(fontSize: 11, color: AppColors.muted)),
            ]),
          ],
        ),
      ),
    );
  }
}
