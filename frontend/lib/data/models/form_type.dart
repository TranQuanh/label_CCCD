import 'package:flutter/material.dart';

/// Trường bổ sung của một loại biểu mẫu — nằm ngoài thông tin trên thẻ CCCD,
/// do người dùng nhập tay ở màn hình đối chiếu.
///
/// P2: đến từ server qua `GET /api/v1/forms` (`required_fields` JSONB
/// `[{key,label,hint}, ...]`) — nguồn duy nhất; bản mock dùng `kFormTypes`.
class SuppField {
  final String key;
  final String label;
  final String hint;

  const SuppField({required this.key, required this.label, required this.hint});

  factory SuppField.fromJson(Map<String, dynamic> json) => SuppField(
        key: json['key']?.toString() ?? '',
        label: json['label']?.toString() ?? '',
        hint: json['hint']?.toString() ?? '',
      );
}

/// Một loại biểu mẫu: định nghĩa tiêu đề, mô tả, các trường bổ sung.
///
/// Màu/glyph KHÔNG có trên server — giữ phía client theo slug để hiển thị ổn
/// định; slug lạ (admin thêm mới) dùng bộ mặc định.
class FormType {
  final String id; // slug
  final String title;
  final String desc;
  final bool requiresFront;
  final bool requiresBack;
  final List<SuppField> supp;
  final String glyph;
  final Color color;
  final Color tint;
  final List<dynamic> layout; // JSON layout for supplemental fields rendering

  const FormType({
    required this.id,
    required this.title,
    required this.desc,
    this.requiresFront = true,
    this.requiresBack = true,
    this.supp = const [],
    this.glyph = '📋',
    this.color = const Color(0xFF1656C4),
    this.tint = const Color(0xFFEAF0FB),
    this.layout = const [],
  });

  /// Dựng từ phản hồi `GET /api/v1/forms`. `required_fields` là list
  /// `{key,label,hint}`. Glyph/màu lấy từ bảng tra theo slug.
  factory FormType.fromJson(Map<String, dynamic> json) {
    final style = _kFormStyle[json['slug']?.toString()] ??
        const _FormStyle('📋', Color(0xFF1656C4), Color(0xFFEAF0FB));
    final fields = <SuppField>[];
    final raw = json['required_fields'];
    if (raw is List) {
      for (final f in raw) {
        if (f is Map<String, dynamic>) fields.add(SuppField.fromJson(f));
      }
    }
    final layoutRaw = json['layout'];
    final List<dynamic> layoutList = layoutRaw is List ? List<dynamic>.from(layoutRaw) : <dynamic>[];

    return FormType(
      id: json['slug']?.toString() ?? '',
      title: json['name']?.toString() ?? '',
      desc: json['description']?.toString() ?? '',
      requiresFront: json['requires_front'] is bool
          ? json['requires_front'] as bool
          : true,
      requiresBack: json['requires_back'] is bool
          ? json['requires_back'] as bool
          : true,
      supp: fields,
      glyph: style.glyph,
      color: style.color,
      tint: style.tint,
      layout: layoutList,
    );
  }
}

/// Màu/glyph client-side cho các slug quen thuộc — không phải hợp đồng API.
class _FormStyle {
  final String glyph;
  final Color color;
  final Color tint;
  const _FormStyle(this.glyph, this.color, this.tint);
}

const _kFormStyle = <String, _FormStyle>{
  'atm_open': _FormStyle('🏦', Color(0xFF0B6E4F), Color(0xFFE5F4EE)),
  'health_declare': _FormStyle('🩺', Color(0xFFB3261E), Color(0xFFFBEAE9)),
  'service_contract': _FormStyle('📄', Color(0xFF1656C4), Color(0xFFEAF0FB)),
};

/// Danh sách biểu mẫu dùng cho chế độ MOCK (`ApiConfig.useMock`) — không có
/// server. Ở chế độ thật, danh mục phải lấy từ `GET /api/v1/forms`.
const kFormTypes = <FormType>[
  FormType(
    id: 'atm_open',
    title: 'Đăng ký mở thẻ ATM',
    desc: 'Kê khai thông tin cá nhân khi mở tài khoản thanh toán.',
    glyph: '🏦',
    color: Color(0xFF0B6E4F),
    tint: Color(0xFFE5F4EE),
    supp: [
      SuppField(
        key: 'phone',
        label: 'Số điện thoại liên hệ',
        hint: 'Nhập số điện thoại đang sử dụng',
      ),
      SuppField(
        key: 'occupation',
        label: 'Nghề nghiệp hiện tại',
        hint: 'Ví dụ: Nhân viên văn phòng',
      ),
    ],
    layout: [], // default empty layout; can be customized later
  ),
  FormType(
    id: 'health_declare',
    title: 'Khai báo y tế',
    desc: 'Tờ khai sức khỏe phục vụ khám chữa bệnh.',
    glyph: '🩺',
    color: Color(0xFFB3261E),
    tint: Color(0xFFFBEAE9),
    supp: [
      SuppField(
        key: 'phone',
        label: 'Số điện thoại liên hệ',
        hint: 'Nhập số điện thoại đang sử dụng',
      ),
      SuppField(
        key: 'symptoms',
        label: 'Triệu chứng (nếu có)',
        hint: 'Nhập triệu chứng hoặc ghi "Không"',
      ),
    ],
    layout: [],
  ),
  FormType(
    id: 'service_contract',
    title: 'Hợp đồng dịch vụ',
    desc: 'Đăng ký ký hợp đồng cung cấp dịch vụ.',
    glyph: '📄',
    color: Color(0xFF1656C4),
    tint: Color(0xFFEAF0FB),
    supp: [
      SuppField(
        key: 'phone',
        label: 'Số điện thoại liên hệ',
        hint: 'Nhập số điện thoại đang sử dụng',
      ),
      SuppField(
        key: 'company',
        label: 'Công ty / đơn vị',
        hint: 'Nhập tên công ty nếu ký thay tổ chức',
      ),
    ],
    layout: [],
  ),
];

/// Tra loại biểu mẫu theo id; trả về biểu mẫu đầu tiên nếu không tìm thấy.
FormType formTypeById(String id) {
  for (final f in kFormTypes) {
    if (f.id == id) return f;
  }
  return kFormTypes.first;
}