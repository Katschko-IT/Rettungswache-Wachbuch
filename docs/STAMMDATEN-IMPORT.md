# Stammdaten-Import (CSV)

Stand: 0.27 (ROADMAP 0.27, Baustein 7). Dieser Teil umfasst **Lagerorte, Artikel,
Bestand (Altbestand) und Medizingeräte**. Fahrzeuge und Einladungen folgen in
einem eigenen Schritt.

Der Import ist für die Einrichtung einer Wache gedacht: Listen, die es schon in
Excel gibt, werden einmal übernommen. Danach wird in Wachwerk gepflegt.

- **Wer:** nur Master-Admins (Rolle `admin`) der eigenen Wache.
- **Wo:** „Mehr“ → „Stammdaten importieren“ (`/einstellungen/import/`).
- **Code:** `core/masterdata_import.py` (Prüfen und Importieren),
  `core/masterdata_import_views.py` (Ansichten), Tests in
  `core/test_masterdata_import.py`.

## Ablauf

1. **Vorlage herunterladen** (je Art). Die Vorlage ist eine CSV-Datei mit
   UTF-8-BOM, Trennzeichen `;`, der Überschriftenzeile und einer Beispielzeile,
   die mit `# Beispiel` beginnt. Zeilen, die mit `#` beginnen, und leere Zeilen
   werden immer übersprungen.
2. **Ausfüllen** in Excel oder LibreOffice. Speichern mit „Speichern unter“ →
   „CSV UTF-8 (durch Trennzeichen getrennt)“.
3. **Datei prüfen** (Trockenlauf). Wachwerk prüft jede Zeile, führt den Import
   in einer Transaktion aus und rollt sie wieder zurück. Die Vorschau zeigt je
   Zeile „Neu“, „Bereits vorhanden – wird übersprungen“ oder „Fehler“, dazu
   Hinweise.
4. **Jetzt importieren.** Wachwerk prüft die Datei erneut und legt alle Zeilen in
   einer Transaktion an. Enthält die Datei einen Fehler, wird nichts angelegt
   (alles oder nichts). Hat sich seit der Vorschau etwas geändert (z. B. hat
   jemand denselben Artikel angelegt), wird ebenfalls nichts angelegt; die neue
   Vorschau erscheint und muss erneut bestätigt werden.

**Reihenfolge:** Lagerorte → Artikel → Bestand → Medizingeräte.

**Wichtig für das Lager:** Öffnet jemand `/lager/` auf einer Wache ohne
Lagerorte, legt Wachwerk drei Beispiel-Lagerorte an („Zentrallager / Apotheke“,
„Medikamentenkühlschrank“, „RTW 01/83-01 Schrank“). Diese lassen sich heute nicht
löschen. Deshalb die Lagerorte importieren, **bevor** das Lager zum ersten Mal
geöffnet wird. Hat die Wache nach einem Artikel- oder Bestandsimport noch keine
Lagerorte, bietet die Ergebnisseite statt „Zum Lager“ „Weiter mit: Lagerorte“
an.

## Grundsätze

- **Nur anlegen, nie ändern.** Vorhandene Einträge werden am natürlichen
  Schlüssel erkannt und übersprungen (siehe unten). Ein zweiter Import derselben
  Datei ändert nichts. Korrekturen gehen über die Bearbeiten-Formulare
  (Artikel, Medizingerät).
- **Lagerorte lassen sich nach dem Import nicht bearbeiten oder löschen**; es
  gibt dafür noch keine Oberfläche. Die Lagerort-Datei deshalb vor dem Import
  genau prüfen (offener Punkt, siehe „Nicht enthalten“).
- **Alles oder nichts.** Ein Fehler in einer Zeile verhindert den ganzen Import.
  Hinweise verhindern nichts.
- **Nur die eigene Wache.** Artikel, Lagerorte und übergeordnete Lagerorte
  werden nur innerhalb der eigenen Wache gefunden.
- **Produktgrenze.** Status, Zustände, Füllstände, Funktionskontrollen,
  Prüfprotokolle, Einweisungen und freie Notizen werden nie übernommen.

