/// Dữ liệu một tấm CCCD sau khi trích xuất — dùng khắp luồng e-KYC.
///
/// Đây là model phía app (camelCase). Ánh xạ từ tên trường snake_case của
/// backend (`so_cccd`, `ho_va_ten`…) sang camelCase nằm trong `frontKeyMap` /
/// `backKeyMap` — phải đồng bộ với `FRONT_FIELDS`/`BACK_FIELDS` trong
/// `model/src/utils/cccd_schema.py`.
class IdCardData {
  String fullName;
  String idNumber;
  String dob;
  String sex;
  String nationality;
  String origin;
  String residence;
  String issueDate;
  String expiry;
  String issuePlace;
  String features;

  /// Id server của Profile CCCD (`tblCccdProfile.id`) — chỉ có khi thẻ này là
  /// một profile đã lưu trên server. KHÔNG nằm trong `toMap()`/`toServerJson()`
  /// (không phải dữ liệu thẻ); chỉ lưu vào cache máy qua `toLocalJson()`.
  String? profileId;

  IdCardData({
    this.fullName = '',
    this.idNumber = '',
    this.dob = '',
    this.sex = '',
    this.nationality = '',
    this.origin = '',
    this.residence = '',
    this.issueDate = '',
    this.expiry = '',
    this.issuePlace = '',
    this.features = '',
    this.profileId,
  });

  /// Kiểm tra dữ liệu thẻ có trống hay không.
  bool get isEmpty => fullName.trim().isEmpty && idNumber.trim().isEmpty;
  bool get isNotEmpty => !isEmpty;

  /// Bản sao độc lập — dùng để giữ bản gốc khi người dùng đang sửa.
  IdCardData clone() => IdCardData(
        fullName: fullName,
        idNumber: idNumber,
        dob: dob,
        sex: sex,
        nationality: nationality,
        origin: origin,
        residence: residence,
        issueDate: issueDate,
        expiry: expiry,
        issuePlace: issuePlace,
        features: features,
        profileId: profileId,
      );

  /// Điền giá trị từ một map key=camelCase.
  void applyMap(Map<String, String> m) {
    fullName = m['fullName'] ?? fullName;
    idNumber = m['idNumber'] ?? idNumber;
    dob = m['dob'] ?? dob;
    sex = m['sex'] ?? sex;
    nationality = m['nationality'] ?? nationality;
    origin = m['origin'] ?? origin;
    residence = m['residence'] ?? residence;
    issueDate = m['issueDate'] ?? issueDate;
    expiry = m['expiry'] ?? expiry;
    issuePlace = m['issuePlace'] ?? issuePlace;
    features = m['features'] ?? features;
  }

  /// Map key=camelCase — dùng để render PDF và đối chiếu.
  Map<String, String> toMap() => {
        'fullName': fullName,
        'idNumber': idNumber,
        'dob': dob,
        'sex': sex,
        'nationality': nationality,
        'origin': origin,
        'residence': residence,
        'issueDate': issueDate,
        'expiry': expiry,
        'issuePlace': issuePlace,
        'features': features,
      };

  Map<String, dynamic> toJson() => toMap();

  /// JSON lưu cache Profile CCCD trên máy: dữ liệu thẻ + `profileId` (nếu có).
  Map<String, dynamic> toLocalJson() => {
        ...toMap(),
        if (profileId != null) 'profileId': profileId,
      };

  /// Đọc lại từ cache máy (đối xứng với [toLocalJson]).
  factory IdCardData.fromLocalJson(Map<String, dynamic> json) {
    final id = json['profileId']?.toString();
    return IdCardData.fromJson(json)
      ..profileId = (id == null || id.isEmpty) ? null : id;
  }

  /// Map key=snake_case tiếng Việt — dùng khi GỬI lên server (đổi chiều của
  /// `frontKeyMap`/`backKeyMap`). Khớp FRONT_FIELDS/BACK_FIELDS cccd_schema.py.
  Map<String, dynamic> toServerJson() => {
        for (final e in toMap().entries)
          if (e.value.trim().isNotEmpty) _toServerKey(e.key): e.value.trim(),
      };

