# Vorlage: Vereinbarung mit der Interessenvertretung

Stand: 31. Oktober 2026 · gilt für Wachwerk 0.27

> **Keine Rechtsberatung und kein fertiger Vertragstext.** Diese Vorlage
> sammelt Bausteine für eine Betriebs- oder Dienstvereinbarung über den
> Einsatz von Wachwerk. Paragraphen sind mit **[prüfen]** markiert und müssen
> am amtlichen Text und an der für den Träger geltenden Fassung geprüft
> werden. Datenschutzbeauftragte und Interessenvertretung werden von Anfang
> an beteiligt.

Wachwerk ist eine technische Einrichtung, mit der sich Verhalten oder
Leistung überwachen ließen (Anmeldungen, Zeitstempel, Namen an erledigten
Aufgaben). Deshalb braucht der Pilot eine Vereinbarung, bevor echte Daten
erfasst werden (Startkriterium in `ROADMAP.md`).

## 1. Welche Variante gilt?

| Trägerart (Beispiele) | Datenschutzrecht | Aufsicht | Interessenvertretung | Vereinbarung | Beteiligung (Anknüpfung) |
| --- | --- | --- | --- | --- | --- |
| Verein, gGmbH oder anderer privater Träger (z. B. DRK, ASB [prüfen]) | DSGVO und BDSG | Datenschutzaufsicht des Landes am Sitz des Trägers | Betriebsrat | Betriebsvereinbarung, § 77 BetrVG [prüfen] | § 87 Abs. 1 Nr. 6 BetrVG, ggf. Nr. 1 und 7; Unterrichtung nach § 90 BetrVG [prüfen] |
| Kommune, Kreis, Zweckverband (Berufsfeuerwehr, kommunaler Rettungsdienst) | DSGVO und Landesdatenschutzgesetz | Landesbeauftragte/r für den Datenschutz | Personalrat | Dienstvereinbarung | Personalvertretungsgesetz des Landes, z. B. LPVG NRW § 72 Abs. 3 [prüfen]; beim Bund § 80 Abs. 1 Nr. 21 BPersVG [prüfen] |
| Katholischer Träger (z. B. Malteser [prüfen]) | KDG (Gesetz über den Kirchlichen Datenschutz) | Datenschutzaufsicht des Bistums, z. B. ein Katholisches Datenschutzzentrum | Mitarbeitervertretung (MAV) | Dienstvereinbarung nach MAVO [prüfen] | Zustimmung bei technischen Einrichtungen nach MAVO [prüfen]; das BetrVG gilt nicht (§ 118 Abs. 2 BetrVG) |
| Evangelischer Träger (z. B. Johanniter, Diakonie [prüfen]) | DSG-EKD (Datenschutzgesetz der EKD) | in der Regel der Beauftragte für den Datenschutz der EKD (BfD EKD); einige Landeskirchen haben eine eigene Aufsicht | Mitarbeitervertretung (MAV) | Dienstvereinbarung nach MVG-EKD [prüfen] | Mitbestimmung bei technischen Einrichtungen, § 40 MVG-EKD [prüfen]; das BetrVG gilt nicht (§ 118 Abs. 2 BetrVG) |
| Kommunale GmbH oder andere privatrechtliche Form in öffentlicher Hand | mit der oder dem DSB klären (DSGVO mit BDSG oder Landesrecht) | je nach Datenschutzrecht | Betriebsrat | Betriebsvereinbarung | wie beim privaten Träger [prüfen] |

Kirchliche Träger dürfen nach Art. 91 DSGVO eigenes Datenschutzrecht
anwenden. Rechte der Beschäftigten, Beschwerdestelle und Fristen richten sich
dann nach KDG bzw. DSG-EKD [prüfen].

## 2. Bausteine

Jeder Baustein hat zwei Teile: **Wachwerk-Fakten** (was das System heute tut;
belegt im Datenkatalog) und **zu regeln** (was die Vereinbarung festlegt).

### 2.1 Gegenstand und Geltungsbereich

