import 'dart:async';

import 'package:flutter/material.dart';
// XFile đọc ảnh được cả mobile lẫn web (KHÔNG dùng Image.file / dart:io).
import 'package:image_picker/image_picker.dart' show XFile;
import 'dart:typed_data';
import '../../core/config/api_config.dart';
import '../../core/image_quality/image_quality.dart';
import '../../core/image_quality/image_quality_analyzer.dart';
import '../../core/theme/app_theme.dart';
import '../../data/api/quality_api_client.dart';

/// Màn xem lại ảnh vừa chụp / chọn + cảnh báo chất lượng ảnh.
///
/// Phân tích trên app (sáng/tối/chói/nhòe/nhiễu/độ phân giải) chạy ngay; song
/// song gọi server kiểm tra khung thẻ (lệch/nhỏ/mất góc). Cảnh báo CHỈ để tham
/// khảo: hai nút luôn bấm được, kể cả khi có lỗi nặng hoặc đang chờ server.
///
/// Trả về qua `Navigator.pop`: `true` = dùng ảnh này, `false`/`null` = chụp lại.
class CaptureReviewScreen extends StatefulWidget {
  final String imagePath;
  final bool isBack;

  const CaptureReviewScreen({
    super.key,
    required this.imagePath,
    required this.isBack,
  });

  @override
  State<CaptureReviewScreen> createState() => _CaptureReviewScreenState();
}

class _CaptureReviewScreenState extends State<CaptureReviewScreen> {
  final QualityApiClient _api = QualityApiClient();

  Uint8List? _bytes;
  bool _loadFailed = false;

  List<QualityIssue> _localIssues = const [];
  bool _localDone = false;

  ServerQualityResult? _server;
  // Chế độ mock không gọi server → coi như đã xong.
  bool _serverDone = ApiConfig.useMock;

  @override
  void initState() {
    super.initState();
    if (!ApiConfig.useMock) unawaited(_checkServer());
    unawaited(_analyzeLocal());
  }

  @override
  void dispose() {
    _api.dispose();
    super.dispose();
  }

  Future<void> _analyzeLocal() async {
    Uint8List bytes;
    try {
      bytes = await XFile(widget.imagePath).readAsBytes();
    } catch (_) {
      if (mounted) {
        setState(() {
          _loadFailed = true;
          _localDone = true;
        });
      }
      return;
    }
    if (!mounted) return;
    setState(() => _bytes = bytes);

    final issues = await analyzeImageBytes(bytes);
    if (!mounted) return;
    setState(() {
      _localIssues = issues;
      _localDone = true;
    });
  }

  Future<void> _checkServer() async {
    final result = await _api.checkQuality(
      widget.imagePath,
      side: widget.isBack ? ApiConfig.sideBack : ApiConfig.sideFront,
    );
    if (!mounted) return;
    setState(() {
      _server = result;
      _serverDone = true;
    });
  }

  /// Gộp cảnh báo app + server, loại trùng theo `code` (server ghi đè);
  /// cảnh báo nặng lên trước.
  List<QualityIssue> get _issues {
    final byCode = <String, QualityIssue>{};
    for (final i in _localIssues) {
      byCode[i.code] = i;
    }
    for (final i in _server?.issues ?? const <QualityIssue>[]) {
      byCode[i.code] = i;
    }
    final list = byCode.values.toList();
    final severe =
        list.where((i) => i.severity == QualitySeverity.severe).toList();
    final warning =
        list.where((i) => i.severity != QualitySeverity.severe).toList();
    return [...severe, ...warning];
  }

  void _retake() => Navigator.of(context).pop(false);
  void _use() => Navigator.of(context).pop(true);