  static String _toServerKey(String camel) =>
      serverKeyMap[camel] ?? camel;

  /// Tái dựng IdCardData từ map snake_case server trả về (như lịch sử hồ sơ).
  /// Các key chưa biết được giữ nguyên (không thể rơi mất dữ liệu).
  factory IdCardData.fromServerJson(Map<String, dynamic> json) {
    final camel = <String, String>{};
    for (final e in json.entries) {
      final mapped = _fromServerKey(e.key);
      camel[mapped] = _s(e.value);
    }
    return IdCardData.fromJson(camel);
  }

  static String _fromServerKey(String snake) {
    if (frontKeyMap.containsKey(snake)) {
      return frontKeyMap[snake]!;
    }
    if (backKeyMap.containsKey(snake)) {
      return backKeyMap[snake]!;
    }
    return snake;
  }

  factory IdCardData.fromJson(Map<String, dynamic> json) => IdCardData(
        fullName: _s(json['fullName']),
        idNumber: _s(json['idNumber']),
        dob: _s(json['dob']),
        sex: _s(json['sex']),
        nationality: _s(json['nationality']),
        origin: _s(json['origin']),
        residence: _s(json['residence']),
        issueDate: _s(json['issueDate']),
        expiry: _s(json['expiry']),
        issuePlace: _s(json['issuePlace']),
        features: _s(json['features']),
      );

  static String _s(Object? v) => v == null ? '' : v.toString();

  /// Thứ tự + nhãn hiển thị dùng cho PDF và biểu mẫu hoàn chỉnh.
  /// Mỗi phần tử là [key-camelCase, nhãn tiếng Việt].
  static const displayOrder = <List<String>>[
    ['fullName', 'Họ và tên'],
    ['idNumber', 'Số CCCD'],
    ['dob', 'Ngày sinh'],
    ['sex', 'Giới tính'],
    ['nationality', 'Quốc tịch'],
    ['origin', 'Quê quán'],
    ['residence', 'Nơi thường trú'],
    ['issueDate', 'Ngày cấp'],
    ['expiry', 'Có giá trị đến'],
    ['issuePlace', 'Nơi cấp'],
    ['features', 'Đặc điểm nhận dạng'],
  ];
}

/// Ánh xạ tên trường backend (mặt trước) → key camelCase của app.
///
/// Khớp `FRONT_FIELDS` trong `cccd_schema.py`. Khi schema backend đổi, sửa cả
/// hai nơi.
const frontKeyMap = <String, String>{
  'so_cccd': 'idNumber',
  'ho_va_ten': 'fullName',
  'ngay_sinh': 'dob',
  'gioi_tinh': 'sex',
  'quoc_tich': 'nationality',
  'que_quan': 'origin',
  'noi_thuong_tru': 'residence',
  'co_gia_tri_den': 'expiry',
};

/// Ánh xạ tên trường backend (mặt sau) → key camelCase của app.
///
/// Khớp `BACK_FIELDS` trong `cccd_schema.py`.
const backKeyMap = <String, String>{
  'dac_diem_nhan_dang': 'features',
  'ngay_cap': 'issueDate',
  'noi_cap': 'issuePlace',
};

/// Ánh xạ ngược camelCase → snake_case server (cho `toServerJson()`).
/// Đổi chiều của `frontKeyMap` + `backKeyMap`; mọi key thẻ phải có mặt.
const serverKeyMap = <String, String>{
  'fullName': 'ho_va_ten',
  'idNumber': 'so_cccd',
  'dob': 'ngay_sinh',
  'sex': 'gioi_tinh',
  'nationality': 'quoc_tich',
  'origin': 'que_quan',
  'residence': 'noi_thuong_tru',
  'issueDate': 'ngay_cap',
  'expiry': 'co_gia_tri_den',
  'issuePlace': 'noi_cap',
  'features': 'dac_diem_nhan_dang',
};