Wachwerk-Fakten:

- Wachwerk organisiert interne Abläufe der Wache. Es speichert keine Patienten-, Einsatz-, Alarmierungs-, Gesundheits- oder Leistungsdaten.
- Welche Module eingeschaltet sind, zeigt der Datenkatalog der Wache (Anlage 1).

Zu regeln:

- Wache(n) und Personenkreis: `[ausfüllen]`
- Pilotzeitraum: 12 Wochen ab `[Datum]`, danach Entscheidung über Weiterbetrieb
- eingeschaltete Module: laut Anlage 1; weitere Module nur nach Unterrichtung (Baustein 2.7)

### 2.2 Zweck und Produktgrenze

Wachwerk-Fakten:

- Zwecke je Modul stehen im Datenkatalog.
- Das System hat keine Felder für Patienten- oder Einsatzangaben; Übergabe- und Desinfektionsformular weisen darauf hin, solche Angaben nicht einzutragen.

Zu regeln:

- abschließende Liste der Zwecke: `[ausfüllen]`
- Verbot, Patienten-, Einsatz- oder Gesundheitsdaten in Freitexte oder Fotos zu schreiben
- Vorgehen, wenn trotzdem solche Daten eingetragen wurden (Meldung, Löschung): `[ausfüllen]`

### 2.3 Keine Leistungs- und Verhaltenskontrolle

Wachwerk-Fakten (Spalte „Auswertungen mit Personenbezug“ im Datenkatalog):

- Lesebestätigungen von Übergaben zeigen **Name und Uhrzeit**; sichtbar für alle Inhaltsrollen und am Wachenterminal.
- Erledigte Tagesaufgaben und Checklisten zeigen im Web den **Vornamen** und die Uhrzeit; sichtbar für alle Inhaltsrollen und am Wachenterminal. Die App zeigt beim letzten Abschluss einer Checkliste den **vollen Namen**.
- Die Einweisungsmatrix (Gerätepass) zeigt für jedes Mitglied, für welche Geräte eine Einweisung vorliegt, und eine **Quote je Person**; sichtbar für alle Inhaltsrollen.
- Verläufe in Mängeln, Geräteausgabe, Medizinprodukten, Lager, Fuhrpark und Wiki nennen die handelnde Person; die Mängelliste nennt die zuständige Person. Die App zeigt bei Mängeln den Benutzernamen.
- Lesequittungen von Dienstanweisungen mit Namen sehen nur Schichtleitung und Master-Admin (auch als CSV).
- Desinfektionen zeigen allen Inhaltsrollen Datum, Mittel und die durchführende Person; Stufe, Einwirkzeit und Bemerkung sehen nur die durchführende Person, Schichtleitung und Master-Admin (Entscheidung D2).
- Stände und Buchungen der Kaffeekasse aller Teilnehmenden sieht nur der Kassenwart (Web und App, in der App mit vollem Namen).
- Das Audit-Protokoll (Person, Zeit, Aktion, geänderte Felder) sehen Auditor und Master-Admin; es enthält keine fachlichen Freitexte.
- Neuigkeiten zeigen den Lesestand nur als Zahl („3 von 8 haben gelesen“).
- Fast jeder Eintrag hat einen Zeitstempel.
- Es gibt keine Ranglisten, keine Dauer je Person und keine Aktivitätsquote.

Zu regeln:

- Die Liste der Auswertungen in Anlage 1 ist **abschließend**. Neue Auswertungen nur nach Zustimmung.
- Kein Abgleich von Zeitstempeln mit Arbeitszeit oder Dienstplan.
- **Verwertungsverbot:** Daten aus Wachwerk werden nicht für arbeitsrechtliche Maßnahmen gegen einzelne Beschäftigte genutzt. Ausnahmen (z. B. begründeter Verdacht einer Straftat) nur nach Beteiligung der Interessenvertretung: `[ausfüllen]`
- ob die Sichtbarkeit der Namen (Lesebestätigungen, erledigte Aufgaben, Gerätepass) so bleibt: `[entscheiden]`

