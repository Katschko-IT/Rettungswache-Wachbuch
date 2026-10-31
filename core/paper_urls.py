from django.urls import path

from core import paper_views

# Eingebunden in core/urls.py unter "papier/". Bewusst nicht in
# core.terminal.OPEN_MODE_PATHS: Das Wachenterminal erreicht keine Druckansicht.
urlpatterns = [
    path("", paper_views.paper_hub, name="paper_hub"),
    path("fristen/", paper_views.paper_deadlines, name="paper_deadlines"),
    path("telefonbuch/", paper_views.paper_phonebook, name="paper_phonebook"),
    path("checklisten/", paper_views.paper_checklists, name="paper_checklists"),
    path("fahrzeuguebernahme/", paper_views.paper_vehicle_handover, name="paper_vehicle_handover"),
    path("desinfektion/", paper_views.paper_disinfection, name="paper_disinfection"),
    path("funktionskontrolle/", paper_views.paper_device_checks, name="paper_device_checks"),
]
