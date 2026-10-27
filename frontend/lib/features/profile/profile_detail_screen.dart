import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/section_label.dart';
import '../../data/models/id_card.dart';
import '../../data/session/session_store.dart';
import 'cccd_card_widget.dart';
import 'edit_profile_screen.dart';

/// Màn hình xem chi tiết một Profile CCCD.
///
/// Giữ THAM CHIẾU [profile] (không giữ chỉ số cố định) và mỗi lần build tìm lại
/// vị trí hiện tại qua [SessionStore.indexOfProfile] — danh sách có nạp lại từ
/// server/đổi thứ tự thì màn hình vẫn trỏ đúng profile. Bọc AnimatedBuilder nên
/// sau khi "Sửa" → lưu → quay lại, thông tin hiển thị là bản vừa chỉnh sửa.
class ProfileDetailScreen extends StatelessWidget {
  final IdCardData profile;

  const ProfileDetailScreen({super.key, required this.profile});

  void _copy(BuildContext context, String label, String value) {
    if (value.trim().isEmpty) return;
    Clipboard.setData(ClipboardData(text: value.trim()));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('✓ Đã sao chép $label'),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  void _edit(BuildContext context, IdCardData current, int index) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => EditProfileScreen(
          initialCard: current,
          profileIndex: index,
        ),
      ),
    );
  }

  Future<void> _setDefault(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      // Tìm lại vị trí ngay lúc bấm (không dùng chỉ số cũ).
      final index = sessionStore.indexOfProfile(profile);
      if (index < 0) return;
      await sessionStore.selectProfileAt(index);
      messenger.showSnackBar(
        const SnackBar(
          content: Text('✓ Đã đặt làm profile mặc định'),
          backgroundColor: AppColors.valid,
          duration: Duration(seconds: 2),
        ),
      );
    } catch (e) {
      messenger.showSnackBar(
        SnackBar(content: Text('Lỗi khi chọn profile: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionStore,
      builder: (context, _) {
        final profiles = sessionStore.profiles;
        final profileIndex = sessionStore.indexOfProfile(profile);
        // Profile có thể đã bị xoá ở nơi khác → hiển thị trạng thái trống.
        if (profileIndex < 0) {
          return Scaffold(
            appBar: AppBar(
              backgroundColor: AppColors.navy,
              foregroundColor: Colors.white,
              title: const Text('Thông tin Profile'),
            ),
            body: const Center(
              child: Text('Profile không còn tồn tại.',
                  style: TextStyle(color: AppColors.muted)),
            ),
          );
        }

        // Đặt tên `current` (không dùng `profile`) để không che field [profile]
        // đã được dùng ở trên — Dart sẽ báo lỗi biên dịch nếu trùng tên.
        final current = profiles[profileIndex];
        final isDefault = sessionStore.selectedProfileIndex == profileIndex;
        final map = current.toMap();

        return Scaffold(
          backgroundColor: AppColors.bg,
          appBar: AppBar(
            backgroundColor: AppColors.navy,
            foregroundColor: Colors.white,
            elevation: 0,
            title: const Text('Thông tin Profile',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
            actions: [
              IconButton(
                icon: const Icon(Icons.edit_outlined),
                tooltip: 'Sửa profile',
                onPressed: () => _edit(context, current, profileIndex),
              ),
            ],
          ),
          body: ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
            children: [
              CccdCardWidget(
                card: current,
                onEdit: () => _edit(context, current, profileIndex),
              ),
              const SizedBox(height: 20),
              const SectionLabel(
                text: 'CHI TIẾT THÔNG TIN',
                barColor: AppColors.cobalt,
                textColor: AppColors.navy,
              ),
              const SizedBox(height: 10),
              // Material (thay vì Container có màu) để hiệu ứng nhấn giữ của
              // InkWell ở từng dòng hiện được trên nền trắng.
              Material(
                color: Colors.white,
                clipBehavior: Clip.antiAlias,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppRadius.card),
                  side: const BorderSide(color: AppColors.lineSoft),
                ),
                child: Column(
                  children: [
                    for (var i = 0; i < IdCardData.displayOrder.length; i++)
                      _row(
                        context,
                        IdCardData.displayOrder[i][1],
                        map[IdCardData.displayOrder[i][0]] ?? '',
                        isLast: i == IdCardData.displayOrder.length - 1,
                      ),
                  ],
                ),
              ),
            ],
          ),
          bottomNavigationBar: Container(
            decoration: const BoxDecoration(
              color: Colors.white,
              border: Border(top: BorderSide(color: AppColors.lineSoft)),
            ),
            padding: EdgeInsets.fromLTRB(
                20, 12, 20, MediaQuery.of(context).padding.bottom + 14),
            child: Row(
              children: [
                Expanded(
                  child: SizedBox(
                    height: 52,
                    child: OutlinedButton.icon(
                      onPressed: isDefault ? null : () => _setDefault(context),
                      icon: Icon(
                          isDefault ? Icons.check_circle : Icons.star_outline,
                          size: 18),
                      label: Text(isDefault ? 'Đang mặc định' : 'Đặt mặc định',
                          style: const TextStyle(
                              fontSize: 14, fontWeight: FontWeight.w700)),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.navy,
                        side: const BorderSide(color: AppColors.line),
                        shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(AppRadius.button)),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: SizedBox(
                    height: 52,
                    child: ElevatedButton.icon(
                      onPressed: () => _edit(context, current, profileIndex),
                      icon: const Icon(Icons.edit, size: 18),
                      label: const Text('Sửa thông tin',
                          style: TextStyle(
                              fontSize: 15, fontWeight: FontWeight.w700)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.flagRed,
                        foregroundColor: Colors.white,
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(AppRadius.button)),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _row(BuildContext context, String label, String value,
      {bool isLast = false}) {
    final display = value.trim().isEmpty ? '—' : value.trim();
    return InkWell(
      onLongPress: () => _copy(context, label, value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
        decoration: BoxDecoration(
          border: isLast
              ? null
              : const Border(bottom: BorderSide(color: Color(0xFFF0F3F9))),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 120,
              child: Text(label,
                  style: const TextStyle(fontSize: 13, color: AppColors.muted)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(display,
                  textAlign: TextAlign.right,
                  style: const TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w600,
                      color: AppColors.ink)),
            ),
          ],
        ),
      ),
    );
  }
}