## Excel-Hinweise

- PZN, GTIN und Inventarnummern als **Text** formatieren. Fehlende führende
  Nullen bei der PZN ergänzt Wachwerk; eine von Excel gekürzte Zahl
  (`4,01E+12`) wird mit Hinweis abgelehnt.
- Zeichenkodierung: UTF-8 (mit oder ohne BOM) oder Windows-1252. UTF-16
  („Unicode-Text“) und .xlsx-Dateien werden mit Hinweis abgelehnt.
- Trennzeichen: `;` oder `,` (automatisch erkannt). Eine erste Zeile `sep=;`
  wird beachtet.
- Datum: `TT.MM.JJJJ`, `T.M.JJJJ`, `TT.MM.JJ` (wird zu 20JJ) oder `JJJJ-MM-TT`.
  Bei MHD und den Prüfterminen (Nächste STK/MTK/DGUV V3) auch `MM/JJJJ`,
  `MM.JJJJ` oder `JJJJ-MM`; das gilt dann als Monatsende, so wie es auf
  Prüfplaketten steht.
- Ja/Nein: `Ja`, `J`, `X`, `1`, `wahr` bzw. `Nein`, `N`, `0`, `falsch`.
- Ein einzelnes `-`, `–` oder `—` gilt als leer.
- Werte, die mit `=`, `+`, `-`, `@` oder einem Tabulator beginnen, werden
  abgelehnt (Schutz vor Formeln, die später über Exporte in Tabellenprogramme
  gelangen würden).
- Die Überschriften sind ein festes deutsches Datenformat und werden nicht
  übersetzt. Groß-/Kleinschreibung, ein `*` am Ende und `ae`/`ue` statt
  Umlauten sind egal. Die Exporte von Wachwerk (FEFO-Liste, Bestellschein,
  Bestandsverzeichnis) werden direkt erkannt. Unbekannte Spalten werden
  angezeigt und ignoriert.
- Auswahlwerte (Kategorie, Einheit, Risikoklasse …) werden als Code oder als
  deutsche Bezeichnung erkannt, auch wenn die Oberfläche auf Englisch steht.

## Arten und Spalten

Pflichtspalten sind mit * markiert. Die vollständige Beschreibung jeder Spalte
mit erlaubten Werten steht in Wachwerk auf der Seite der jeweiligen Art.

### Lagerorte (`lagerorte`)

| Spalte | Bedeutung |
|---|---|
| Lagerort* | Bezeichnung, z. B. „Fach 3“. Ohne „→“ und „>“. |
| Art | Hauptlager / Apotheke, Fahrzeug / RTW / KTW, Koffer / Rucksack, Medikamentenkühlschrank, Sonstiger Lagerort (Standard). Kurzformen wie „RTW“, „Kühlschrank“ gehen auch. |
| Kühlung | Ja/Nein. Leer: Ja nur beim Kühlschrank. |
| Übergeordneter Lagerort | Name oder Pfad eines vorhandenen Lagerorts oder einer Zeile der Datei, z. B. `RTW 1 → Schrank links` (auch `RTW 1 > Schrank links`). Die Reihenfolge der Zeilen ist egal. |
| Beschreibung | höchstens 255 Zeichen |

Schlüssel: der volle Pfad (z. B. `RTW 1 → Schrank links → Fach 3`). Ein Name, der
mehrfach vorkommt, muss als Pfad angegeben werden. Kreise und Selbstbezug sind
Fehler.

So werden Namen und Pfade gelesen (hier und in der Spalte „Lagerort“ beim
Bestand):

- Gibt es einen Lagerort mit **genau diesem vollständigen Pfad**, ist er gemeint.
  `Kühlschrank` ist also der Kühlschrank auf oberster Ebene, auch wenn es
  `RTW 1 → Kühlschrank` gibt. Die Vorschau zeigt dann einen Hinweis; für den
  Kühlschrank im RTW den ganzen Pfad `RTW 1 → Kühlschrank` schreiben.