### 2.4 Rollen und Zugriffe

Wachwerk-Fakten:

- Rollen je Wache: Mitglied, Schichtleitung, Kassenwart, Master-Admin, Auditor (Anlage 2). Jede Abfrage bleibt an die eigene Wache gebunden.
- **Auditor** liest nur das Audit-Protokoll, ohne fachliche Freitexte.
- **Wachenterminal:** gemeinsames Gerät mit Wachen-Code, Dienstkonto mit Rolle Mitglied, nur Alltagsbereiche. Was dort erfasst wird, trägt das Dienstkonto, keine Person. Der Sperrbildschirm zeigt ohne Code die Inhalte des Wachen-Displays (Titel, Zählwerte, am Geburtstag Vorname und Anfangsbuchstabe).
- **Wachen-Display:** Bildschirm ohne Anmeldung mit Titeln, Zählwerten und Ampeln.
- **Django-Admin (`/django-admin/`):** Superuser des technischen Betriebs sehen und ändern dort Daten **ohne Bindung an eine Wache** (welche Tabellen, steht im Datenkatalog unter „Zugriffswege“).
- Wer welche Rolle hat, legt der Master-Admin fest; Änderungen stehen im Audit-Protokoll.

Zu regeln:

- wer Master-Admin, Auditor und Superuser ist: `[Namen/Funktionen]`
- Superuser-Zugriff nur für technische Wartung, mit Protokoll: `[ausfüllen]`
- Vier-Augen-Prinzip für Rollenänderungen: `[ja/nein]`

### 2.5 Löschfristen

Wachwerk-Fakten:

- Technisch umgesetzte Fristen stehen im Datenkatalog; der Vorschlag für den Pilot in `LOESCHKONZEPT.md` (Anlage 3).
- Nachweise (Quittierungen, Abschlüsse, Prüfungen, Buchungen) löscht Wachwerk nicht automatisch. Welche Tabelle ein Nachweis ist, ob sie append-only ist (Ändern und Löschen gesperrt) und ob Wachwerk selbst etwas ersetzt, steht im Datenkatalog je Tabelle („Nachweis“, „Löschschutz“, „Frist technisch“).
- Kein Nachweis sind der Lesestatus von Neuigkeiten und der Erledigt-Vermerk von Tagesaufgaben: „Wieder öffnen“ löscht den Vermerk, das Audit-Protokoll hält das fest.
- Für einige Daten gibt es heute keine Löschautomatik (Lücken im Löschkonzept).

Zu regeln:

- Fristen laut freigegebenem Löschkonzept (Anlage 3)
- Umgang mit den Lücken bis zur technischen Umsetzung: `[ausfüllen]`

### 2.6 Datenflüsse an Dritte

Wachwerk-Fakten:

- Alle externen Dienste sind abschaltbar und im Standard überwiegend aus (Anlage 4, `DATENFLUESSE.md`).
- Im Pilot läuft Wachwerk nur im LAN bzw. auf dem Pi, ohne Erreichbarkeit aus dem Internet; der E2EE-Chat ist aus.

Zu regeln:

- welche Dienste eingeschaltet werden: `[Liste]`
- Einschalten weiterer Dienste nur nach Unterrichtung

### 2.7 Änderungen und Updates

Wachwerk-Fakten:

- Jede Version hat ein CHANGELOG. Der Datenkatalog wird für jede Version neu erzeugt; der Unterschied zur vorigen Fassung zeigt neue Tabellen, Felder und Auswertungen.

Zu regeln:

- Unterrichtung der Interessenvertretung vor jedem Update mit CHANGELOG und Unterschied des Datenkatalogs (`docker compose exec -T web python manage.py data_catalog --station auto > datenkatalog.md`, mit der vorigen Fassung vergleichen)
- Frist für Einwände: `[ausfüllen]`
- Sicherheitsupdates dürfen sofort eingespielt werden; Unterrichtung danach: `[ja/nein]`

