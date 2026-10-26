# Signal-Benachrichtigungen

Wachwerk kann Erinnerungen und Hinweise per Signal verschicken:

- **In die Wachengruppe**, ohne Namen und ohne Beträge einzelner Personen:
  - monatliche Erinnerung an den Kaffeekassen-Beitrag („Der Beitrag für November ist fällig – 5 von 12 haben schon bezahlt.“)
  - Ergebnis des Kassensturzes
- **Persönlich** an Personen, die ihre Nummer selbst hinterlegt und per Code bestätigt haben. Sie bekommen ihre Benachrichtigungen aus dem Posteingang zusätzlich per Signal, z. B. „Kaffeekasse: Beitrag offen“ oder „Fahrzeug kann freigegeben werden“.

## Wie das technisch läuft

Signal hat keine offizielle Bot-Schnittstelle. Wachwerk nutzt deshalb
[signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)
(Open Source) als zusätzlichen Container.

**Kopplung:**

- Der Container wird als **verknüpftes Gerät** an ein Signal-Konto der Wache gekoppelt, genau wie Signal Desktop.
- Nachrichten kommen dann vom Wachen-Handy.
- Es wird keine neue Nummer registriert.

**Absicherung:**

- Der Container hat **keinen Port nach außen**.
- Nur `web` und `notify-worker` erreichen ihn über das interne Netz `signal-api`.
- Die REST-API selbst hat keine Anmeldung, darf also nie veröffentlicht werden.

**Versand:**

- Wachwerk legt Nachrichten in einen Postausgang (`SignalOutbox`).
- Der `notify-worker` verschickt sie und wiederholt bei Fehlern bis zu 6-mal, mit wachsendem Abstand.
- Gesendete Nachrichten werden nach 30 Tagen gelöscht.

**Image:** `bbernhard/signal-cli-rest-api:0.101`, per Digest festgelegt. Es läuft auf amd64, arm64 (Raspberry Pi) und armv7.

## Einrichtung

1. **Ein Handy der Wache** mit Signal bereithalten, z. B. das Wachen-Diensthandy. Es muss Mitglied der Wachengruppe sein.
2. In `.env` eintragen:

   ```
   COMPOSE_PROFILES=signal          # bei HTTPS: COMPOSE_PROFILES=https,signal
   SIGNAL_API_URL=http://signal:8080
   SIGNAL_NUMBER=+491701234567      # Nummer des Wachen-Handys
   SITE_URL=https://wache.example   # damit Nachrichten einen Link enthalten
   ```

3. `docker compose up -d` (bzw. `wachbuch update`).
4. In Wachwerk als Admin: **Einstellungen → Signal**.
   - Den angezeigten QR-Code scannen: Signal auf dem Wachen-Handy → Einstellungen → Verknüpfte Geräte → „+“.
   - Seite neu laden.
   - Die Wachengruppe auswählen. Ist der Signal-Einladungslink der Wache hinterlegt, ist die passende Gruppe vorausgewählt.
   - Testnachricht senden.
5. **Kaffeekasse → Einstellungen:** „Monatliche Erinnerung in die Signal-Gruppe“ und optional „Kassensturz-Ergebnis“ einschalten.
6. **Jede Person für sich:** Konto → Signal-Benachrichtigungen → Handynummer eingeben → Code aus der Signal-Nachricht bestätigen.

## Datenschutz

- **Persönliche Nummern:** Nur freiwillig und nur nach Bestätigung per Code. So kann niemand fremde Nummern eintragen. Code-Anforderungen sind auf 3 pro Stunde begrenzt.
- **Sichtbarkeit:** Die Nummer sieht niemand im Team. Beim Abschalten wird sie gelöscht.
- **Gruppennachrichten** enthalten keine personenbezogenen Angaben einzelner Beschäftigter.
- **Transport:** Signal ist Ende-zu-Ende-verschlüsselt. Auf dem Server liegen die Schlüssel des verknüpften Geräts im Volume `signal-data`; zusammen mit `.env` sichern und schützen.
- **Datenschutzinformation:** Die Datenschutzseite nennt Signal als optionalen Übertragungsweg.

## Fehlersuche

| Meldung | Ursache |
| --- | --- |
| „Signal-Dienst nicht erreichbar“ | Container läuft nicht (`docker compose ps signal`) oder `SIGNAL_API_URL` falsch |
| „no data to encode“ beim QR-Code | Container erreicht die Signal-Server nicht (Internetzugang/Firewall) |
| „User +49… is not registered“ | Noch nicht gekoppelt oder `SIGNAL_NUMBER` passt nicht zum gekoppelten Handy |
| Gruppe fehlt in der Liste | Wachen-Handy ist nicht Mitglied der Gruppe; nach dem Beitritt Seite neu laden |

Gescheiterte Nachrichten stehen mit Fehlertext in `SignalOutbox` (Django-Admin).
