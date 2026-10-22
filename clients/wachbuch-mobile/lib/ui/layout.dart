/// Responsive breakpoints for phone vs. tablet layouts.
class AppLayout {
  const AppLayout._();

  static const double tabletBreakpoint = 720;
  static const double wideBreakpoint = 1100;

  static bool isTablet(double width) => width >= tabletBreakpoint;

  static bool isWide(double width) => width >= wideBreakpoint;

  /// Max content width for readable forms on large screens.
  static double contentMaxWidth(double width) {
    if (width >= wideBreakpoint) return 960;
    if (width >= tabletBreakpoint) return 720;
    return width;
  }

  /// Handover grid columns: 1 phone, 2 tablet, 3 wide.
  static int handoverColumns(double width) {
    if (width >= wideBreakpoint) return 3;
    if (width >= tabletBreakpoint) return 2;
    return 1;
  }
}
