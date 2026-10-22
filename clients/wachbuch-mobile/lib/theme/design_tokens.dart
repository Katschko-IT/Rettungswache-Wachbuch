import 'package:flutter/material.dart';

class WachbuchTokens {
  WachbuchTokens._();

  static const Color urgent = Color(0xFFDC2626);
  static const Color important = Color(0xFFF59E0B);
  static const Color normal = Color(0xFF2563EB);
  static const Color done = Color(0xFF16A34A);

  static const Color statusOpen = Color(0xFF2563EB);
  static const Color statusInProgress = Color(0xFFF59E0B);
  static const Color statusDone = Color(0xFF16A34A);

  static const Color error = Color(0xFFDC2626);
  static const Color success = Color(0xFF16A34A);
  static const Color warning = Color(0xFFF59E0B);
  static const Color info = Color(0xFF2563EB);

  static const Color surfaceLight = Color(0xFFF7F9FC);
  static const Color surfaceDark = Color(0xFF0B1220);
  static const Color primary = Color(0xFF0D47A1);
  static const Color brandDeep = Color(0xFF17343D);
  static const Color brandHover = Color(0xFF082E63);
  static const Color brandAccent = Color(0xFF2563EB);

  static const double spaceXs = 4;
  static const double spaceSm = 8;
  static const double spaceMd = 12;
  static const double spaceLg = 16;
  static const double spaceXl = 24;
  static const double space2Xl = 32;

  static const double touchTarget = 48;

  static const double textCaption = 12;
  static const double textBody = 14;
  static const double textTitle = 16;
  static const double textHeadline = 20;
  static const double textDisplay = 28;

  static const double radiusSm = 6;
  static const double radiusMd = 10;
  static const double radiusLg = 16;

  static Duration animFast = const Duration(milliseconds: 150);
  static Duration animNormal = const Duration(milliseconds: 300);

  static Color priorityColor(String priority) {
    return switch (priority) {
      'urgent' || 'high' => urgent,
      'important' || 'medium' => important,
      'done' || 'low' => done,
      _ => normal,
    };
  }

  static Color statusColor(String status) {
    return switch (status) {
      'open' || 'new' => statusOpen,
      'in_progress' || 'active' => statusInProgress,
      'waiting' || 'blocked' => important,
      'done' || 'closed' => statusDone,
      _ => normal,
    };
  }
}
