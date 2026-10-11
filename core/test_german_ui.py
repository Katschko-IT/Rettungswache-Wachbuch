"""German UI copy regression; identifiers and URL spellings stay ASCII."""
import re
from pathlib import Path
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from core.models import StationTask
from core.wachalltag_models import Defect, StationAsset, InventoryItem, ChecklistSchedule

class GermanUICopyTests(TestCase):
    def test_language_and_encoding_are_german(self):
        self.assertTrue(settings.USE_I18N)
        self.assertTrue(settings.LANGUAGE_CODE.startswith('de'))
        for name in ('login','privacy'):
            with self.subTest(route=name):
                response=self.client.get(reverse(name))
                self.assertEqual(response.status_code,200)
                self.assertContains(response,'lang="de"')
                self.assertContains(response,'charset="utf-8"')
                self.assertIn('charset=utf-8',response.headers['Content-Type'])

    def test_translated_choice_labels_keep_original_values(self):
        self.assertEqual(StationAsset.Kind.KEY.value,'key')
        self.assertEqual(StationAsset.Kind.KEY.label,'Schlüssel')
        self.assertEqual(StationAsset.Kind.DEVICE.value,'device')
        self.assertEqual(StationAsset.Kind.DEVICE.label,'Gerät')
        self.assertEqual(InventoryItem.Kind.KEY.label,'Schlüssel')
        self.assertIn('Gebäude',dict(Defect.Category.choices).values())
        self.assertIn('Täglich',dict(ChecklistSchedule.Interval.choices).values())
        self.assertIn('Täglich',dict(StationTask.Band.choices).values())

    def test_visible_template_copy_has_no_known_ascii_transliterations(self):
        # Exclude template expressions, comments, tags/URLs/identifiers entirely.
        bad=re.compile(r'\b(?:fuer|Fuer|Uebersicht|oeffentlich|zurueckgegeben|Uebergabe|Ungueltige|Schluessel|Gebaeude|Geraet|Taeglich)\b')
        for path in sorted((Path(settings.BASE_DIR)/'templates').rglob('*.html')):
            raw=path.read_text(encoding='utf-8')
            visible=re.sub(r'{%.*?%}|{{.*?}}|<!--.*?-->|<[^>]*>',' ',raw,flags=re.S)
            with self.subTest(template=str(path.relative_to(settings.BASE_DIR))):
                self.assertIsNone(bad.search(visible))

    def test_original_ascii_url_identifiers_are_preserved(self):
        self.assertEqual(reverse('handover_list'),'/uebergaben/')
        self.assertEqual(reverse('defects_web'),'/maengel/')
        self.assertEqual(reverse('station_member_keys'),'/chat/schluessel.json')
