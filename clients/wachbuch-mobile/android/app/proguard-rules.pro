# Wachbuch Android release rules.
#
# Flutter and the included Android libraries ship their own consumer rules.
# Keep this file intentionally small so R8 can optimize aggressively and so
# missing library rules fail visibly during CI instead of being hidden by broad
# -keep or -dontwarn directives.

-keepattributes RuntimeVisibleAnnotations,RuntimeInvisibleAnnotations,AnnotationDefault
