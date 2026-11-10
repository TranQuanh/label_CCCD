import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/api/auth_api_client.dart';
import 'admin_common.dart';

/// Tab Nhật ký (admin): xem hoạt động trong hệ thống.
///
/// - Hành động hiển thị bằng câu tiếng Việt + icon + màu (đỏ = bảo mật / lỗi).
/// - Nhóm theo ngày (Hôm nay, Hôm qua, ...).
/// - Lọc: nhóm hành động, chỉ sự kiện bảo mật, khoảng ngày.
/// - Bấm một dòng → chi tiết: người thực hiện, đối tượng (tên đăng nhập / mã
///   hồ sơ / tên biểu mẫu), IP, thiết bị, thông tin thêm.
/// - Tải thêm (phân trang).
/// Nhật ký không chứa nội dung CCCD của người dùng.
///
/// [userId] (tuỳ chọn): chỉ nhật ký do một tài khoản thực hiện.
class AuditLogsAdminTab extends StatefulWidget {
  final String? userId;

  const AuditLogsAdminTab({super.key, this.userId});

  @override
  State<AuditLogsAdminTab> createState() => _AuditLogsAdminTabState();
}

class _AuditLogsAdminTabState extends State<AuditLogsAdminTab> {
  static const _pageSize = 50;
  static const _groups = {
    null: 'Tất cả',
    'auth': 'Đăng nhập',
    'user': 'Tài khoản',
    'record': 'Hồ sơ',
    'profile': 'Profile',
    'form': 'Biểu mẫu',
  };

  final AuthApiClient _auth = AuthApiClient();
  final List<Map<String, dynamic>> _logs = [];
  int _total = 0;
  String? _error;
  bool _loading = true;
  bool _loadingMore = false;

  String? _group;
  bool _securityOnly = false;
  DateTimeRange? _range;

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

