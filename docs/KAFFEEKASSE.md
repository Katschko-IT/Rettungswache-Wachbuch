# Kaffeekasse

Stand: Oktober 2026. Recherche, Entscheidungen und Funktionsweise der
Kaffeekasse in Wachwerk.

## Ausgangslage

Auf vielen Wachen heißt sie nur „Kaffeekasse“, ist aber eine
**Gemeinschaftskasse mit festem Monatsbeitrag**:

- Jede teilnehmende Person zahlt jeden Monat einen festen Betrag, meist bar.
- Das Geld kommt in eine Metalldose.
- In einer Mappe wird pro Monat „bezahlt“ abgehakt.
- Aus der Dose wird Kaffee, Milch, Filter usw. gekauft.

Gezählt wird nicht jede einzelne Tasse.

Wachwerk bildet genau das nach und ergänzt, was mit Papier schwer ist:

- Kassenbestand und Kassensturz
- Erinnerung bei offenem Beitrag
- Überweisung per QR-Code
- nachvollziehbare Einkäufe

## Recherche (Kurzfassung)

### Vergleichbare Lösungen

Verglichen wurden:

- **Strichliste (strichliste.org, Open Source):** Guthaben oder Strich mit Kontogrenzen, Rückgängig-Fenster, Artikel, Auswertungen.
- **Getränkeliste (iPad-Kiosk):** PIN, Kopplung des eigenen Handys per QR, verdeckter Saldo.
- **Getränkewart (Feuerwehren):** persönlicher „Deckel“, Push-Nachrichten.
- **Splid/Tricount:** Ausgaben teilen.

### Was übernommen wurde

- Korrektur nur per Gegenbuchung, Buchungen werden nie gelöscht.
- Erinnerung bei offenem Betrag.
- Kassensturz mit zweiter Person.
- Überweisung per GiroCode.
- Einkäufe transparent für alle.
- Austritt nur nach Ausgleich.

### Was bewusst fehlt

- Keine Strichliste pro Tasse: Sie ist auf der Wache nicht üblich. Zudem verraten Zeitstempel einzelner Tassen Pausen- und Anwesenheitsmuster.
- Keine Ranglisten.
- Keine öffentliche Schuldnerliste.

### Typische Probleme in der Praxis

- Schulden wachsen unbemerkt.
- Wer die Wache wechselt, geht mit offenem Betrag.
- Bargeld ist ohne Gegenzeichnung nicht nachvollziehbar.
- Zahlen ohne Kontext beschämen Einzelne.
- Die Kasse läuft über das Privatkonto des Kassenwarts.

### Datenschutz und Mitbestimmung

Das ist eine Einschätzung, keine Rechtsberatung.

**Datenschutz (DSGVO):**

- Die Kasse ist eine freiwillige Absprache der Beschäftigten.
- Läuft sie in Wachwerk, ist der Betreiber datenschutzrechtlich Verantwortlicher.
- Daher gelten strikte Zweckbindung, Datensparsamkeit und Einsicht nur für die Person selbst und den Kassenwart.

**Mitbestimmung (BetrVG):**

- Für § 87 Abs. 1 Nr. 6 BetrVG reicht es, wenn ein System *objektiv geeignet* ist, Verhalten zu überwachen. Ob der Arbeitgeber das will, spielt keine Rolle.
- Ein Monatsbeitrag ohne Verbrauchszeitstempel ist dafür deutlich weniger geeignet als eine Strichliste.
- Die Wachenleitung sieht trotzdem keine Einzelstände (siehe unten).

**Buchführung und Steuer:**

- Die GoBD gelten für eine private Beschäftigtenkasse nach unserer Einschätzung nicht.
- Das Ledger erfüllt das Prinzip ohnehin: Buchungen werden nur angehängt, Korrekturen laufen über Gegenbuchungen.

### GiroCode (EPC069-12)

Der Überweisungs-QR-Code ist so aufgebaut:

- **Zeilen in fester Reihenfolge:**
  1. `BCD`
  2. `002`
  3. `1` (UTF-8)
  4. `SCT`
  5. BIC (in Version 002 optional)
  6. Name (max. 70 Zeichen)
  7. IBAN
  8. Betrag `EUR12.50`
  9. Zweckcode
  10. Referenz
  11. Verwendungszweck (max. 140 Zeichen)
- **Länge:** höchstens 331 Byte.
- **Ende:** kein Zeilenumbruch nach dem letzten Feld.
- **Klartext:** Die Angaben stehen zusätzlich als Text neben dem Code.

