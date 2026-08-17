import 'package:flutter/material.dart';

/// Nhãn nhóm trường: vạch màu + tiêu đề in hoa.
class SectionLabel extends StatelessWidget {
  final String text;
  final Color barColor;
  final Color textColor;
  const SectionLabel({
    super.key,
    required this.text,
    required this.barColor,
    required this.textColor,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 5,
          height: 16,
          decoration: BoxDecoration(
            color: barColor,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
        const SizedBox(width: 8),
        Text(
          text,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w800,
            color: textColor,
            letterSpacing: .2,
          ),
        ),
      ],
    );
  }
}
