import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/api/api_exception.dart';
import '../../data/session/session_store.dart';
import '../scan/onboarding_screen.dart';
import 'edit_profile_screen.dart';
import 'profile_detail_screen.dart';

/// Tab Profile — Quản lý hồ sơ CCCD cá nhân của người dùng.
///
/// Xuất hiện cùng 3 tab Biểu mẫu, Hồ sơ, Tài khoản.
/// Cho phép xem danh sách profiles, tạo mới, chỉnh sửa, xóa và sử dụng trong biểu mẫu.
class ProfileTab extends StatefulWidget {
  final VoidCallback? onUseInForms;

  const ProfileTab({super.key, this.onUseInForms});

  @override
  State<ProfileTab> createState() => _ProfileTabState();
}

class _ProfileTabState extends State<ProfileTab> {
  @override
  void initState() {
    super.initState();
    // Nạp lại profile khi mở tab
    WidgetsBinding.instance.addPostFrameCallback((_) {
      sessionStore.loadProfiles();
    });
  }

  Future<void> _confirmDelete(int index) async {
    final profile = sessionStore.profiles[index];
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Xác nhận xóa Profile?'),
        content: Text(
          'Bạn có chắc chắn muốn xóa profile "${profile.fullName.isNotEmpty ? profile.fullName : 'Chưa có tên'}"?\n'
          'Hành động này không thể hoàn tác.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Hủy'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child:
                const Text('Xóa Profile', style: TextStyle(color: AppColors.flagRed)),
          ),
        ],
      ),
    );

    if (ok == true) {
      try {
        await sessionStore.removeProfileAt(index);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Đã xóa Profile CCCD.')),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Lỗi khi xóa profile: $e')),
          );
        }
      }
    }
  }

  void _showAddProfileBottomSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      // `sheetContext` chỉ dùng để đóng sheet; mọi điều hướng/snackbar sau đó
      // dùng `context` của State (sheet đã bị huỷ sau khi pop).
      builder: (sheetContext) => Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(sheetContext).viewInsets.bottom,
          left: 24,
          right: 24,
          top: 24,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(height: 16),
            const Text(
              'Thêm Profile CCCD mới',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w800,
                color: AppColors.ink,
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton.icon(
                onPressed: () {
                  Navigator.of(sheetContext).pop(); // Đóng bottom sheet
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => const OnboardingScreen(
                        isProfileScan: true,
                        isForNewProfile: true,
                      ),
                    ),
                  );
                },
                icon: const Icon(Icons.camera_alt, size: 20),
                label: const Text('Quét CCCD tạo Profile mới',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.flagRed,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              height: 56,
              child: OutlinedButton.icon(
                onPressed: () {
                  Navigator.of(sheetContext).pop(); // Đóng bottom sheet
                  Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => const EditProfileScreen(),
                    ),
                  );
                },
                icon: const Icon(Icons.edit_note, size: 20),
                label: const Text('Nhập thông tin thủ công',
                    style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.navy,
                  side: const BorderSide(color: AppColors.line),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
            const SizedBox(height: 16),
            sessionStore.latestCard != null
                ? SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: OutlinedButton.icon(
                      onPressed: () async {
                        // Messenger lấy từ context của State (không phải sheet).
                        final messenger = ScaffoldMessenger.of(context);
                        Navigator.of(sheetContext).pop(); // Đóng bottom sheet
                        try {
                          final success =
                              await sessionStore.importProfileFromLatestRecord();
                          if (!mounted) return;
                          if (success) {
                            messenger.showSnackBar(
                              const SnackBar(
                                content: Text('✓ Đã nhập thông tin từ hồ sơ gần nhất!'),
                                backgroundColor: AppColors.valid,
                              ),
                            );
                          }
                        } on ApiException catch (e) {
                          // Trùng số CCCD với profile đã có / lỗi kết nối.
                          if (!mounted) return;
                          messenger.showSnackBar(
                            SnackBar(
                              content: Text(e.userMessage),
                              backgroundColor: AppColors.flagRed,
                            ),
                          );
                        } catch (e) {
                          if (!mounted) return;
                          messenger.showSnackBar(
                            SnackBar(content: Text('Lỗi khi nhập từ hồ sơ gần nhất: $e')),
                          );
                        }
                      },
                      icon: const Icon(Icons.history, size: 20),
                      label: const Text('Dùng cấu hình cũ',
                          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.navy,
                        side: const BorderSide(color: AppColors.line),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(AppRadius.button)),
                      ),
                    ),
                  )
                : const SizedBox.shrink(),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    try {
      return Scaffold(
        appBar: AppBar(
          title: const Text('Profiles'),
          centerTitle: true,
          backgroundColor: AppColors.navy,
          elevation: 0,
          actions: [
            if (widget.onUseInForms != null)
              IconButton(
                icon: const Icon(Icons.assignment_outlined),
                tooltip: 'Dùng trong biểu mẫu',
                onPressed: widget.onUseInForms,
              ),
          ],
        ),
        body: AnimatedBuilder(
          animation: sessionStore,
          builder: (context, _) {
            final profiles = sessionStore.profiles;
            final selectedIndex = sessionStore.selectedProfileIndex;

            if (profiles.isEmpty) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.badge_outlined,
                        size: 80,
                        color: AppColors.cobalt,
                      ),
                      const SizedBox(height: 24),
                      const Text(
                        'Chưa có profile nào',
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w900,
                          color: AppColors.ink,
                        ),
                      ),
                      const SizedBox(height: 12),
                      const Text(
                        'Nhấn nút thêm để tạo profile mới',
                        style: TextStyle(
                          fontSize: 14,
                          color: AppColors.muted,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            } else {
              return ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: profiles.length,
                separatorBuilder: (_, __) => const SizedBox(height: 12),
                itemBuilder: (context, index) {
                  final profile = profiles[index];
                  final isSelected = index == selectedIndex;

                  // ListTile PHẢI có Material làm cha trực tiếp (không có widget
                  // tô màu nào xen giữa). Trước đây bọc trong Container có màu
                  // nền → Flutter báo "ListTile background color or ink splashes
                  // may be invisible". Nền, viền, bo góc giờ nằm trên Material.
                  final radius = BorderRadius.circular(16);
                  return Material(
                    color: isSelected
                        ? AppColors.cobalt.withValues(alpha: .08)
                        : Colors.white,
                    clipBehavior: Clip.antiAlias,
                    shape: RoundedRectangleBorder(
                      borderRadius: radius,
                      side: BorderSide(
                        color: isSelected
                            ? AppColors.cobalt.withValues(alpha: .3)
                            : AppColors.lineSoft,
                      ),
                    ),
                    child: ListTile(
                      shape: RoundedRectangleBorder(borderRadius: radius),
                      contentPadding: const EdgeInsets.all(16),
                      leading: CircleAvatar(
                        radius: 24,
                        backgroundColor: AppColors.cobalt.withValues(alpha: .2),
                        child: Text(
                          profile.fullName.isNotEmpty
                              ? profile.fullName[0].toUpperCase()
                              : '?',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: AppColors.cobalt,
                          ),
                        ),
                      ),
                      title: Text(
                        profile.fullName.isNotEmpty
                            ? profile.fullName
                            : 'Chưa có tên',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: AppColors.ink,
                        ),
                      ),
                      subtitle: Text(
                        profile.idNumber.isNotEmpty
                            ? profile.idNumber
                            : 'Chưa có số CCCD',
                        style: const TextStyle(
                          fontSize: 14,
                          color: AppColors.muted,
                        ),
                      ),
                      trailing: PopupMenuButton<int>(
                        offset: const Offset(0, 40),
                        color: Colors.white,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        icon: const Icon(
                          Icons.more_vert,
                          color: AppColors.muted,
                        ),
                        itemBuilder: (context) => [
                          PopupMenuItem<int>(
                            value: 1,
                            child: const Row(
                              children: [
                                Icon(Icons.edit, color: AppColors.navy),
                                SizedBox(width: 12),
                                Text('Chỉnh sửa'),
                              ],
                            ),
                          ),
                          PopupMenuItem<int>(
                            value: 2,
                            child: const Row(
                              children: [
                                Icon(Icons.delete, color: AppColors.flagRed),
                                SizedBox(width: 12),
                                Text('Xóa'),
                              ],
                            ),
                          ),
                        ],
                        onSelected: (value) async {
                          // PopupMenuButton tự đóng menu khi chọn item —
                          // KHÔNG tự gọi Navigator.pop() ở đây, nếu không sẽ
                          // pop nhầm route màn hình chính và để lộ màn hình đen.
                          if (value == 1) {
                            // Edit profile
                            Navigator.of(context).push(
                              MaterialPageRoute<void>(
                                builder: (_) => EditProfileScreen(
                                  initialCard: profile,
                                  profileIndex: index,
                                ),
                              ),
                            );
                          } else if (value == 2) {
                            // Delete profile
                            await _confirmDelete(index);
                          }
                        },
                      ),
                      onTap: () {
                        // Mở màn hình xem chi tiết profile (có nút Sửa).
                        Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) =>
                                ProfileDetailScreen(profile: profile),
                          ),
                        );
                      },
                    ),
                  );
                },
              );
            }
          },
        ),
        floatingActionButton: FloatingActionButton(
          backgroundColor: AppColors.flagRed,
          foregroundColor: Colors.white,
          onPressed: _showAddProfileBottomSheet,
          child: const Icon(Icons.add),
        ),
      );
    } catch (e) {
      return Center(
        child: Text(
          'Lỗi không mong đợi: $e\nVui lòng khởi động lại ứng dụng.',
          textAlign: TextAlign.center,
          style: const TextStyle(color: AppColors.flagRed),
        ),
      );
    }
  }
}