/// Dữ liệu trích xuất từ 2 mặt thẻ CCCD.
///
/// Tên trường trong app là camelCase tiếng Anh; backend trả snake_case tiếng Việt
/// (`so_cccd`, `ho_va_ten`, …) theo `model/src/utils/cccd_schema.py`. Toàn bộ ánh xạ
/// giữa hai bộ tên nằm gọn ở [frontKeyMap] / [backKeyMap] trong file này — đừng
/// hardcode tên trường backend ở bất kỳ chỗ nào khác.
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
