/// Phân tích chất lượng ảnh CCCD ngay trên app (sáng/tối/chói/nhòe/nhiễu/độ
/// phân giải) bằng `package:image` (Dart thuần — chạy cả mobile lẫn web).
///
/// KHÔNG import `dart:io`. Chạy nặng nên đẩy qua `compute` (isolate riêng trên
/// mobile; trên web `compute` chạy cùng luồng — chấp nhận được với ảnh 512px).
/// Mọi lỗi phân tích → trả danh sách rỗng, không bao giờ làm sập màn hình.
library;

import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;

import 'image_quality.dart';

/// Phân tích [bytes] (JPEG/PNG/WEBP...) và trả danh sách cảnh báo
/// (rỗng = đạt yêu cầu hoặc không phân tích được).
Future<List<QualityIssue>> analyzeImageBytes(Uint8List bytes) async {
  try {
    return await compute(analyzeImageBytesSync, bytes);
  } catch (_) {
    return const [];
  }
}

/// Bản đồng bộ (top-level để dùng với `compute`).
List<QualityIssue> analyzeImageBytesSync(Uint8List bytes) {
  try {
    return _analyze(bytes);
  } catch (_) {
    return const [];
  }
}

List<QualityIssue> _analyze(Uint8List bytes) {
  final decoded = img.decodeImage(bytes);
  if (decoded == null) {
    return const [
      QualityIssue(
        code: 'decode_failed',
        severity: QualitySeverity.warning,
        message: 'Không đọc được ảnh để kiểm tra chất lượng',
      ),
    ];
  }

  // Xoay theo EXIF trước khi đo (ảnh điện thoại thường lưu xoay 90°).
  var image = img.bakeOrientation(decoded);
  final origShort = math.min(image.width, image.height);

  // Thu nhỏ cạnh dài về 512px; `average` ≈ cv2.INTER_AREA ở backend để số đo
  // nhòe/nhiễu của app và server tương đương nhau.
  const target = QualityThresholds.analysisLongSide;
  if (math.max(image.width, image.height) > target) {
    image = image.width >= image.height
        ? img.copyResize(image,
            width: target, interpolation: img.Interpolation.average)
        : img.copyResize(image,
            height: target, interpolation: img.Interpolation.average);
  }

  final w = image.width;
  final h = image.height;
  if (w <= 0 || h <= 0) return const [];

  // Ảnh xám 0–255 (công thức luminance BT.601, giống cv2.COLOR_BGR2GRAY).
  // Dùng giá trị chuẩn hoá để đúng với mọi định dạng kênh (8/16 bit, palette).
  final gray = Float32List(w * h);
  var sum = 0.0;
  var glare = 0;
  var darkPx = 0;
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      final p = image.getPixel(x, y);
      final v = 255.0 *
          (0.299 * p.rNormalized +
              0.587 * p.gNormalized +
              0.114 * p.bNormalized);
      gray[y * w + x] = v;
      sum += v;
      if (v > QualityThresholds.glarePixel) glare++;
      if (v < QualityThresholds.darkPixel) darkPx++;
    }
  }
  final n = w * h;
  final mean = sum / n;
  final glareRatio = glare / n;
  final darkRatio = darkPx / n;

  // Phương sai Laplacian 3x3 (kernel 4 lân cận, như cv2.Laplacian ksize=1) và
  // nhiễu = trung vị |pixel − trung bình 3x3| (đếm bằng histogram 0–255).
  double? lapVar;
  double? noise;
  if (w >= 3 && h >= 3) {
    var lapSum = 0.0;
    var lapSq = 0.0;
    final hist = List<int>.filled(256, 0);
    var count = 0;
    for (var y = 1; y < h - 1; y++) {
      for (var x = 1; x < w - 1; x++) {
        final i = y * w + x;
        final c = gray[i];
        final up = gray[i - w];
        final down = gray[i + w];
        final left = gray[i - 1];
        final right = gray[i + 1];
        final lap = up + down + left + right - 4 * c;
        lapSum += lap;
        lapSq += lap * lap;

        final box = (gray[i - w - 1] +
                up +
                gray[i - w + 1] +
                left +
                c +
                right +
                gray[i + w - 1] +
                down +
                gray[i + w + 1]) /
            9.0;
        final d = (c - box).abs().round();
        hist[d > 255 ? 255 : d]++;
        count++;
      }
    }
    final lapMean = lapSum / count;
    lapVar = lapSq / count - lapMean * lapMean;
    noise = _histMedian(hist, count).toDouble();
  }

  final issues = <QualityIssue>[];

  // Độ phân giải (ảnh gốc).
  if (origShort < QualityThresholds.resolutionSevere) {
    issues.add(const QualityIssue(
      code: 'low_resolution',
      severity: QualitySeverity.severe,
      message:
          'Ảnh có độ phân giải quá thấp — đưa máy lại gần thẻ hoặc chụp bằng camera sau',
    ));
  } else if (origShort < QualityThresholds.resolutionWarning) {
    issues.add(const QualityIssue(
      code: 'low_resolution',
      severity: QualitySeverity.warning,
      message:
          'Ảnh có độ phân giải thấp — đưa máy lại gần thẻ hoặc chụp bằng camera sau',
    ));
  }

  // Tối / sáng.
  if (mean < QualityThresholds.darkSevere) {
    issues.add(const QualityIssue(
      code: 'too_dark',
      severity: QualitySeverity.severe,
      message: 'Ảnh quá tối — hãy chụp nơi đủ sáng hoặc bật đèn flash',
    ));
  } else if (mean < QualityThresholds.darkWarning ||
      darkRatio > QualityThresholds.darkRatioWarning) {
    issues.add(const QualityIssue(
      code: 'too_dark',
      severity: QualitySeverity.warning,
      message: 'Ảnh hơi tối — hãy chụp nơi đủ sáng hoặc bật đèn flash',
    ));
  } else if (mean > QualityThresholds.brightWarning) {
    issues.add(const QualityIssue(
      code: 'too_bright',
      severity: QualitySeverity.warning,
      message: 'Ảnh quá sáng — tránh nguồn sáng chiếu thẳng hoặc tắt đèn flash',
    ));
  }

  // Chói / lóa.
  if (glareRatio > QualityThresholds.glareRatioSevere) {
    issues.add(const QualityIssue(
      code: 'glare',
      severity: QualitySeverity.severe,
      message: 'Ảnh bị chói / lóa sáng — nghiêng thẻ để tránh đèn phản chiếu',
    ));
  } else if (glareRatio > QualityThresholds.glareRatioWarning) {
    issues.add(const QualityIssue(
      code: 'glare',
      severity: QualitySeverity.warning,
      message: 'Ảnh có vùng lóa sáng — nghiêng thẻ để tránh đèn phản chiếu',
    ));
  }

  // Nhòe.
  if (lapVar != null) {
    if (lapVar < QualityThresholds.blurSevere) {
      issues.add(const QualityIssue(
        code: 'blurry',
        severity: QualitySeverity.severe,
        message: 'Ảnh bị nhòe — giữ yên máy và chạm để lấy nét',
      ));
    } else if (lapVar < QualityThresholds.blurWarning) {
      issues.add(const QualityIssue(
        code: 'blurry',
        severity: QualitySeverity.warning,
        message: 'Ảnh hơi nhòe — giữ yên máy và chạm để lấy nét',
      ));
    }
  }

  // Nhiễu (chỉ warning).
  if (noise != null && noise > QualityThresholds.noiseWarning) {
    issues.add(const QualityIssue(
      code: 'noisy',
      severity: QualitySeverity.warning,
      message: 'Ảnh bị nhiễu (lấm tấm hạt) — chụp nơi đủ sáng hơn',
    ));
  }

  return issues;
}

/// Trung vị từ histogram giá trị nguyên 0–255.
int _histMedian(List<int> hist, int count) {
  final half = count ~/ 2;
  var acc = 0;
  for (var v = 0; v < hist.length; v++) {
    acc += hist[v];
    if (acc > half) return v;
  }
  return hist.length - 1;
}