- Sonst genügt das Ende des Pfads, wenn es nur einen solchen Lagerort gibt
  (`Fach 3` oder `Schrank links → Fach 3`). Passen mehrere, ist das ein Fehler
  „mehrdeutig“ mit einem Beispielpfad.

### Artikel (`artikel`)

| Spalte | Bedeutung |
|---|---|
| Artikel* | Bezeichnung (auch `Artikelbezeichnung`) |
| Kategorie | Leer: Sonstiges Material |
| Einheit | Leer: Stück; auch `Stk`, `Amp`, `Pck` |
| PZN | mit Prüfziffer; führende Nullen werden ergänzt |
| GTIN | 8, 12, 13 oder 14 Ziffern mit Prüfziffer (auch `GTIN / EAN`, `EAN`) |
| Mindestbestand | Leer: 0 (nicht 5, sonst stünden alle Artikel auf der Nachbestellliste) |
| Sollbestand | Leer: wie Mindestbestand |
| Kühlpflichtig | Leer: Nein |
| Max. Tage bei Raumtemperatur | nur bei kühlpflichtigen Artikeln |

Schlüssel: PZN, sonst GTIN, sonst die Bezeichnung. PZN und GTIN werden auf
beiden Seiten nur als Ziffern verglichen (PZN auf 8, GTIN auf 14 Stellen
aufgefüllt). Ein vorhandener Artikel gleichen Namens ohne PZN/GTIN wird mit
Hinweis übersprungen. Doppelte Zeilen mit gleichen Angaben werden
zusammengefasst, widersprüchliche sind ein Fehler. Spalten der FEFO-Liste
(Charge, MHD, Lagerort, Bestand …) werden mit dem Hinweis „Bestand bitte über
‚Bestand (Altbestand)‘ übernehmen“ ignoriert.

### Bestand (Altbestand) (`bestand`)

Eine Zeile je Charge und Lagerort. Artikel und Lagerorte müssen schon angelegt
sein. **Betäubungsmittel gehören nicht hierher**; ihr Bestand bleibt im
BtM-Buch.

| Spalte | Bedeutung |
|---|---|
| Artikel / PZN / GTIN | mindestens eine Spalte; PZN hat Vorrang, dann GTIN, dann die eindeutige Bezeichnung |
| Charge (Lot)* | wie auf der Packung |
| Hersteller-MHD* | aufgedrucktes MHD; `05/2027` = 31.05.2027 |
| Out-of-Fridge Datum | nur bei kühlpflichtigen Artikeln |
| Lagerort* | Name oder Pfad eines vorhandenen Lagerorts (gelesen wie bei den Lagerorten beschrieben) |
| Bestand* | Menge; 0 wird mit Hinweis übersprungen |
| Einheit | nur zum Abgleich, Abweichung ist ein Hinweis |
| Status / Rückruf | „Gesperrt …“ ist ein Fehler; gesperrte Chargen werden nicht übernommen |

Jede Zeile wird als Buchung „**Übernahme Altbestand**“ (Buchungsart `legacy`)
ins Lagerjournal geschrieben; die Notiz `CSV-Import <Prüfsumme>` verbindet sie
mit dem Audit-Eintrag. Eine vorhandene Charge mit anderem MHD oder mit Rückruf
ist ein Fehler; eine Charge, die am Lagerort schon Bestand hat, wird
übersprungen.

Rundweg aus einer anderen Wachwerk-Installation: die FEFO-Liste zweimal
importieren, zuerst als „Artikel“, dann als „Bestand“. Die FEFO-Liste enthält
nur den Namen des Lagerorts; kommen Namen mehrfach vor (z. B. „Fach 3“ in zwei
Fahrzeugen), die Spalte vorher auf Pfade (`RTW 1 → Fach 3`) ändern.

### Medizingeräte (`medizingeraete`)

