import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/form_type.dart';
import '../../data/session/session_store.dart';
import '../scan/onboarding_screen.dart';

/// Tab 1 — Danh mục biểu mẫu.
class FormsTab extends StatefulWidget {
  const FormsTab({super.key});

  @override
  State<FormsTab> createState() => _FormsTabState();
}

class _FormsTabState extends State<FormsTab> {
  @override
  void initState() {
    super.initState();
    sessionStore.loadForms();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: sessionStore,
      builder: (context, _) {
        final forms = sessionStore.forms;
        return Column(
          children: [
            _header(context),
            Expanded(
              child: forms.isEmpty && sessionStore.loadingForms
                  ? const Center(
                      child: CircularProgressIndicator(color: AppColors.navy))
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            const Text('Danh mục biểu mẫu',
                                style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w800,
                                    color: AppColors.ink)),
                            Text('${forms.length} biểu mẫu',
                                style: const TextStyle(
                                    fontSize: 12, color: AppColors.muted)),
                          ],
                        ),
                        const SizedBox(height: 14),
                        ...forms.map((f) => Padding(
                              padding: const EdgeInsets.only(bottom: 11),
                              child: _FormCard(form: f),
                            )),
                      ],
                    ),
            ),
          ],
        );
      },
    );
  }

  Widget _header(BuildContext context) => Container(
        width: double.infinity,
        color: AppColors.navy,
        padding: EdgeInsets.fromLTRB(
            24, MediaQuery.of(context).padding.top + 16, 24, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Xin chào,',
                        style:
                            TextStyle(fontSize: 13, color: AppColors.onNavy)),
                    const SizedBox(height: 2),
                    Text(sessionStore.displayName,
                        style: const TextStyle(
                            fontSize: 19,
                            fontWeight: FontWeight.w800,
                            color: Colors.white)),
                  ],
                ),
                Container(
                  width: 44,
                  height: 44,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white.withValues(alpha: .12),
                    border: Border.all(color: Colors.white24, width: 1.5),
                  ),
                  child: Text(sessionStore.initial,
                      style: const TextStyle(
                          color: Colors.white, fontWeight: FontWeight.w700)),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 15, vertical: 13),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: .08),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.white.withValues(alpha: .14)),
              ),
              child: Row(children: [
                Container(
                  width: 32,
                  height: 32,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: AppColors.star,
                    borderRadius: BorderRadius.circular(9),
                  ),
                  child: const Text('i',
                      style: TextStyle(
                          color: AppColors.navy,
                          fontWeight: FontWeight.w900,
                          fontSize: 15)),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Text(
                      'Chọn biểu mẫu để quét CCCD và điền tự động bằng AI.',
                      style: TextStyle(
                          fontSize: 12.5,
                          color: Color(0xFFDCE6FA),
                          height: 1.4)),
                ),
              ]),
            ),
          ],
        ),
      );
}

class _FormCard extends StatelessWidget {
  final FormType form;
  const _FormCard({required this.form});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(AppRadius.card),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute<void>(
            builder: (_) => OnboardingScreen(formType: form)),
      ),
      child: Container(
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppRadius.card),
          border: Border.all(
            color: AppColors.lineSoft,
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
                color: AppColors.navy.withValues(alpha: .05),
                blurRadius: 12,
                offset: const Offset(0, 5)),
          ],
        ),
        child: Row(children: [
          Container(
            width: 44,
            height: 44,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: form.tint,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(form.glyph,
                style: TextStyle(
                    color: form.color,
                    fontSize: 16,
                    fontWeight: FontWeight.w900)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(form.title,
                    style: const TextStyle(
                        fontSize: 14.5,
                        fontWeight: FontWeight.w700,
                        color: AppColors.ink)),
                const SizedBox(height: 2),
                Text(form.desc,
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.muted)),
              ],
            ),
          ),
          const Icon(Icons.chevron_right, color: Color(0xFFB0BBD2)),
        ]),
      ),
    );
  }
}