### 2.8 Kontrollrechte der Interessenvertretung

Zu regeln:

- Einsicht in Datenkatalog, Rollenliste und Audit-Zweck: `[Turnus]`
- Stichproben im Beisein der oder des DSB: `[ausfüllen]`
- Ansprechperson beim Betreiber: `[Name]`

### 2.9 Rechte der Beschäftigten und freiwillige Angaben

Wachwerk-Fakten:

- Freiwillig sind Geburtstag (nur Tag und Monat), Profilbild, Signal-Nummer und die Teilnahme an der Kaffeekasse. Geburtstag, Profilbild und Signal-Nummer entfernt ein Widerruf sofort. Wer die Kaffeekasse verlässt, zahlt ab dem Folgemonat keinen Beitrag mehr; die bisherigen Buchungen bleiben als Kassennachweis erhalten (append-only, auch der Kassenwart kann sie nicht löschen).
- Persönliche Hinweise sieht nur die Person selbst.

Zu regeln:

- Keine Nachteile bei Verzicht auf freiwillige Angaben.
- Auskunft, Berichtigung und Löschung: Weg und Ansprechperson `[ausfüllen]`; bei KDG bzw. DSG-EKD nach kirchlichem Recht [prüfen].

### 2.10 Bewertung des Pilots

Wachwerk-Fakten:

- Wachwerk misst keine Bediendauer und keine Aktivität je Person.

Zu regeln:

- Bewertung nur über eine anonyme Umfrage (z. B. SUS) und moderierte Tests mit Freiwilligen.
- Ergebnisse nur zusammengefasst für die Wache.

### 2.11 Ausstieg, Export und Löschung

Wachwerk-Fakten:

- Exporte gibt es für Kaffeekasse, Bestandsverzeichnis, Verfallsliste, Fahrzeugliste, Quittierungsnachweise und Kalender, dazu Druckansichten der Papier-Rückfallebene (leere Formulare, Fristenliste, Telefonbuch); Einzelheiten im Datenkatalog.
- Sicherungen laufen nach ihrer Frist aus (Standard 7 Tage, Offsite laut Ziel).

Zu regeln:

- Entscheidung spätestens 3 Monate nach Pilotende: Weiterbetrieb oder Löschung aller Pilotdaten
- Nachweis der Löschung gegenüber der Interessenvertretung: `[ausfüllen]`

### 2.12 Laufzeit und Kündigung

Zu regeln:

- Inkrafttreten: `[Datum]`
- Laufzeit: Pilotzeitraum plus `[ausfüllen]`; Verlängerung schriftlich
- Kündigung: `[Frist]`; Nachwirkung: `[ausfüllen]` [prüfen]

## 3. Anlagen

| Anlage | Inhalt | Quelle |
| --- | --- | --- |
| 1 | Datenkatalog der Wache: Module, Felder, Rollen, Zugriffswege, Auswertungen, Fristen | `docker compose exec -T web python manage.py data_catalog --station auto > datenkatalog.md`; Referenz: [`DATENKATALOG.md`](DATENKATALOG.md) |
| 2 | Rollenmatrix | Abschnitte „Lesen“ und „Schreiben“ im Datenkatalog; Rollenbeschreibung in [`ROLLENMODELL-RETTUNGSWACHE.md`](ROLLENMODELL-RETTUNGSWACHE.md) |
| 3 | Löschfristen | freigegebene Tabelle aus [`LOESCHKONZEPT.md`](LOESCHKONZEPT.md), Abschnitt „Vorschlag für den Pilot“ |
| 4 | Datenflüsse an Dritte | [`DATENFLUESSE.md`](DATENFLUESSE.md) mit den eingeschalteten Diensten |
| 5 | Technische und organisatorische Maßnahmen | [`DSGVO-TOM.md`](DSGVO-TOM.md) |

Unterschriften:

- Betreiber / Dienststelle: `[Name, Datum]`
- Betriebsrat / Personalrat / Mitarbeitervertretung: `[Name, Datum]`