| Spalte | Bedeutung |
|---|---|
| Gerätebezeichnung* | auch `Bezeichnung`, `Gerät` |
| Kategorie | Leer: Sonstiges aktives Medizinprodukt |
| Risikoklasse* | I, IIa, IIb oder III (auch „Klasse IIb“). Pflicht, wird nicht geraten. |
| Hersteller, Typ / Modell | |
| Seriennummer, Inventarnummer | mindestens eine von beiden (§ 14 MPBetreibV) |
| UDI-DI (GTIN), CE-Kennnummer | CE-Kennnummern mit weniger als 4 Ziffern werden aufgefüllt (`123` → `0123`) |
| Baujahr, Anschaffungsdatum | |
| Standort / Fahrzeug | Leer: Wache |
| Anlage 1 (STK) | Leer: Ja |
| Anlage 2 (MTK) | Leer: Nein; bei Ja ist das MTK-Intervall Pflicht |
| STK-, MTK-, DGUV-Intervall (M) | Monate; Leer: 24 bzw. 12 |
| Nächste STK, Nächste MTK, Nächste DGUV V3 | Datum von der Prüfplakette |
| Status | wird **nicht** übernommen (siehe unten) |

Schlüssel: gleiche Inventarnummer oder gleiche Seriennummer beim gleichen
Hersteller, auch bei außer Betrieb genommenen Geräten. Ein solches Gerät bleibt
außer Betrieb genommen (Hinweis in der Vorschau); ein Import nimmt nie ein Gerät
wieder in Betrieb (`core/evidence.py`).

**Status in der Datei** (z. B. aus dem Bestandsverzeichnis):

- „Einsatzklar“ oder leer: wird importiert.
- „Eingeschränkt“: wird importiert, mit Hinweis.
- „Gesperrt“ (bis 0.26 „Außer Betrieb (Gesperrt)“), „In Wartung / STK“: **Fehler**. Ein Gerät, das
  auf Papier gesperrt ist, darf nicht als einsatzklar erscheinen. Die Zeile
  entfernen, das Gerät einzeln anlegen und über „Mangel melden“ sperren.
- „Außer Betrieb genommen“ (auch „Ausgemustert“): wird übersprungen. Die übrigen
  Zellen dieser Zeile werden nicht geprüft; eine fehlende Serien- oder
  Inventarnummer verhindert den Import dann nicht.

Spalten wie „Letzte STK“ oder „Letzte Funktionskontrolle“ werden ignoriert:
Bitte die nächste Fälligkeit von der Prüfplakette übernehmen. Die Spalte
„Außerbetriebnahme“ aus dem Bestandsverzeichnis wird ebenfalls ignoriert.

## Altbestand-Kennzeichnung

- **Lager:** Buchungsart „Übernahme Altbestand“ im Lagerjournal
  (`StockMovement.Kind.LEGACY_IMPORT`, append-only wie alle Buchungen).
- **Medizingeräte:** Feld `MedicalDevice.legacy_imported_at` („Aus Altbestand
  übernommen am“), nicht bearbeitbar. Die Geräteseite zeigt einen Hinweis
  („Frühere Prüfungen und Einweisungen sind in den Papierunterlagen
  dokumentiert.“) und neben Nächste STK/MTK/DGUV V3 das Kennzeichen
  „Altbestand“, bis eine bestandene Prüfung dieser Art mit neuer Frist in
  Wachwerk eingetragen ist. Das Bestandsverzeichnis (CSV) hat dafür die Spalte
  „Aus Altbestand übernommen am“.
- Es entstehen **keine rückdatierten Einträge** im Medizinproduktebuch und keine
  Einweisungen. Ein erfundenes „Bestanden“ wäre eine Falschaussage.
- Hinweis zur Einweisungspflicht: Importierte Geräte haben noch keine
  Einweisungen in Wachwerk. Die Einweisungen liegen auf Papier und werden nach
  dem Import nachgetragen (Pilot-Einrichtungsschritt).

## Grenzen

| Grenze | Wert |
|---|---|
| Dateigröße | 1 MB |
| Datenzeilen | 2000 je Datei |
| Spalten | 50 |
| Zeichen je Zelle | 1000 (zusätzlich die Feldlänge) |
| Gültigkeit der Vorschau | 1 Stunde |

## Datenschutz

