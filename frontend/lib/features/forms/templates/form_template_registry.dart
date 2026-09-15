import 'package:flutter/material.dart';

import '../../../data/models/form_type.dart';
import '../../../data/models/id_card.dart';
import 'atm_open_template.dart';
import 'health_declare_template.dart';
import 'service_contract_template.dart';

/// Kiểu dữ liệu truyền vào mỗi template.
///
/// [mode] phân biệt 3 ngữ cảnh render:
///   - `preview`  : xem trước biểu mẫu trống (trước khi quét)
///   - `review`   : đối chiếu & bổ sung thông tin sau khi AI trích xuất
///   - `output`   : biểu mẫu hoàn chỉnh (sau khi review, trước/sau khi gửi)
enum FormRenderMode { preview, review, output }

/// Dữ liệu đầy đủ truyền vào template.
class FormTemplateData {
  final FormType formType;
  final IdCardData card;
  final Map<String, String> supp;
  final String code;
  final FormRenderMode mode;

  /// Controllers cho màn hình review (chỉnh sửa trực tiếp).
  /// Null khi mode != review.
  final Map<String, TextEditingController>? cardControllers;
  final Map<String, TextEditingController>? suppControllers;

  const FormTemplateData({
    required this.formType,
    required this.card,
    required this.supp,
    required this.code,
    required this.mode,
    this.cardControllers,
    this.suppControllers,
  });

  /// Lấy giá trị hiển thị của một trường thẻ.
  /// Ở chế độ review: lấy từ controller (giá trị đang gõ).
  /// Ở chế độ khác: lấy từ card model.
  String cardValue(String key) {
    if (mode == FormRenderMode.review && cardControllers != null) {
      return cardControllers![key]?.text ?? '';
    }
    return card.toMap()[key] ?? '';
  }

  /// Lấy giá trị hiển thị của một trường bổ sung.
  String suppValue(String key) {
    if (mode == FormRenderMode.review && suppControllers != null) {
      return suppControllers![key]?.text ?? '';
    }
    return supp[key] ?? '';
  }

  /// Trả về true nếu đang ở chế độ preview (trường để trống '—').
  bool get isPreview => mode == FormRenderMode.preview;

  /// Trả về true nếu đang ở chế độ có thể chỉnh sửa.
  bool get isEditable => mode == FormRenderMode.review;
}

/// Registry trung tâm: ánh xạ slug → Widget template.
///
/// Cách dùng:
/// ```dart
/// final widget = FormTemplateRegistry.buildPreview(formType, card, supp, code);
/// final widget = FormTemplateRegistry.buildReview(formType, card, supp, code, cardCtls, suppCtls);
/// final widget = FormTemplateRegistry.buildOutput(formType, card, supp, code);
/// ```
///
/// Nếu slug chưa có template riêng → trả `null` → caller dùng generic renderer cũ.
/// Điều này đảm bảo backward compatible khi thêm form mới từ server.
class FormTemplateRegistry {
  FormTemplateRegistry._();

  /// Builders theo slug. Mỗi builder nhận [FormTemplateData] và trả Widget.
  static final Map<String, Widget Function(FormTemplateData)> _builders = {
    'atm_open': (data) => AtmOpenTemplate(data: data),
    'health_declare': (data) => HealthDeclareTemplate(data: data),
    'service_contract': (data) => ServiceContractTemplate(data: data),
  };

  /// Kiểm tra slug có template riêng không.
  static bool hasTemplate(String slug) => _builders.containsKey(slug);

  /// Build template cho màn hình xem trước (trống).
  static Widget? buildPreview({
    required FormType formType,
    required IdCardData card,
    required Map<String, String> supp,
    String code = '',
  }) {
    final builder = _builders[formType.id];
    if (builder == null) return null;
    return builder(FormTemplateData(
      formType: formType,
      card: card,
      supp: supp,
      code: code,
      mode: FormRenderMode.preview,
    ));
  }

  /// Build template cho màn hình review (có controller chỉnh sửa).
  static Widget? buildReview({
    required FormType formType,
    required IdCardData card,
    required Map<String, String> supp,
    required String code,
    required Map<String, TextEditingController> cardControllers,
    required Map<String, TextEditingController> suppControllers,
  }) {
    final builder = _builders[formType.id];
    if (builder == null) return null;
    return builder(FormTemplateData(
      formType: formType,
      card: card,
      supp: supp,
      code: code,
      mode: FormRenderMode.review,
      cardControllers: cardControllers,
      suppControllers: suppControllers,
    ));
  }

  /// Build template cho màn hình output (hoàn chỉnh, chỉ đọc).
  static Widget? buildOutput({
    required FormType formType,
    required IdCardData card,
    required Map<String, String> supp,
    required String code,
  }) {
    final builder = _builders[formType.id];
    if (builder == null) return null;
    return builder(FormTemplateData(
      formType: formType,
      card: card,
      supp: supp,
      code: code,
      mode: FormRenderMode.output,
    ));
  }
}