  Future<AdminPage> _fetch(int offset) => _auth.listAuditLogs(
        userId: widget.userId,
        actionGroup: _group,
        securityOnly: _securityOnly,
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
        _logs
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
      final page = await _fetch(_logs.length);
      if (!mounted) return;
      setState(() {
        _logs.addAll(page.items);
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
      helpText: 'Chọn khoảng ngày',
    );
    if (picked == null) return;
    setState(() => _range = picked);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _toolbar(),
        Expanded(child: RefreshIndicator(onRefresh: _load, child: _body())),
      ],
    );
  }

  Widget _toolbar() {
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(children: [
              for (final e in _groups.entries) ...[
                ChoiceChip(
                  label: Text(e.value, style: const TextStyle(fontSize: 12.5)),
                  selected: _group == e.key,
                  onSelected: (_) {
                    setState(() => _group = e.key);
                    _load();
                  },
                ),
                const SizedBox(width: 6),
              ],
            ]),
          ),
          Row(children: [
            FilterChip(
              avatar: const Icon(Icons.shield_outlined, size: 16),
              label: const Text('Chỉ sự kiện bảo mật',
                  style: TextStyle(fontSize: 12.5)),
              selected: _securityOnly,
              onSelected: (v) {
                setState(() => _securityOnly = v);
                _load();
              },
            ),
            const Spacer(),
            TextButton.icon(
              onPressed: _pickRange,
              icon: const Icon(Icons.date_range, size: 18),
              label: Text(
                  _range == null
                      ? 'Khoảng ngày'
                      : '${displayDate(_range!.start)} – ${displayDate(_range!.end)}',
                  style: const TextStyle(fontSize: 12.5)),
            ),
            if (_range != null)
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
    if (_loading && _logs.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return AdminErrorView(message: _error!, onRetry: _load);
    }
    if (_logs.isEmpty) {
      return ListView(children: const [
        SizedBox(height: 80),
        Center(child: Text('Không có nhật ký nào khớp bộ lọc.')),
      ]);
    }

    // Chèn tiêu đề ngày trước dòng đầu tiên của mỗi ngày.
    final items = <Widget>[];
    String? lastDay;
    for (final log in _logs) {
      final t = parseServerTime(log['created_at']);
      final day = t == null ? '—' : dayHeader(t);
      if (day != lastDay) {
        items.add(Padding(
          padding: const EdgeInsets.fromLTRB(2, 10, 2, 6),
          child: Text(day,
              style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w800,
                  color: AppColors.inkSoft)),
        ));
        lastDay = day;
      }
      items.add(Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: _logCard(log),
      ));
    }
    items.add(LoadMoreFooter(
      shown: _logs.length,
      total: _total,
      loading: _loadingMore,
      onLoadMore: _loadMore,
    ));
    return ListView(
      padding: const EdgeInsets.fromLTRB(14, 4, 14, 0),
      children: items,
    );
  }

  /// Câu tóm tắt đối tượng bị tác động (không dùng UUID).
  static String? _targetText(Map<String, dynamic> log) {
    final label = log['target_label']?.toString();
    if (label == null || label.isEmpty) return null;
    switch (log['target_type']) {
      case 'user':
        return 'Tài khoản @$label';
      case 'record':
        return 'Hồ sơ $label';
      case 'form':
        return 'Biểu mẫu "$label"';
      default:
        return label;
    }
  }

  static String _actor(Map<String, dynamic> log) {
    final username = log['username']?.toString() ?? '';
    if (username.isNotEmpty) return '@$username';
    final meta = log['metadata'];
    if (meta is Map && meta['identifier'] != null) {
      return 'Khách (${meta['identifier']})';
    }
    return '(hệ thống)';
  }

  Widget _logCard(Map<String, dynamic> log) {
    final info = actionInfo(log['action']?.toString() ?? '');
    final target = _targetText(log);

    return Material(
      color: Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.card),
        side: BorderSide(
            color: info.security
                ? info.color.withValues(alpha: .35)
                : AppColors.lineSoft),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => _showDetail(log),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: info.color.withValues(alpha: .12),
                child: Icon(info.icon, size: 18, color: info.color),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Expanded(
                        child: Text(info.label,
                            style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w800,
                                color: info.security ? info.color : AppColors.ink)),
                      ),
                      Text(formatTime(log['created_at']),
                          style: const TextStyle(
                              fontSize: 11, color: AppColors.hint)),
                    ]),
                    const SizedBox(height: 3),
                    Text(target == null ? _actor(log) : '${_actor(log)} → $target',
                        style: const TextStyle(
                            fontSize: 12, color: AppColors.muted)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, size: 18, color: AppColors.hint),
            ],
          ),
        ),
      ),
    );
  }

  void _showDetail(Map<String, dynamic> log) {
    final info = actionInfo(log['action']?.toString() ?? '');
    final rows = <MapEntry<String, String>>[
      MapEntry('Thời gian', formatDateTime(log['created_at'])),
      MapEntry('Người thực hiện', _actor(log)),
      if ((log['email']?.toString() ?? '').isNotEmpty)
        MapEntry('Email', log['email'].toString()),
      if (_targetText(log) != null) MapEntry('Đối tượng', _targetText(log)!),
      ...describeMetadata(log['action']?.toString() ?? '', log['metadata']),
      if ((log['ip_address']?.toString() ?? '').isNotEmpty)
        MapEntry('Địa chỉ IP', log['ip_address'].toString()),
      if ((log['device_info']?.toString() ?? '').isNotEmpty)
        MapEntry('Thiết bị', log['device_info'].toString()),
      MapEntry('Mã hành động', log['action']?.toString() ?? ''),
    ];

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (sheetContext) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(
              maxHeight: MediaQuery.of(sheetContext).size.height * .75),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
            children: [
              Row(children: [
                CircleAvatar(
                  radius: 18,
                  backgroundColor: info.color.withValues(alpha: .12),
                  child: Icon(info.icon, size: 20, color: info.color),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(info.label,
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w800)),
                ),
                if (info.security)
                  const StatusPill('BẢO MẬT', AppColors.flagRed),
              ]),
              const SizedBox(height: 14),
              for (final r in rows)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 130,
                        child: Text(r.key,
                            style: const TextStyle(
                                fontSize: 12.5, color: AppColors.muted)),
                      ),
                      Expanded(
                        child: SelectableText(r.value,
                            style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: AppColors.ink)),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
