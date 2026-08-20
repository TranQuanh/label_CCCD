import 'package:flutter/material.dart';

import '../../core/config/api_config.dart';
import '../../core/theme/app_theme.dart';
import '../../data/api/api_exception.dart';
import '../../data/models/form_type.dart';
import '../../data/repositories/extraction_repository.dart';
import '../review/review_screen.dart';

/// Trạng thái AI đang trích xuất dữ liệu từ 2 mặt thẻ.
///
/// Bản cũ gọi `await` trần, không `try/catch`, không timeout, không lối thoát:
/// với mock thì luôn thành công, nhưng khi nối API thật thì mất mạng = vòng xoay
/// quay vĩnh viễn và người dùng kẹt cứng. Ở đây mọi lỗi đều có màn hình riêng với
/// hai lối ra: **Thử lại** (dùng đúng 2 ảnh cũ) và **Chụp lại**.
class ProcessingScreen extends StatefulWidget {
  final FormType formType;
  final String? frontPath;
  final String? backPath;
  final ExtractionRepository? repository;

  const ProcessingScreen({
    super.key,
    required this.formType,
    this.frontPath,
    this.backPath,
    this.repository,
  });

  @override
  State<ProcessingScreen> createState() => _ProcessingScreenState();
}

class _ProcessingScreenState extends State<ProcessingScreen> {
  late final ExtractionRepository _repo =
      widget.repository ?? ExtractionRepository();

  String? _error;
  bool _running = false;
  int _attempt = 0;

  @override
  void initState() {
    super.initState();
    _run();
  }

  @override
  void dispose() {
    // Chỉ đóng client nếu chính màn này tạo ra nó.
    if (widget.repository == null) _repo.dispose();
    super.dispose();
  }

  Future<void> _run() async {
    setState(() {
      _running = true;
      _error = null;
      _attempt++;
    });
    try {
      final result = await _repo.extract(
        frontPath: widget.frontPath,
        backPath: widget.backPath,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
        builder: (_) => ReviewScreen(
          formType: widget.formType,
          card: result.card,
          needsReview: result.needsReview,
          issues: result.issues,
        ),
      ));
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _running = false;
        _error = e.userMessage;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _running = false;
        _error = 'Lỗi không xác định khi trích xuất:\n$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AppColors.navy, AppColors.navySoft],
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(36),
            child: Center(
              child: _error == null ? _loadingView() : _errorView(),
            ),
          ),
        ),
      ),
    );
  }

  Widget _loadingView() => Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(
            width: 88,
            height: 88,
            child: CircularProgressIndicator(
              strokeWidth: 4,
              color: AppColors.star,
              backgroundColor: Color(0x33F6D24B),
            ),
          ),
          const SizedBox(height: 30),
          const Text('Đang trích xuất dữ liệu',
              style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  color: Colors.white)),
          const SizedBox(height: 8),
          const Text(
              'Mô hình VLM đang đọc & chuẩn hoá thông tin\ntừ 2 mặt thẻ CCCD…',
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 14, color: Color(0xFFB7C9EE), height: 1.5)),
          const SizedBox(height: 10),
          const Text('Mỗi mặt mất khoảng 11–20 giây.',
              style: TextStyle(fontSize: 12.5, color: AppColors.onNavy)),
          const SizedBox(height: 26),
          const Text(
              ApiConfig.useMock
                  ? 'Chế độ mock — không gọi máy chủ'
                  : 'POST ${ApiConfig.extractPath}  ·  ${ApiConfig.baseUrl}',
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 11.5,
                  color: AppColors.onNavy,
                  fontFamily: 'monospace')),
          if (_attempt > 1) ...[
            const SizedBox(height: 10),
            Text('Lần thử thứ $_attempt',
                style:
                    const TextStyle(fontSize: 12, color: AppColors.onNavy)),
          ],
        ],
      );

  Widget _errorView() => SingleChildScrollView(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 84,
              height: 84,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.flagRed.withValues(alpha: .18),
                border: Border.all(color: AppColors.flagRed, width: 2),
              ),
              child: const Icon(Icons.cloud_off,
                  size: 38, color: Colors.white),
            ),
            const SizedBox(height: 24),
            const Text('Không trích xuất được',
                style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                    color: Colors.white)),
            const SizedBox(height: 12),
            Text(_error!,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 13.5, color: Color(0xFFB7C9EE), height: 1.5)),
            const SizedBox(height: 28),
            SizedBox(
              width: double.infinity,
              height: 54,
              child: ElevatedButton.icon(
                onPressed: _running ? null : _run,
                icon: const Icon(Icons.refresh, size: 20),
                label: const Text('Thử lại',
                    style:
                        TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.star,
                  foregroundColor: AppColors.navy,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              height: 52,
              child: OutlinedButton.icon(
                onPressed: () => Navigator.of(context).maybePop(),
                icon: const Icon(Icons.photo_camera_outlined, size: 18),
                label: const Text('Chụp lại',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: BorderSide(color: Colors.white.withValues(alpha: .4), width: 1.5),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
          ],
        ),
      );
}
