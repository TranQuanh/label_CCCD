<<<<<<< HEAD
/// Dữ liệu trích xuất từ 2 mặt thẻ CCCD.
///
/// Tên trường trong app là camelCase tiếng Anh; backend trả snake_case tiếng Việt
/// (`so_cccd`, `ho_va_ten`, …) theo `model/src/utils/cccd_schema.py`. Toàn bộ ánh xạ
/// giữa hai bộ tên nằm gọn ở [frontKeyMap] / [backKeyMap] trong file này — đừng
/// hardcode tên trường backend ở bất kỳ chỗ nào khác.
=======
/// Dữ liệu một tấm CCCD sau khi trích xuất — dùng khắp luồng e-KYC.
///
/// Đây là model phía app (camelCase). Ánh xạ từ tên trường snake_case của
/// backend (`so_cccd`, `ho_va_ten`…) sang camelCase nằm trong `frontKeyMap` /
/// `backKeyMap` — phải đồng bộ với `FRONT_FIELDS`/`BACK_FIELDS` trong
/// `model/src/utils/cccd_schema.py`.
>>>>>>> 8593503 (add data)
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

<<<<<<< HEAD
=======
  /// Id profile trên server (tblCccdProfile.id) — chỉ dùng cho Profile CCCD,
  /// KHÔNG nằm trong toMap()/toServerJson() (các màn hình lặp toMap() để tạo ô
  /// nhập, PDF dùng displayOrder). Cache local dùng toLocalJson()/fromLocalJson().
  String? profileId;

>>>>>>> 8593503 (add data)
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
<<<<<<< HEAD
  });

  /// `so_cccd` → `idNumber`, … (8 trường mặt trước, bỏ `mat_the`).
  static const Map<String, String> frontKeyMap = {
    'so_cccd': 'idNumber',
    'ho_va_ten': 'fullName',
    'ngay_sinh': 'dob',
    'gioi_tinh': 'sex',
    'quoc_tich': 'nationality',
    'que_quan': 'origin',
    'noi_thuong_tru': 'residence',
    'co_gia_tri_den': 'expiry',
  };

  /// `dac_diem_nhan_dang` → `features`, … (3 trường mặt sau).
  static const Map<String, String> backKeyMap = {
    'dac_diem_nhan_dang': 'features',
    'ngay_cap': 'issueDate',
    'noi_cap': 'issuePlace',
  };

  /// Khoá app thuộc mặt trước / mặt sau — dùng để nhóm trường ở màn đối chiếu.
  static List<String> get frontKeys => frontKeyMap.values.toList();
  static List<String> get backKeys => backKeyMap.values.toList();

  factory IdCardData.fromJson(Map<String, dynamic> j) => IdCardData(
        fullName: _str(j['fullName']),
        idNumber: _str(j['idNumber']),
        dob: _str(j['dob']),
        sex: _str(j['sex']),
        nationality: _str(j['nationality']),
        origin: _str(j['origin']),
        residence: _str(j['residence']),
        issueDate: _str(j['issueDate']),
        expiry: _str(j['expiry']),
        issuePlace: _str(j['issuePlace']),
        features: _str(j['features']),
      );

  /// Nạp khối `data` của backend vào thẻ.
  ///
  /// Chỉ ghi đè các khoá thuộc đúng mặt đó, nên gọi lần lượt hai mặt là ghép được
  /// một thẻ đầy đủ mà không mặt nào xoá dữ liệu của mặt kia. Backend trả `null`
  /// cho trường không in trên thẻ (mẫu thẻ không có mục thường trú) — `null` được
  /// quy về chuỗi rỗng, đúng cách `metrics.normalize_text` chuẩn hoá khi chấm điểm.
  void applyBackendData(Map<String, dynamic> data, {required bool isFront}) {
    final map = isFront ? frontKeyMap : backKeyMap;
    final patch = <String, String>{};
    map.forEach((backendKey, appKey) {
      if (data.containsKey(backendKey)) {
        patch[appKey] = _str(data[backendKey]);
      }
    });
    applyMap(patch);
  }

  static String _str(Object? v) {
    if (v == null) return '';
    final s = v.toString().trim();
    // Backend có thể trả chuỗi "null"/"None" thay vì null thật.
    if (s.toLowerCase() == 'null' || s.toLowerCase() == 'none') return '';
    return s;
  }

=======
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

  /// JSON cho cache Profile CCCD trên máy: các trường thẻ + `profileId` (nếu có).
  Map<String, dynamic> toLocalJson() => {
        ...toMap(),
        if (profileId != null) 'profileId': profileId,
      };

  /// Đọc cache Profile CCCD trên máy (đọc được cả cache cũ không có `profileId`).
  factory IdCardData.fromLocalJson(Map<String, dynamic> json) {
    final id = json['profileId']?.toString();
    return IdCardData.fromJson(json)
      ..profileId = (id != null && id.isNotEmpty) ? id : null;
  }

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
>>>>>>> 8593503 (add data)
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

<<<<<<< HEAD
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

  IdCardData clone() => IdCardData.fromJson(toMap());

  /// Nhãn hiển thị theo thứ tự trên văn bản hành chính.
  static const List<List<String>> displayOrder = [
=======
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
>>>>>>> 8593503 (add data)
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
<<<<<<< HEAD

  /// Dữ liệu mẫu — CHỈ dùng khi `ApiConfig.useMock`.
  static IdCardData sample() => IdCardData(
        fullName: 'NGUYỄN VĂN AN',
        idNumber: '038204001234',
        dob: '12/05/1990',
        sex: 'Nam',
        nationality: 'Việt Nam',
        origin: 'Nam Định',
        residence: 'Số 25, đường Lê Lợi, P. Bến Nghé, Q.1, TP. Hồ Chí Minh',
        issueDate: '15/03/2021',
        expiry: '12/05/2030',
        issuePlace: 'CỤC TRƯỞNG CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI',
        features: 'Sẹo chấm C:1cm trên đuôi lông mày trái',
      );
}
=======
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
>>>>>>> 8593503 (add data)
