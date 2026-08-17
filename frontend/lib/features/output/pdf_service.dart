import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../../data/models/form_type.dart';
import '../../data/models/id_card.dart';

/// Lỗi xuất PDF đã diễn giải sẵn cho người dùng.
class PdfExportException implements Exception {
  final String message;
  const PdfExportException(this.message);
  @override
  String toString() => message;
}

/// Sinh biểu mẫu hoàn chỉnh dạng PDF A4 và mở hộp thoại in / lưu.
class PdfService {
  const PdfService._();

  static String _two(int n) => n.toString().padLeft(2, '0');

  static Future<void> exportForm({
    required FormType formType,
    required IdCardData card,
    required Map<String, String> supp,
    required String code,
  }) async {
    // Roboto hỗ trợ đầy đủ dấu tiếng Việt, nhưng `PdfGoogleFonts` TẢI FONT QUA
    // MẠNG lúc chạy. Offline là hỏng — báo lỗi rõ ràng thay vì ném exception thô.
    // Muốn dùng được offline: nhúng file .ttf vào assets rồi đọc bằng
    // `pw.Font.ttf(await rootBundle.load('assets/fonts/Roboto-Regular.ttf'))`.
    final pw.Font base;
    final pw.Font bold;
    try {
      base = await PdfGoogleFonts.robotoRegular();
      bold = await PdfGoogleFonts.robotoBold();
    } catch (_) {
      throw const PdfExportException(
          'Không tải được phông chữ tiếng Việt (cần mạng lần đầu). '
          'Kiểm tra kết nối rồi thử lại.');
    }

    final now = DateTime.now();
    final dateStr =
        'Ngày ${_two(now.day)} tháng ${_two(now.month)} năm ${now.year}';

    final cardMap = card.toMap();
    final cardRows = IdCardData.displayOrder.map((e) {
      final v = cardMap[e[0]] ?? '';
      return [e[1], v.trim().isEmpty ? '—' : v];
    }).toList();

    final suppRows = formType.supp.map((s) {
      final v = (supp[s.key] ?? '').trim();
      return [s.label, v.isEmpty ? '—' : v];
    }).toList();

    final doc = pw.Document();
    doc.addPage(
      pw.MultiPage(
        pageFormat: PdfPageFormat.a4,
        margin: const pw.EdgeInsets.symmetric(horizontal: 48, vertical: 56),
        theme: pw.ThemeData.withFont(base: base, bold: bold),
        build: (ctx) => [
          pw.Center(
            child: pw.Column(children: [
              pw.Text('CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM',
                  style: pw.TextStyle(
                      fontSize: 12, fontWeight: pw.FontWeight.bold)),
              pw.SizedBox(height: 3),
              pw.Text('Độc lập – Tự do – Hạnh phúc',
                  style: pw.TextStyle(
                      fontSize: 12, fontWeight: pw.FontWeight.bold)),
              pw.SizedBox(height: 5),
              pw.Container(width: 150, height: 1, color: PdfColors.black),
            ]),
          ),
          pw.SizedBox(height: 22),
          pw.Center(
            child: pw.Text(formType.title.toUpperCase(),
                textAlign: pw.TextAlign.center,
                style: pw.TextStyle(
                    fontSize: 16, fontWeight: pw.FontWeight.bold)),
          ),
          pw.SizedBox(height: 5),
          pw.Center(
            child: pw.Text('Mã hồ sơ: $code',
                style: const pw.TextStyle(
                    fontSize: 10, color: PdfColors.grey700)),
          ),
          pw.SizedBox(height: 20),
          _section('I. THÔNG TIN CÔNG DÂN'),
          _table(cardRows),
          pw.SizedBox(height: 16),
          _section('II. THÔNG TIN BỔ SUNG'),
          _table(suppRows),
          pw.SizedBox(height: 28),
          pw.Align(
            alignment: pw.Alignment.centerRight,
            child: pw.Column(children: [
              pw.Text(dateStr,
                  style: pw.TextStyle(
                      fontSize: 11, fontStyle: pw.FontStyle.italic)),
              pw.SizedBox(height: 4),
              pw.Text('NGƯỜI KHAI',
                  style: pw.TextStyle(
                      fontSize: 12, fontWeight: pw.FontWeight.bold)),
              pw.Text('(Ký, ghi rõ họ tên)',
                  style: const pw.TextStyle(
                      fontSize: 10, color: PdfColors.grey700)),
              pw.SizedBox(height: 40),
              pw.Text(card.fullName,
                  style: pw.TextStyle(
                      fontSize: 13,
                      fontWeight: pw.FontWeight.bold,
                      color: PdfColor.fromInt(0xFF0A2A66))),
            ]),
          ),
        ],
      ),
    );

    final safeCode = code.replaceAll('#', '');
    await Printing.layoutPdf(
      onLayout: (_) => doc.save(),
      name: 'SmartID_${formType.id}_$safeCode.pdf',
    );
  }

  static pw.Widget _section(String title) => pw.Container(
        margin: const pw.EdgeInsets.only(bottom: 8),
        padding: const pw.EdgeInsets.only(left: 8),
        decoration: const pw.BoxDecoration(
          border: pw.Border(
            left: pw.BorderSide(color: PdfColor.fromInt(0xFFDA251D), width: 3),
          ),
        ),
        child: pw.Text(title,
            style: pw.TextStyle(
                fontSize: 12,
                fontWeight: pw.FontWeight.bold,
                color: PdfColor.fromInt(0xFF0A2A66))),
      );

  static pw.Widget _table(List<List<String>> rows) => pw.Column(
        children: rows
            .map((r) => pw.Container(
                  padding: const pw.EdgeInsets.symmetric(vertical: 5),
                  decoration: const pw.BoxDecoration(
                    border: pw.Border(
                      bottom:
                          pw.BorderSide(color: PdfColors.grey400, width: .5),
                    ),
                  ),
                  child: pw.Row(
                    crossAxisAlignment: pw.CrossAxisAlignment.start,
                    children: [
                      pw.SizedBox(
                        width: 150,
                        child: pw.Text(r[0],
                            style: const pw.TextStyle(
                                fontSize: 11, color: PdfColors.grey800)),
                      ),
                      pw.Expanded(
                        child: pw.Text(r[1],
                            style: pw.TextStyle(
                                fontSize: 11,
                                fontWeight: pw.FontWeight.bold)),
                      ),
                    ],
                  ),
                ))
            .toList(),
      );
}
