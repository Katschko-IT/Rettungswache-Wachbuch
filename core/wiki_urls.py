from django.urls import path

from core import wiki_views

urlpatterns = [
    path("", wiki_views.wiki_index, name="wiki_index"),
    path("neu/", wiki_views.wiki_create, name="wiki_create"),
    path("<int:pk>/", wiki_views.wiki_detail, name="wiki_detail"),
    path("<int:pk>/bearbeiten/", wiki_views.wiki_edit, name="wiki_edit"),
    path("<int:pk>/archivieren/", wiki_views.wiki_archive, name="wiki_archive"),
    path("<int:pk>/wiederherstellen/", wiki_views.wiki_restore, name="wiki_restore"),
]

# Einbindung in core/urls.py:
# from django.urls import include, path
# path("wiki/", include("core.wiki_urls")),