Quellen: strichliste.org; App-Store-Beschreibungen von Getränkeliste und
Getränkewart; EPC069-12 v3.0; BAG 1 ABR 20/74, 1 ABR 7/15, 1 ABR 46/15;
EuGH C-34/21; R 19.6 LStR.

## Wer sieht was

| Rolle | Sieht | Darf |
| --- | --- | --- |
| Mitglied | eigenen Stand und eigene Monate, eigene Buchungen; für alle: Kassenbestand, Einkäufe, Kassenstürze, „x von y haben bezahlt“ (ohne Namen) | selbst abhaken („Ich habe bezahlt“), Einkauf eintragen |
| Kassenwart | zusätzlich alle Stände (Mappe), alle Buchungen, Export | Bar erhalten, Monat befreien, Buchung/Korrektur, Kassensturz, Bewegungen, Teilnehmende, Einstellungen |
| Admin (Wachenleitung) | wie Mitglied, **keine Einzelstände** | Teilnehmende, Beitrag und Zahlungswege einrichten; Kassenwart im Team festlegen |
| Auditor | nichts | – |
| Wachenterminal | nichts (Kaffeekasse ist kein Terminal-Bereich) | – |

Erinnerungen gehen nur an die betroffene Person, über den Posteingang und Push.

## Funktionsweise

### Monatsbeitrag

- **Wer zahlt:** Der Kassenwart oder ein Admin trägt Teilnehmende ein, mit dem Monat, ab dem sie zahlen.
- **Buchung:** Für jeden Monat entsteht automatisch eine Belastung mit dem Beitrag, der zu diesem Zeitpunkt gilt. Ändert sich der Beitrag später, bleiben alte Monate unverändert.
- **Ausgeschiedene:** Inaktive Mitglieder werden nicht weiter belastet.
- **Beenden:** Die Teilnahme läuft bis einschließlich des laufenden Monats.
- **Einzahlungen** tilgen den ältesten offenen Monat zuerst. Ein Rest wird zu Guthaben, z. B. „im Voraus bezahlt bis März“.
- **Befreiung** (Urlaub, Elternzeit, Krankheit): Der Kassenwart gleicht genau einen Monat aus, mit Begründung.
- **Erinnerung:** Ab dem eingestellten Tag (Standard: der 10.) erinnert Wachwerk einmal pro Monat an einen offenen Beitrag. Das übernimmt der `notify-worker`, höchstens alle 15 Minuten. Er bucht dabei auch neue Monate.

### Selbst abhaken

„Ich habe bezahlt“ funktioniert wie das Kreuz in der Mappe:

- **Bar:** Die Einzahlung zählt sofort zum Soll-Bestand der Dose. Beim nächsten Kassensturz fällt auf, wenn Geld fehlt.
- **Überweisung, PayPal oder Wero:** Der Kassenwart gleicht mit dem Kontoauszug ab. Dafür gibt es den Filter „Selbst eingetragene Zahlungen“.

### Kasse und Konto

- **Dose** = Bareinzahlungen ± Kassenbewegungen.
- **Konto** = Überweisungen, PayPal und Wero ± Kontobewegungen + eingezahltes Bargeld.
- **Einkäufe** kann jedes Mitglied eintragen. Der Beleg kommt in die Dose.
- **Kassensturz:** Gezählt wird gegen das Soll. Die Differenz wird als eigene Bewegung festgehalten, auch eine Differenz von 0. Eine zweite Person kann mitzählen.
- **Korrekturen** laufen nur über Gegenbuchungen. Auf Datenbankebene sind `UPDATE` und `DELETE` für die App-Rolle gesperrt (`grant_database_access`).

### Überweisung

Ist eine IBAN hinterlegt, zeigt die Seite einen GiroCode:

- Empfänger ist der Kontoinhaber aus den Einstellungen, sonst der Wachenname.
- Der Betrag ist das Offene, sonst ein Monatsbeitrag.
- Der Verwendungszweck lautet „Kaffeekasse <Wache> <Name>“.
- Alle Angaben stehen zusätzlich als Text neben dem Code.
- Empfehlung: ein eigenes Konto der Kasse statt eines Privatkontos.

## Grenzen und nächste Schritte

- **App:** Die API liefert den eigenen Stand (`own`). „Ich habe bezahlt“ gibt es in der App noch nicht, nur im Browser.
- **Löschfristen:** Sie legt der Betreiber im Löschkonzept fest. Buchungen ausgeschiedener Personen bleiben, bis der Stand ausgeglichen ist.
- **Betriebsrat:** Gibt es einen, sollte er vor dem Start informiert werden. Eine kurze Vereinbarung mit Zweckbindung und Verwertungsverbot schafft Klarheit.