- Wachwerk speichert die Datei nicht: weder in der Datenbank noch in der
  Sitzung noch in einem Dateiverzeichnis, also auch nicht in Backups. Dateien
  bis 1 MB liest der Server nur im Arbeitsspeicher. Größere Dateien werden
  abgewiesen; ab 2,5 MB legt Django den Upload vor der Ablehnung kurz in einer
  temporären Datei ab (im Container auf tmpfs) und löscht sie am Ende der
  Anfrage. Der vorgeschaltete Proxy (nginx) puffert große Anfragen und Antworten
  ebenfalls kurz in Zwischendateien und verwirft sie nach der Anfrage.
- Die Vorschau trägt den Dateiinhalt als Base64 im Formular zurück, zusammen mit
  der SHA-256-Prüfsumme und einem signierten Token (Wache, Person, Art,
  Prüfsumme, Vorschau-Ergebnis; 1 Stunde gültig). Vorschau und Ergebnis werden
  mit `Cache-Control: no-store` ausgeliefert.
- Im Audit-Log steht je Import genau ein Eintrag (`import.storage_locations`,
  `import.articles`, `import.stock`, `import.medical_devices`) mit Art, Anzahl
  (Zeilen, neu, übersprungen, Hinweise), Zeichenkodierung, Trennzeichen und
  SHA-256 der Datei. Keine Zellwerte, kein Dateiname. Der Trockenlauf schreibt
  nichts.
- Personenbezug: Die Arten dieses Teils enthalten keine Personendaten. Das
  Lagerjournal nennt wie jede Buchung die importierende Person.

## Demo

In der öffentlichen Demo sind Übersicht und Vorlagen sichtbar. Prüfen und
Importieren sind gesperrt.

## Meldungen und Abhilfe

| Meldung | Abhilfe |
|---|---|
| „Die Datei ist in UTF-16 gespeichert …“ | In Excel „CSV UTF-8 (durch Trennzeichen getrennt)“ wählen |
| „Das ist eine Excel-Datei …“ | Als CSV speichern, nicht als .xlsx |
| „Die Zahl wurde vom Tabellenprogramm gekürzt …“ | Spalte als Text formatieren, Werte neu eintragen |
| „… ist ungültig (Prüfziffer)“ | PZN/GTIN von der Packung prüfen |
| „… ist mehrdeutig. Bitte als Pfad angeben …“ | den ganzen Pfad schreiben, z. B. `RTW 1 → Fach 3` |
| „… steht für den Lagerort mit genau diesem Pfad …“ (Hinweis) | Passt so, wenn der Lagerort auf oberster Ebene gemeint ist; sonst den ganzen Pfad schreiben |
| „Pflichtspalte fehlt: …“ | Überschrift aus der Vorlage übernehmen |
| „Die Vorschau ist abgelaufen …“ | Datei erneut prüfen |
| „Seit der Prüfung hat sich der Datenbestand geändert …“ | Neue Vorschau ansehen und erneut bestätigen |

## Messbares Ziel (ROADMAP 0.27)

„300 Artikel und 40 Medizingeräte in unter 30 Minuten importiert.“

- **Serverseite (automatisiert belegt):** `ImportPerformanceTests` prüft 300
  Artikel, 40 Geräte und 300 Bestandszeilen mit festen Abfragebudgets
  (Artikel ≤ Zeilen + 20, Geräte ≤ 2 × Zeilen + 20, Bestand ≤ 3 × Zeilen + 20).
  Prüfen und Importieren dauern zusammen wenige Sekunden.
- **Menschlicher Teil (offen):** Das Ausfüllen der Vorlagen wird einmal in einer
  moderierten Probe mit der Pilotwache gemessen und hier eingetragen. Gemessen
  wird nur im Test, nicht im Betrieb (keine Messung je Person).

## Nicht enthalten

- Fahrzeuge und Einladungen (folgender Schritt).
- Bearbeiten und Löschen von Lagerorten in der Oberfläche.
- Aktualisieren vorhandener Einträge per Import, XLSX-Import (nur nach ADR),
  englische Spaltennamen, Import von Einweisungen, Prüfprotokollen oder
  Desinfektionsmitteln.
- Ein Befehl für die Kommandozeile.
- Formelschutz in den bestehenden Exporten (eigener Schritt).