  @override
  Widget build(BuildContext context) {
    // Nút Back hệ thống = Chụp lại (pop không kèm kết quả → null).
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          _header(),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
              children: [
                _imageBox(),
                const SizedBox(height: 16),
                _issuesPanel(),
              ],
            ),
          ),
          _bottomBar(),
        ],
      ),
    );
  }

  Widget _header() => Container(
        width: double.infinity,
        color: AppColors.navy,
        padding: EdgeInsets.fromLTRB(
            20, MediaQuery.of(context).padding.top + 12, 20, 16),
        child: Row(children: [
          // Nút quay lại = chụp lại (DEF-35: nhãn cho trình đọc màn hình).
          Tooltip(
            message: 'Chụp lại',
            child: Semantics(
              button: true,
              label: 'Quay lại, chụp lại ảnh',
              child: InkWell(
                onTap: _retake,
                borderRadius: BorderRadius.circular(10),
                child: Container(
                  width: 34,
                  height: 34,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: .12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.arrow_back,
                      size: 18, color: Colors.white),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                    widget.isBack
                        ? 'Kiểm tra ảnh mặt sau'
                        : 'Kiểm tra ảnh mặt trước',
                    style: const TextStyle(
                        fontSize: 15.5,
                        fontWeight: FontWeight.w800,
                        color: Colors.white)),
                const SizedBox(height: 2),
                const Text('Chụm hai ngón để phóng to, kiểm tra chữ rõ nét',
                    style: TextStyle(fontSize: 12, color: AppColors.onNavy)),
              ],
            ),
          ),
        ]),
      );

  Widget _imageBox() {
    Widget child;
    if (_bytes != null) {
      child = InteractiveViewer(
        maxScale: 5,
        child: Image.memory(
          _bytes!,
          fit: BoxFit.contain,
          gaplessPlayback: true,
          errorBuilder: (_, __, ___) => _imagePlaceholder(),
        ),
      );
    } else if (_loadFailed) {
      child = _imagePlaceholder();
    } else {
      child = const Center(
          child: CircularProgressIndicator(color: AppColors.cobalt));
    }
    return Container(
      height: 260,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: const Color(0xFF1A2438),
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.lineSoft),
      ),
      child: child,
    );
  }

  Widget _imagePlaceholder() => const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.broken_image_outlined, size: 40, color: Colors.white54),
            SizedBox(height: 8),
            Text('Không hiển thị được ảnh',
                style: TextStyle(fontSize: 13, color: Colors.white70)),
          ],
        ),
      );

  Widget _issuesPanel() {
    final issues = _issues;
    final hasSevere = issues.any((i) => i.severity == QualitySeverity.severe);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(color: AppColors.lineSoft),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('CHẤT LƯỢNG ẢNH',
              style: TextStyle(
                  fontSize: 11.5,
                  fontWeight: FontWeight.w800,
                  letterSpacing: .6,
                  color: AppColors.navy)),
          const SizedBox(height: 10),
          if (!_localDone)
            _pendingRow('Đang phân tích chất lượng ảnh…')
          else if (issues.isEmpty && _serverDone)
            const Text('✓ Ảnh đạt yêu cầu',
                style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: AppColors.valid)),
          for (final issue in issues) _issueRow(issue),
          if (hasSevere)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text('Nên chụp lại để AI đọc chính xác hơn.',
                  style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      color: AppColors.flagRed)),
            ),
          if (!_serverDone) _pendingRow('Đang kiểm tra khung thẻ…'),
          // Server không kiểm tra được (lỗi mạng, backend cũ, chưa cài OpenCV).
          if (_serverDone && _server == null && !ApiConfig.useMock)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text('Chưa kiểm tra được khung thẻ',
                  style: TextStyle(fontSize: 11.5, color: AppColors.muted)),
            ),
        ],
      ),
    );
  }

  Widget _pendingRow(String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(children: [
          const SizedBox(
            width: 16,
            height: 16,
            child: CircularProgressIndicator(
                strokeWidth: 2, color: AppColors.cobalt),
          ),
          const SizedBox(width: 10),
          Text(text,
              style: const TextStyle(fontSize: 13, color: AppColors.inkSoft)),
        ]),
      );

  Widget _issueRow(QualityIssue issue) {
    final severe = issue.severity == QualitySeverity.severe;
    final color = severe ? AppColors.flagRed : AppColors.warn;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: .45)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(severe ? Icons.error_outline : Icons.warning_amber_rounded,
              size: 20, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(issue.message,
                    style: const TextStyle(
                        fontSize: 13.5, color: AppColors.ink, height: 1.35)),
                if (severe) ...[
                  const SizedBox(height: 3),
                  const Text('Nên chụp lại',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppColors.flagRed)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _bottomBar() => Container(
        color: AppColors.card,
        padding: EdgeInsets.fromLTRB(
            20, 12, 20, MediaQuery.of(context).padding.bottom + 12),
        child: Row(children: [
          Expanded(
            child: SizedBox(
              height: 52,
              child: OutlinedButton.icon(
                onPressed: _retake,
                icon: const Icon(Icons.photo_camera_outlined, size: 18),
                label: const Text('Chụp lại',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.navy,
                  side: const BorderSide(color: AppColors.line, width: 1.5),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: SizedBox(
              height: 52,
              child: ElevatedButton.icon(
                onPressed: _use,
                icon: const Icon(Icons.check, size: 20),
                label: const Text('Dùng ảnh này',
                    style:
                        TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.flagRed,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadius.button)),
                ),
              ),
            ),
          ),
        ]),
      );
}
