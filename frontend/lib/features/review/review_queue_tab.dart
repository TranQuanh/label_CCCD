import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/form_type.dart';
import '../../data/models/submitted_record.dart';
import '../../data/session/session_store.dart';
import '../output/preview_screen.dart';

/// Tab — Hàng đợi duyệt (chỉ operator/admin).
///
/// P2: liệt kê hồ sơ `pending` từ `GET /scan-records/review-queue`; bấm để xem
/// nội dung (read-only) rồi Duyệt / Bỏ qua. Sau khi duyệt, hồ sơ xuất hiện
/// trong lịch sử người dùng và (với viewer) qua bản che số CCCD.
class ReviewQueueTab extends StatefulWidget {
  const ReviewQueueTab({super.key});

  @override
  State<ReviewQueueTab> createState() => _ReviewQueueTabState();
}

class _ReviewQueueTabState extends State<ReviewQueueTab> {
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    unawaited(sessionStore.loadReviewQueue());
  }

  Future<void> _refresh() async {
    setState(() => _busy = true);
    await sessionStore.loadReviewQueue();
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _open(SubmittedRecord record) async {
    final form = sessionStore.formById(record.formId) ??
        formTypeById(record.formId);
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => PreviewScreen(
        formType: form,
        card: record.card,
        supp: record.supp,
        code: record.code,
        readOnly: true,
      ),
    ));
    if (mounted) await _refresh();
  }

  Future<void> _approve(SubmittedRecord record) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Duyệt hồ sơ?'),
        content: Text(
            '${record.code} — ${record.name}.\nSau khi duyệt, hồ sơ sẽ hiển thị '
            'trong lịch sử người dùng (kể cả bản che cho người xem).'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Huỷ')),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Duyệt', style: TextStyle(color: AppColors.valid)),
          ),
        ],
      ),
    );
    if (confirm != true) return;
    final id = record.id;
    if (id == null) return;
    setState(() => _busy = true);
    try {
      await sessionStore.reviewRecord(id, approve: true);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Không duyệt được: $e')));
      }
    }
    if (mounted) {
      setState(() => _busy = false);
      await _refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionStore,
      builder: (context, _) {
        final queue = sessionStore.reviewQueue;
        return Column(
          children: [
            Container(
              width: double.infinity,
              color: AppColors.navy,
              padding: EdgeInsets.fromLTRB(
                  24, MediaQuery.of(context).padding.top + 16, 24, 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Chờ duyệt',
                      style: TextStyle(
                          fontSize: 19,
                          fontWeight: FontWeight.w800,
                          color: Colors.white)),
                  const SizedBox(height: 3),
                  const Text('Duyệt hồ sơ trích xuất trước khi hiển thị',
                      style:
                          TextStyle(fontSize: 12.5, color: AppColors.onNavy)),
                  const SizedBox(height: 14),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 9),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: .08),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.white.withValues(alpha: .14)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(queue.length.toString(),
                            style: const TextStyle(
                                fontSize: 22,
                                fontWeight: FontWeight.w900,
                                color: Colors.white)),
                        const SizedBox(width: 8),
                        const Text('hồ sơ đang chờ',
                            style: TextStyle(
                                fontSize: 12, color: AppColors.onNavy)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: queue.isEmpty
                  ? RefreshIndicator(
                      onRefresh: _refresh,
                      child: ListView(
                        children: const [
                          SizedBox(height: 140),
                          Icon(Icons.task_alt, size: 56, color: AppColors.valid),
                          SizedBox(height: 12),
                          Center(
                            child: Text('Không còn hồ sơ chờ duyệt',
                                style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.w700,
                                    color: AppColors.inkSoft)),
                          ),
                        ],
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: _refresh,
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(20, 18, 20, 16),
                        children: [
                          if (_busy)
                            const Padding(
                              padding: EdgeInsets.only(bottom: 12),
                              child: LinearProgressIndicator(
                                  color: AppColors.cobalt),
                            ),
                          ...queue.map((r) => Padding(
                                padding: const EdgeInsets.only(bottom: 12),
                                child: _QueueCard(
                                  record: r,
                                  onTap: () => _open(r),
                                  onApprove: () => _approve(r),
                                ),
                              )),
                        ],
                      ),
                    ),
            ),
          ],
        );
      },
    );
  }
}

class _QueueCard extends StatelessWidget {
  final SubmittedRecord record;
  final VoidCallback onTap;
  final VoidCallback onApprove;

  const _QueueCard({
    required this.record,
    required this.onTap,
    required this.onApprove,
  });

  @override
  Widget build(BuildContext context) {
    final form = sessionStore.formById(record.formId) ??
        formTypeById(record.formId);
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.lineSoft),
        boxShadow: [
          BoxShadow(
              color: AppColors.navy.withValues(alpha: .05),
              blurRadius: 12,
              offset: const Offset(0, 5)),
        ],
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.card),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            children: [
              Row(children: [
                Container(
                  width: 42,
                  height: 42,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: form.tint,
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: Text(form.glyph,
                      style: TextStyle(
                          color: form.color,
                          fontSize: 15,
                          fontWeight: FontWeight.w900)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(form.title,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                              color: AppColors.ink)),
                      const SizedBox(height: 2),
                      Text(record.code,
                          style: const TextStyle(
                              fontSize: 11.5,
                              color: AppColors.muted,
                              fontFamily: 'monospace')),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: AppColors.warn.withValues(alpha: .12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Text('Chờ duyệt',
                      style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          color: AppColors.warn)),
                ),
              ]),
              const SizedBox(height: 11),
              const Divider(height: 1, color: Color(0xFFE7ECF5)),
              const SizedBox(height: 11),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text('Người khai: ${record.name}',
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 12, color: AppColors.inkSoft)),
                  ),
                  const SizedBox(width: 12),
                  SizedBox(
                    height: 34,
                    child: ElevatedButton.icon(
                      onPressed: onApprove,
                      icon: const Icon(Icons.check, size: 16),
                      label: const Text('Duyệt',
                          style: TextStyle(
                              fontSize: 13, fontWeight: FontWeight.w700)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.valid,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(horizontal: 14),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(9)),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}