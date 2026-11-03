/// Thông tin tài khoản đăng nhập — đồng bộ với backend `/api/v1/auth/me`.
///
/// Không còn `dob` (bảng `tblUser` không có cột này); thêm `id` và `role` từ
/// server. Role chỉ có 2 giá trị: `user` (người dùng) và `admin` (quản trị viên).
class AuthUser {
  final String id;
  final String username;
  final String fullName;
  final String email;
  final String role;

  const AuthUser({
    required this.id,
    required this.username,
    required this.fullName,
    required this.email,
    required this.role,
  });

  bool get isAdmin => role == 'admin';

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
        id: json['user_id']?.toString() ?? '',
        username: json['username']?.toString() ?? '',
        fullName: json['full_name']?.toString() ?? '',
        email: json['email']?.toString() ?? '',
        role: json['role']?.toString() ?? 'user',
      );
}