import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/scanner_overlay.dart';
import '../../data/models/form_type.dart';
import 'processing_screen.dart';
import 'dart:async';

/// Màn hình 4 — Camera & Quét: chụp mặt trước rồi mặt sau.
///
/// Ảnh chụp được ghi ra thư mục tạm của hệ điều hành và bị xoá ngay sau khi
/// backend trích xuất xong (xem `ExtractionRepository`).
class CameraScreen extends StatefulWidget {
  final FormType formType;
  const CameraScreen({super.key, required this.formType});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  CameraController? _controller;
  final ImagePicker _picker = ImagePicker();

  bool _ready = false;
  bool _busy = false;
  bool _isBack = false;
  String? _frontPath;
  FlashMode _flash = FlashMode.off;
  String? _error;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        if (mounted) {
          setState(() => _error = 'Không tìm thấy camera, tự động chuyển sang thư viện ảnh.');
          _pickFromGallery();
        }
        return;
      }

      // Try to find a back camera, fall back to any camera
      CameraDescription? selectedCamera;

      // First try to find back camera
      for (final camera in cameras) {
        if (camera.lensDirection == CameraLensDirection.back) {
          selectedCamera = camera;
          break;
        }
      }

      // If no back camera, use first available
      if (selectedCamera == null && cameras.isNotEmpty) {
        selectedCamera = cameras.first;
      }

      if (selectedCamera == null) {
        if (mounted) {
          setState(() => _error = 'Không thể truy cập camera.');
          _pickFromGallery();
        }
        return;
      }

      // Use a resolution that's more compatible with emulators
      final ctrl =
          CameraController(selectedCamera, ResolutionPreset.medium, enableAudio: false);

      // Initialize with timeout to prevent hanging
      await ctrl.initialize().timeout(
        const Duration(seconds: 15),
        onTimeout: () => throw Exception('Camera initialization timeout'),
      );

      if (!mounted) {
        await ctrl.dispose();
        return;
      }

      // Small delay to let camera stabilize
      await Future.delayed(const Duration(milliseconds: 500));

      setState(() {
        _controller = ctrl;
        _ready = true;
        _error = null; // Clear any previous error
      });
    } on TimeoutException catch (e) {
      if (mounted) {
        setState(() => _error = 'Khởi tạo camera hết thời gian. Vui lòng thử lại hoặc sử dụng thư viện ảnh.');
        _pickFromGallery();
      }
    } catch (e) {
      if (mounted) {
        setState(() => _error = 'Không mở được camera: $e\nTự động chuyển sang thư viện ảnh.');
        _pickFromGallery();
      }
    }
  }

  Future<void> _toggleFlash() async {
    final next = _flash == FlashMode.off ? FlashMode.torch : FlashMode.off;
    try {
      await _controller?.setFlashMode(next);
      if (mounted) setState(() => _flash = next);
    } catch (_) {
      // Một số thiết bị không có đèn — bỏ qua thay vì làm sập màn hình.
    }
  }

  Future<void> _capture() async {
    if (_controller == null || _busy) return;
    setState(() => _busy = true);
    try {
      final file = await _controller!.takePicture();
      _accept(file.path);
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        _toast('Không chụp được ảnh: $e');
      }
    }
  }

  /// Chọn ảnh có sẵn — trước đây nút này chỉ là hình trang trí, không có `onTap`.
  Future<void> _pickFromGallery() async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final picked = await _picker.pickImage(
        source: ImageSource.gallery,
        imageQuality: 95,
      );
      if (picked == null) {
        if (mounted) setState(() => _busy = false);
        return;
      }
      _accept(picked.path);
    } catch (e) {
      if (mounted) {
        setState(() => _busy = false);
        _toast('Không mở được thư viện ảnh: $e');
      }
    }
  }

  /// Nhận một ảnh: mặt trước thì giữ lại và chuyển bước, mặt sau thì gửi đi xử lý.
  void _accept(String path) {
    if (!mounted) return;
    if (!_isBack) {
      setState(() {
        _frontPath = path;
        _isBack = true;
        _busy = false;
      });
      return;
    }
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
      builder: (_) => ProcessingScreen(
        formType: widget.formType,
        frontPath: _frontPath,
        backPath: path,
      ),
    ));
  }

  void _toast(String msg) => ScaffoldMessenger.of(context)
      .showSnackBar(SnackBar(content: Text(msg)));

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: _error != null
          ? _errorView()
          : !_ready
              ? const Center(
                  child: CircularProgressIndicator(color: AppColors.star))
              : Stack(children: [
                  Positioned.fill(
                    child: _controller != null
                        ? CameraPreview(_controller!)
                        : const Center(
                            child: Icon(
                              Icons.videocam,
                              size: 64,
                              color: Colors.white38,
                            ),
                          ),
                  ),
                  Positioned.fill(
                    child: ScannerOverlay(
                      hint: _busy
                          ? 'Giữ nguyên — đang xử lý ảnh…'
                          : (_isBack
                              ? 'Lật thẻ, đặt mặt sau vào khung hình'
                              : 'Đặt mặt trước vừa vặn vào khung hình'),
                      isBack: _isBack,
                      frontDone: _frontPath != null,
                    ),
                  ),
                  _topBar(),
                  _bottomControls(),
                ]),
    );
  }

  Widget _errorView() => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.no_photography_outlined,
                  size: 48, color: Colors.white54),
              const SizedBox(height: 16),
              Text(_error!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70, fontSize: 14)),
              const SizedBox(height: 24),
              Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                OutlinedButton.icon(
                  onPressed: _pickFromGallery,
                  icon: const Icon(Icons.photo_library_outlined, size: 18),
                  label: const Text('Chọn từ thư viện'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: const BorderSide(color: Colors.white38),
                  ),
                ),
                const SizedBox(width: 12),
                OutlinedButton(
                  onPressed: () => Navigator.of(context).maybePop(),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: const BorderSide(color: Colors.white38),
                  ),
                  child: const Text('Quay lại'),
                ),
              ]),
            ],
          ),
        ),
      );

  Widget _topBar() => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _circle(const Icon(Icons.close, color: Colors.white, size: 20),
                  () => Navigator.of(context).maybePop()),
              Column(children: [
                Text(_isBack ? 'Mặt sau CCCD' : 'Mặt trước CCCD',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w700)),
                Text(_isBack ? 'Bước 2/2' : 'Bước 1/2',
                    style: const TextStyle(
                        color: AppColors.star,
                        fontSize: 11,
                        fontWeight: FontWeight.w600)),
              ]),
              _circle(
                Icon(_flash == FlashMode.off ? Icons.flash_off : Icons.flash_on,
                    color: AppColors.star, size: 20),
                _toggleFlash,
              ),
            ],
          ),
        ),
      );

  Widget _circle(Widget icon, VoidCallback onTap) => InkWell(
        onTap: onTap,
        customBorder: const CircleBorder(),
        child: Container(
          width: 36,
          height: 36,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: .4),
            shape: BoxShape.circle,
          ),
          child: icon,
        ),
      );

  Widget _bottomControls() => Align(
        alignment: Alignment.bottomCenter,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(34, 0, 34, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    InkWell(
                      onTap: _pickFromGallery,
                      borderRadius: BorderRadius.circular(12),
                      child: Container(
                        width: 52,
                        height: 52,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: .12),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: Colors.white24),
                        ),
                        child: const Icon(Icons.photo_library_outlined,
                            color: Colors.white, size: 22),
                      ),
                    ),
                    GestureDetector(
                      onTap: _capture,
                      child: Container(
                        width: 80,
                        height: 80,
                        padding: const EdgeInsets.all(6),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 4),
                        ),
                        child: Container(
                          alignment: Alignment.center,
                          decoration: const BoxDecoration(
                            color: AppColors.flagRed,
                            shape: BoxShape.circle,
                          ),
                          child: _busy
                              ? const SizedBox(
                                  width: 26,
                                  height: 26,
                                  child: CircularProgressIndicator(
                                      color: Colors.white, strokeWidth: 3),
                                )
                              : null,
                        ),
                      ),
                    ),
                    const SizedBox(width: 52),
                  ],
                ),
                const SizedBox(height: 14),
                Text(
                    _busy
                        ? 'Đang xử lý ảnh…'
                        : 'Chụp hoặc chọn ảnh có sẵn từ thư viện',
                    style: const TextStyle(
                        color: AppColors.inactive, fontSize: 12)),
              ],
            ),
          ),
        ),
      );
}
