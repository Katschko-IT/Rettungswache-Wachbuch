# Wachen-Wiki (H2)

Das Wachen-Wiki sammelt dauerhafte organisatorische Hinweise einer Rettungswache
(Übergabewege, Schlüsselregeln, Reinigungsabläufe). Es ist **kein** Kanal für
Patienten-, Einsatz- oder Personendaten.

## Modelle

| Modell | Zweck |
|---|---|
| `WikiArticle` | Aktueller Stand eines Hinweises, fest an genau eine `Station` gebunden (`station`, `slug`, `title`, `body`, `is_archived`, `current_revision_number`) |
| `WikiRevision` | Unveränderlicher Schnappschuss mit `number`, `title`, `body`, `edited_by`, `created_at`, `app_version` |

Der Slug wird beim Anlegen aus dem Titel erzeugt und bleibt danach stabil; er ist
pro Wache eindeutig (`unique_wiki_slug_per_station`). Ein Artikel kann seine
Wache nicht wechseln (`WikiArticle.clean`).

## Rollen und Sichtbarkeit

- Lesen: Mitglieder, Schichtleitung, Kassenwart und Master-Admin der eigenen Wache
  (`CONTENT_ROLES`). Die Auditor-Rolle hat keinen Zugriff.
- Schreiben/Archivieren: zunächst ausschließlich Master-Admin der eigenen Wache.
  Das ist der konservative, hier dokumentierte Default; eine eigene Wiki-Rolle
  wird nicht eingeführt.
- Jede Abfrage filtert auf `request.membership.station`. Fremde Artikel liefern
  `404`, nicht `403`, damit keine Existenz durchgesickert wird.
- Archivierte Artikel sind für Nicht-Admins unsichtbar (Liste und Detail).

## Revisionen und Nebenläufigkeit

- Jede inhaltliche Änderung erzeugt genau eine neue Revision (Nummer, Zeitpunkt,
  bearbeitende Person, Softwareversion). Revisionen können weder gespeichert
  noch gelöscht werden; `WikiRevision.save()`/`.delete()` blockieren das.
- Formulare tragen die erwartete Ausgangsrevision als Hidden-Feld.
  `update_article()` sperrt den Artikel (`select_for_update`) und vergleicht
  innerhalb der Transaktion. Bei Abweichung antwortet die View mit **HTTP 409**
  und zeigt die aktuelle Revision; die eigene Eingabe bleibt im Formular erhalten
  und wird mit der aktuellen Revisionsnummer erneut angeboten. Ein stilles
  Überschreiben gibt es nicht.
- Archivieren/Wiederherstellen erzeugt keine Inhaltsrevision, wird aber als
  `wiki.article_archived` bzw. `wiki.article_restored` auditiert. Alte Revisionen
  bleiben vollständig erhalten.

## Ausgabe und Suche

- Titel und Text werden als reiner Text gespeichert und in Templates automatisch
  escaped (`linebreaksbr`, kein `|safe`, kein Markdown-Renderer).
- Die Suche prüft Titel und Text. ASCII-Begriffe nutzt den Datenbankfilter;
  Begriffe mit Umlauten werden portabel in Python per `casefold` verglichen, weil
  SQLite `LIKE` nur ASCII faltet. Die Menge ist auf die Artikel der eigenen Wache
  begrenzt; die Liste ist auf 20 Einträge pro Seite paginiert.

## Bedienung

- Einstieg: „Mehr“ → „Wachen-Wiki“ (`/wiki/`).
- Anlegen: `/wiki/neu/`; Bearbeiten: `/wiki/<id>/bearbeiten/`;
  Archivieren/Wiederherstellen als POST mit CSRF-Token.

## Tests

`core/test_wiki.py` deckt anonymen Zugriff, Rollen, Wachentrennung, XSS/escaping,
CSRF, Revisionsunveränderlichkeit, Konflikt/409, Archivierung, Suche mit Umlauten
und Pagination ab.
