import 'package:flutter/material.dart';
import '../../data/models/form_type.dart';
import '../../data/models/submitted_record.dart';
import '../../data/session/session_store.dart';
import '../../core/theme/app_theme.dart';
import '../output/preview_screen.dart';

/// Tab 2 — Hồ sơ người dùng đã tạo.
///
/// P2: ở chế độ thật, lịch sử tải từ server (`GET /scan-records`) khi mở tab.
/// Viewer thấy bản che số CCCD (banner "dữ liệu đã được che").
class RecordsTab extends StatefulWidget {
  final VoidCallback onCreateNew;
  const RecordsTab({super.key, required this.onCreateNew});

  @override
  State<RecordsTab> createState() => _RecordsTabState();
}

class _RecordsTabState extends State<RecordsTab> {
  @override
  void initState() {
    super.initState();
    sessionStore.loadRecords();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionStore,
      builder: (context, _) {
        final records = sessionStore.records;
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
                  const Text('Hồ sơ của tôi',
                      style: TextStyle(
                          fontSize: 19,
                          fontWeight: FontWeight.w800,
                          color: Colors.white)),
                  const SizedBox(height: 3),
                  const Text('Các biểu mẫu bạn đã kê khai & gửi',
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
                        Text(records.length.toString(),
                            style: const TextStyle(
                                fontSize: 22,
                                fontWeight: FontWeight.w900,
                                color: Colors.white)),
                        const SizedBox(width: 8),
                        const Text('hồ sơ đã tạo',
                            style: TextStyle(
                                fontSize: 12, color: AppColors.onNavy)),
                      ],
                    ),
                  ),
                  if (sessionStore.masked) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 9),
                      decoration: BoxDecoration(
                        color: AppColors.star.withValues(alpha: .16),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                            color: AppColors.star.withValues(alpha: .35)),
                      ),
                      child: const Row(children: [
                        Icon(Icons.visibility_off_outlined,
                            size: 15, color: AppColors.star),
                        SizedBox(width: 8),
                        Expanded(
                          child: Text(
                              'Bạn xem bản che: số CCCD đã ẩn một phần.',
                              style: TextStyle(
                                  fontSize: 11.5, color: AppColors.star)),
                        ),
                      ]),
                    ),
                  ],
                ],
              ),
            ),
            Expanded(
              child: records.isEmpty
                  ? (sessionStore.loadingRecords
                      ? const Center(
                          child: CircularProgressIndicator(color: AppColors.navy))
                      : _empty())
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(20, 18, 20, 16),
                      children: records
                          .map((r) => Padding(
                                padding: const EdgeInsets.only(bottom: 12),
                                child: _RecordCard(record: r),
                              ))
                          .toList(),
                    ),
            ),
          ],
        );
      },
    );
  }

  Widget _empty() => Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 30),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 72,
                height: 72,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppColors.tint,
                  borderRadius: BorderRadius.circular(18),
                ),
                child: const Icon(Icons.description_outlined,
                    size: 34, color: Color(0xFF93A4C4)),
              ),
              const SizedBox(height: 16),
              const Text('Chưa có hồ sơ nào',
                  style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                      color: AppColors.inkSoft)),
              const SizedBox(height: 6),
              const Text(
                  'Chọn một biểu mẫu ở tab Biểu mẫu để bắt đầu kê khai.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      fontSize: 12.5, color: AppColors.hint, height: 1.5)),
              const SizedBox(height: 18),
              ElevatedButton(
                onPressed: widget.onCreateNew,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.navy,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  padding: const EdgeInsets.symmetric(horizontal: 22),
                  minimumSize: const Size(0, 46),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
                child: const Text('Tạo hồ sơ mới',
                    style: TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w700)),
              ),
            ],
          ),
        ),
      );
}

class _RecordCard extends StatelessWidget {
  final SubmittedRecord record;
  const _RecordCard({required this.record});

  @override
  Widget build(BuildContext context) {
    final form = sessionStore.formById(record.formId) ??
        formTypeById(record.formId);
    final isPending = record.reviewStatus == 'pending';
    return InkWell(
      borderRadius: BorderRadius.circular(AppRadius.card),
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => PreviewScreen(
          formType: form,
          card: record.card,
          supp: record.supp,
          code: record.code,
          readOnly: true,
        ),
      )),
      child: Container(
        padding: const EdgeInsets.all(14),
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
                    Row(children: [
                      Flexible(
                        child: Text(form.title,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                                color: AppColors.ink)),
                      ),
                      const SizedBox(width: 6),
                      if (isPending) _statusChip('Chờ duyệt', AppColors.warn)
                      else _statusChip('Đã duyệt', AppColors.valid),
                    ]),
                    const SizedBox(height: 2),
                    Text(record.code,
                        style: const TextStyle(
                            fontSize: 11.5,
                            color: AppColors.muted,
                            fontFamily: 'monospace')),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Color(0xFFB0BBD2)),
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
                Text(record.date,
                    style: const TextStyle(
                        fontSize: 11.5, color: AppColors.hint)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _statusChip(String label, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(
          color: color.withValues(alpha: .12),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(label,
            style: TextStyle(
                fontSize: 10, fontWeight: FontWeight.w700, color: color)),
      );
}
