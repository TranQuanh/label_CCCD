import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Trạng thái xác thực của ô nhập.
enum FieldStatus {
  /// Hợp lệ — viền xanh + dấu tích.
  valid,

  /// Cần kiểm tra / bắt buộc — viền cam + dấu chấm than.
  warning,

  /// Chưa nhập, chưa báo lỗi — viền xám.
  pending,
}

/// Ô nhập liệu có viền đổi màu theo trạng thái, luôn cho phép sửa tay.
class CustomTextField extends StatelessWidget {
  final String label;
  final TextEditingController controller;
  final FieldStatus status;
  final String statusText;
  final String? helper;
  final String? hint;
  final bool multiline;
  final bool mono;
  final TextInputType? keyboardType;

  const CustomTextField({
    super.key,
    required this.label,
    required this.controller,
    this.status = FieldStatus.valid,
    this.statusText = '',
    this.helper,
    this.hint,
    this.multiline = false,
    this.mono = false,
    this.keyboardType,
  });

  Color get _accent {
    switch (status) {
      case FieldStatus.valid:
        return AppColors.valid;
      case FieldStatus.warning:
        return AppColors.warn;
      case FieldStatus.pending:
        return AppColors.line;
    }
  }

  Color get _glow {
    switch (status) {
      case FieldStatus.valid:
        return AppColors.valid.withOpacity(.10);
      case FieldStatus.warning:
        return AppColors.warn.withOpacity(.12);
      case FieldStatus.pending:
        return Colors.transparent;
    }
  }

  Widget? get _suffix {
    switch (status) {
      case FieldStatus.valid:
        return const Icon(Icons.check_circle, color: AppColors.valid, size: 20);
      case FieldStatus.warning:
        return const Icon(Icons.error_outline, color: AppColors.warn, size: 20);
      case FieldStatus.pending:
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(AppRadius.field),
      borderSide: BorderSide(color: _accent, width: 1.5),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: const TextStyle(
                    fontSize: 12.5,
                    fontWeight: FontWeight.w600,
                    color: AppColors.inkSoft)),
            if (statusText.isNotEmpty)
              Text(statusText,
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: status == FieldStatus.pending
                          ? AppColors.hint
                          : _accent)),
          ],
        ),
        const SizedBox(height: 6),
        DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.field),
            boxShadow: [
              if (status != FieldStatus.pending)
                BoxShadow(color: _glow, blurRadius: 0, spreadRadius: 3),
            ],
          ),
          child: TextField(
            controller: controller,
            maxLines: multiline ? 3 : 1,
            minLines: multiline ? 2 : 1,
            keyboardType: keyboardType,
            style: TextStyle(
              fontSize: multiline ? 14.5 : 15.5,
              fontWeight: multiline ? FontWeight.w500 : FontWeight.w600,
              color: AppColors.ink,
              height: multiline ? 1.45 : null,
              fontFamily: mono ? 'monospace' : null,
            ),
            decoration: InputDecoration(
              isDense: true,
              hintText: hint,
              hintStyle: const TextStyle(
                  color: AppColors.hint, fontWeight: FontWeight.w400, fontSize: 14.5),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 14, vertical: 15),
              filled: true,
              fillColor: AppColors.card,
              suffixIcon: _suffix,
              suffixIconConstraints:
                  const BoxConstraints(minWidth: 42, minHeight: 20),
              enabledBorder: border,
              focusedBorder: border.copyWith(
                  borderSide: BorderSide(color: _accent, width: 2)),
            ),
          ),
        ),
        if (helper != null && helper!.isNotEmpty) ...[
          const SizedBox(height: 5),
          Text(helper!, style: TextStyle(fontSize: 11.5, color: _accent)),
        ],
      ],
    );
  }
}
