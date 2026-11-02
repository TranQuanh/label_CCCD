import 'package:flutter/material.dart';

<<<<<<< HEAD
/// Một trường người dùng phải nhập tay (AI không đọc được từ thẻ).
=======
/// Trường bổ sung của một loại biểu mẫu — nằm ngoài thông tin trên thẻ CCCD,
/// do người dùng nhập tay ở màn hình đối chiếu.
///
/// P2: đến từ server qua `GET /api/v1/forms` (`required_fields` JSONB
/// `[{key,label,hint}, ...]`) — nguồn duy nhất; bản mock dùng `kFormTypes`.
>>>>>>> 8593503 (add data)
class SuppField {
  final String key;
  final String label;
  final String hint;
<<<<<<< HEAD
  const SuppField(this.key, this.label, this.hint);
}

/// Một loại biểu mẫu trong danh mục.
class FormType {
  final String id;
  final String title;
  final String desc;
  final Color color;
  final Color tint;
  final String glyph;
  final List<SuppField> supp;
=======

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
>>>>>>> 8593503 (add data)

  const FormType({
    required this.id,
    required this.title,
    required this.desc,
<<<<<<< HEAD
    required this.color,
    required this.tint,
    required this.glyph,
    required this.supp,
  });
}

const _phone = SuppField('phone', 'Số điện thoại', '09xx xxx xxx');
const _email = SuppField('email', 'Email', 'email@example.com');

/// Danh mục 8 biểu mẫu.
const List<FormType> kFormTypes = [
  FormType(
    id: 'cccd_new',
    title: 'Đăng ký Căn cước công dân',
    desc: 'Cấp mới CCCD gắn chip',
    color: Color(0xFFDA251D),
    tint: Color(0xFFFDECEA),
    glyph: 'CC',
    supp: [_phone, _email, SuppField('job', 'Nghề nghiệp', 'VD: Kỹ sư')],
  ),
  FormType(
    id: 'cccd_re',
    title: 'Cấp đổi / Cấp lại CCCD',
    desc: 'Đổi thẻ hết hạn hoặc hư hỏng',
    color: Color(0xFF1656C4),
    tint: Color(0xFFEAF0FB),
    glyph: 'CĐ',
    supp: [_phone, SuppField('reason', 'Lý do cấp đổi', 'VD: Thẻ hết hạn')],
  ),
  FormType(
    id: 'thuongtru',
    title: 'Đăng ký thường trú',
    desc: 'Khai báo nơi cư trú lâu dài',
    color: Color(0xFF1656C4),
    tint: Color(0xFFEAF0FB),
    glyph: 'TT',
    supp: [
      _phone,
      SuppField('owner', 'Họ tên chủ hộ', 'VD: Trần Văn B'),
      SuppField('rel', 'Quan hệ với chủ hộ', 'VD: Con'),
    ],
  ),
  FormType(
    id: 'tamtru',
    title: 'Đăng ký tạm trú',
    desc: 'Khai báo lưu trú tạm thời',
    color: Color(0xFF0E9488),
    tint: Color(0xFFE1F5F2),
    glyph: 'Ta',
    supp: [
      _phone,
      SuppField('addr', 'Địa chỉ tạm trú', 'Số nhà, đường, phường...'),
      SuppField('dur', 'Thời hạn tạm trú', 'VD: 12 tháng'),
    ],
  ),
  FormType(
    id: 'eid',
    title: 'Xác thực định danh điện tử',
    desc: 'Định danh điện tử mức độ 2',
    color: Color(0xFF16A34A),
    tint: Color(0xFFE7F6ED),
    glyph: 'ĐT',
    supp: [_phone, _email],
  ),
  FormType(
    id: 'hochieu',
    title: 'Đăng ký cấp Hộ chiếu',
    desc: 'Cấp hộ chiếu phổ thông',
    color: Color(0xFF7C4DB8),
    tint: Color(0xFFF1EAFB),
    glyph: 'HC',
    supp: [_phone, _email, SuppField('purpose', 'Mục đích xuất cảnh', 'VD: Du lịch')],
  ),
  FormType(
    id: 'kethon',
    title: 'Đăng ký kết hôn',
    desc: 'Thủ tục đăng ký kết hôn',
    color: Color(0xFFDB2777),
    tint: Color(0xFFFCE7F1),
    glyph: 'KH',
    supp: [
      _phone,
      SuppField('pname', 'Họ tên vợ/chồng', 'Nhập họ tên'),
      SuppField('pid', 'Số CCCD vợ/chồng', '12 chữ số'),
    ],
  ),
  FormType(
    id: 'lltp',
    title: 'Cấp Phiếu lý lịch tư pháp',
    desc: 'Phiếu LLTP số 1 / số 2',
    color: Color(0xFFC2410C),
    tint: Color(0xFFFDEDE1),
    glyph: 'LT',
    supp: [_phone, _email, SuppField('purpose', 'Mục đích sử dụng', 'VD: Xin việc')],
  ),
];

FormType formTypeById(String id) =>
    kFormTypes.firstWhere((f) => f.id == id, orElse: () => kFormTypes.first);
=======
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
>>>>>>> 8593503 (add data)
