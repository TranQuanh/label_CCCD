import 'package:flutter/material.dart';

/// Một trường người dùng phải nhập tay (AI không đọc được từ thẻ).
class SuppField {
  final String key;
  final String label;
  final String hint;
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

  const FormType({
    required this.id,
    required this.title,
    required this.desc,
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
