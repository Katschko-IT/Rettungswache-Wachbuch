# CLIENT-OFFLINE-CONTRACT (Entwurf, nicht implementiert)

Stand: 2026-10-19. Status: **Vertragsentwurf / Entscheidungsgrundlage**.
Es gibt **keinen** Client-Offlinebetrieb: keine Offline-Datenbank, keine Outbox,
keinen Sync, keine offline Schreibvorgänge. Dieses Dokument legt fest, was ein
späterer, ausdrücklich autorisierter Scope dürfen darf — und was dauerhaft
ausgeschlossen bleibt. Es ist **keine** Produktzusage und darf nicht als
Feature-Versprechen auf Webseiten, in Präsentationen oder im Marketing zitiert
werden.

Bezug: `docs/OFFLINE-BETRIEB.md` (Szenario 1: WAN-Ausfall, LAN + Server erreichbar,
durch Tests belegt), `AGENTS.md` §1 (Produktgrenze) und §4 (Invarianten).

## 1. Geltungsbereich und Produktgrenze

Das Wachbuch organisiert interne Wachenabläufe. Es ist **kein** System für
Patienten-, Einsatz-, Alarmierungs-, Diagnose-, Krankheits- oder Leistungsdaten.

Für jeden Offline-Scope gilt daher ohne Ausnahme:

- Keine Patientendaten, keine Einsatzdaten, keine medizinischen Freitexte.
- Keine Gesundheits-, Fürsorge- oder Leistungsangaben, auch nicht in Notizen.
- Keine allgemeinen Datei-Uploads, keine Anhänge, keine Bilder.
- Keine Konten-, Rollen- oder Administrationsdaten im Client-Speicher, die eine
  Offline-Privilegienausübung ermöglichen würden.

## 2. Datensparsamkeit

Ein Client-Cache darf ausschließlich folgende Felder der **eigenen** Wache
enthalten, soweit die aktuelle Rolle sie online ohnehin sehen darf:

| Datentyp | Erlaubte Felder | Nicht erlaubt |
|---|---|---|
| Tagesaufgaben | `id`, `title`, `band`, `weekday`, `sort_order`, Status `done` + `work_date` | Notizen anderer Nutzer, Ersteller-Profile |
| Checklisten | `id`, `title`, `description`, Item-Texte, letzter Abschluss (Zeit, Anzeigename) | Abschlussnotizen, Verlauf, Auditor-Sichten |
| Übergaben (nur Liste) | `id`, `title`, `created_at`, `urgent` | Freitext-Body, Anhänge, Empfängerlisten |
| Eigene Mitgliedschaft | `station_id`, `station_name`, `role`, `user_id`, `display_name` | E-Mail, Telefon, Geburtstag, Avatar |
| Metadaten | `schema_version`, `fetched_at`, `expires_at`, `station_id` | Correlation-IDs, Session-IDs, CSRF-Tokens |

Verboten im Cache: Audit-Log, Kaffeekasse, Chat, private Chats, sichere Mail,
Geburtstage, Teamverwaltung, API-Tokens, Push-Subscriptions, Aktivierungstokens,
Passwort- oder MFA-Material, Roh-HTML der Seiten.

Harte Obergrenzen für einen späteren Scope:

- Maximal **5 MB** pro Origin, maximal **24 h** Alter, maximal **eine** Wache.
- Kein Cache für Rollen `auditor`, `admin`, `cashier` (deren Sichten sind zu
  weitreichend); diese Rollen erhalten offline nur die ehrliche Fehlerseite.
- Beim Benutzerwechsel, Logout, Rollenwechsel oder Stationswechsel wird der
  Cache **vollständig und synchron** gelöscht (siehe §3).

## 3. Benutzerwechsel, Logout, Sitzungsende

1. Der Cache ist an `user_id` **und** `station_id` gebunden. Ein anderer
   Benutzer auf demselben Gerät sieht niemals Daten des vorherigen Benutzers.
2. Logout löscht: IndexedDB-Datenbank, `localStorage`-Einträge des Scopes,
   CryptoKey-Handle und alle In-Memory-Objekte. Ein Reload nach Logout zeigt
   ausschließlich die öffentliche Login-Seite.
3. Sitzungsablauf (Session-Cookie ungültig/abgelaufen) sperrt den Cache: Er
   wird nicht angezeigt, sondern beim nächsten Online-Kontakt gelöscht.
4. Ein „Benutzerwechsel“ ohne Logout ist unzulässig. Es gibt keine geteilten
   Geräteprofile und keine Sammelkonten. Davon getrennt: das Wachenterminal (Web,
   Touch-Bildschirm der Wache) mit gemeinsamem Wachen-Code und Dienstkonto, nur
   Alltagsbereiche, Sperren nach Inaktivität und Löschen von Cache und lokalem
   Speicher (`docs/PI-WACHENTERMINAL.md`). Die App kennt kein Dienstkonto.
5. Beim Öffnen der App prüft der Client zuerst die Online-Session. Ist sie
   nicht bestätigbar, gilt §5 (keine Offline-Authentifizierung).

## 4. Verschlüsselung und Vertrauensmodell

Verbindlich ist eine ehrliche Aussage, keine E2EE-Behauptung:

- Cache-Inhalte werden mit **AES-GCM 256** verschlüsselt in IndexedDB abgelegt.
- Der Schlüssel wird als **nicht-extrahierbarer** `CryptoKey` erzeugt und
  origin-gebunden gespeichert; er verlässt das Gerät nie.
- Diese Bindung ist **kein bewiesener Schutz gegen eine Kopie des Browserprofils**
  oder des Dateisystem-Snapshots: Wer das Profil samt Origin-Daten vollständig
  kopiert und im selben Origin zur Ausführung bringt, kann den Schlüssel über den
  Browser verwenden. Der nicht-extrahierbare Schlüssel verhindert nur den direkten
  Export der Schlüsselbytes, nicht die Nutzung im kopierten Origin. Ein Schutz
  gegen Profilkopien wäre erst durch einen gerätegebundenen Faktor (z. B. WebAuthn
  mit Hardware-Bindung) oder eine passphrasebasierte Ableitung erreichbar; beides
  ist hier **nicht** vorgesehen.
- Praktisch begrenzt der Entwurf daher die Wirkung auf beiläufige Einsicht ohne
  Codeausführung im Origin. Es schützt **nicht** gegen XSS, kompromittierte
  Browser-Erweiterungen, Malware mit Codeausführung im Origin, physischen Zugriff
  mit entsperrtem Gerät oder eine vollständige Profilkopie.
- Der ausgelieferte Webclient und der Server bleiben Teil des Vertrauensmodells.
  „Ende-zu-Ende“ wird für diesen Cache nicht zugesagt.
- Keine Schlüsselableitung aus Passwörtern, keine Wiederherstellung ohne
  Online-Login, kein Schlüssel-Export, keine Synchronisierung des Schlüssels.

## 5. Authentifizierung und Autorisierung offline

Dauerhaft ausgeschlossen, unabhängig von jedem späteren Scope:

- Keine Offline-Anmeldung, kein Offline-Passwortcheck, kein Offline-MFA/TOTP,
  kein Offline-Passkey-Ersatz und kein Bypass „weil offline“.
- Keine Offline-Administration: keine Rollenänderung, keine Kontenfreigabe,
  keine Mitgliedschafts-, Stations- oder Moduländerung.
- Keine Offline-Freigaben (QR-Login-Bestätigung, Gerätefreigabe, Adminapproval).
- Keine Offline-Preisgabe von Daten an einen nicht in dieser Sitzung
  authentifizierten Betrachter.

Ein Cache darf nur innerhalb einer **bereits online bestätigten** Sitzung
gelesen werden. Ist die Sitzung nicht bestätigbar, zeigt der Client die
ehrliche Fehlerseite („keine Verbindung“) und keine Wachendaten.

## 6. Konkret zugelassene Aktionen (Vorschlag für den nächsten Scope)

Nur lesend, nur eigene Wache, nur eigene Rolle, nur innerhalb 24 h:

1. Tagesaufgaben der eigenen Wache ansehen (Titel, Band, Status des Tages).
2. Checklisten-Übersicht und Item-Texte ansehen (ohne Abschlussnotizen).
3. Übergabeliste (Titel, Zeit, Dringend-Kennzeichen) ansehen; Öffnen einer
   Übergabe ist **nicht** offline erlaubt.
4. Eigene Mitgliedschaft/Rolle und Cache-Alter anzeigen.
5. Manuelles Verwerfen des Caches („Offline-Daten löschen“).

Ausdrücklich **nicht** zugelassen in diesem Scope: jede Schreiboperation,
Kommentare, Statusänderungen, Checklisten-Abschlüsse, Kaffeekasse, Chat,
Pinnwand, Teamseiten, Audit-Log, Exporte, Benachrichtigungen, Kalenderänderungen.

## 7. Outbox und Idempotenz (nur Vertragsregel, nicht implementiert)

Falls ein späterer, separat autorisierter Scope Schreibvorgänge erlaubt, gilt
verbindlich:

- Jede Mutation erhält einen **clientseitig erzeugten Idempotenzschlüssel**
  (`UUIDv4` oder `ULID`). Der Wert wird **zufällig** erzeugt und **einmal** pro
  Mutation vergeben; er wird **nicht** aus `user_id`, `station_id`, `entity_type`
  oder Client-Zeit abgeleitet. Diese Felder werden getrennt daneben gespeichert
  (Nachvollziehbarkeit, Dedupe-Kontext), nicht als Eingabe der Schlüsselbildung.
  Eine Ableitung wäre mit UUIDv4 technisch falsch und würde den Schlüssel
  vorhersagbar machen.
- Der Server führt eine Dedupe-Tabelle mit `UNIQUE(idempotency_key)`. Ein
  zweiter Zustellversuch liefert das gespeicherte Ergebnis (gleicher Status,
  gleiche Ressourcen-ID), erzeugt aber **keine** zweite fachliche Wirkung und
  keinen zweiten Audit-Eintrag.
- Wiederholte Zustellung nach Timeout ist erlaubt; Wiederholung mit anderem
  Payload unter demselben Schlüssel wird mit `409 idempotency_conflict`
  abgelehnt.
- Outbox-Einträge sind an `user_id`/`station_id` gebunden, maximal 24 h alt,
  maximal 50 Einträge, und werden nach bestätigter Zustellung gelöscht.
- Die Outbox enthält keine Freitexte außerhalb der dafür vorgesehenen,
  serverseitig validierten Felder; keine Anhänge, keine Patientendaten.
- Ein Outbox-Eintrag ist **keine** Autorisierung: Der Server prüft Rolle,
  Station und Objektgrenze bei jeder Zustellung neu.

## 8. Konflikte, Rollen und Widerruf

- **Autorität bleibt der Server.** Client-Zeit und Client-Status sind Hinweise,
  keine Wahrheit.
- Konfliktklassen und Auflösung:
  1. *Idempotente Append-Ereignisse* (Checklisten-Abschluss, Audit): kein
     fachlicher Konflikt; Duplikate werden über den Idempotenzschlüssel
     unterdrückt.
  2. *Status-Toggles* (Aufgabe erledigt/offen): Server gewinnt bei
     `updated_at`-Abweichung; die Client-Aktion wird verworfen und dem Nutzer
     sichtbar als „nicht übernommen“ gemeldet.
  3. *Freitext/Übergaben*: **kein** Offline-Schreiben. Damit entfällt die
     klassische Merge-Entscheidung.
- **Rollenwiderruf**: Wird eine Mitgliedschaft deaktiviert oder die Rolle
  entzogen, gilt das ab dem nächsten Online-Kontakt. Der Client muss bei
  erkanntem Rollenwechsel sofort Cache und Outbox verwerfen. Innerhalb des
  maximalen Offline-Fensters (24 h) kann ein widerrufener Zugriff auf bereits
  geladene, verschlüsselte Daten nicht technisch verhindert werden — dieses
  Restrisiko ist dokumentiert und muss fachlich akzeptiert werden, sonst ist
  der Scope nicht freigebbar.
- **Kein stilles Überschreiben** von Änderungen anderer Nutzer. Jede
  verworfene Client-Aktion erzeugt eine sichtbare, nicht-blockierende Meldung.

## 9. Test- und Abnahmekriterien (für einen späteren Scope)

1. Netzebene: Browser-Test bricht jeden Request außerhalb der lokalen Origin ab;
   es gibt null externe Versuche (wie im Phase-3-Nachweis).
2. Cache-Inspektion: nach Logout/Benutzerwechsel sind IndexedDB und
   `localStorage` leer; ein Reload zeigt keine Wachendaten.
3. Kryptografie: gespeicherte Bytes sind ohne Schlüssel nicht lesbar; der
   Schlüssel ist nicht extrahierbar; kein Schlüssel im Klartext.
4. Negativ: offline darf keine Schreibaktion erfolgreich aussehen; jede
   Schaltfläche, die schreiben würde, ist deaktiviert und erklärt warum.
5. Rollen: `auditor`/`admin`/`cashier` erhalten keinen Cache.
6. Idempotenz: doppelte Zustellung erzeugt genau eine fachliche Wirkung und
   genau einen Audit-Eintrag; Payload-Abweichung → 409.
7. Widerruf: Rollenentzug beim nächsten Sync → Cache gelöscht, Outbox verworfen.
8. Keine Patienten-/Einsatzdaten in Fixtures, Screenshots, Logs oder Dokumenten.

## 10. Vorgeschlagener nächster autorisierter Scope (schmal)

**„Phase 4a — Read-only Offline-Snapshot für Tagesaufgaben und Checklisten“**

- Umfang: §6 Punkte 1–5, keine Schreibvorgänge, keine Outbox, kein Sync.
- Technik: Service-Worker-Cache ausschließlich für App-Shell/Assets;
  IndexedDB-Snapshot (AES-GCM) für die drei Datentypen aus §2.
- Laufzeit: 24 h TTL, 5 MB Limit, eine Wache, Löschung bei Logout/Wechsel.
- Abnahme: §9 Punkte 1–5 und 8, plus echte Geräte im isolierten WLAN.
- Ausdrücklich **nicht** Teil von Phase 4a: Schreibvorgänge, Outbox,
  Konfliktauflösung, Offline-MFA, Adminfunktionen.

Damit ist der Scope klein genug, um ihn in einem Zyklus zu bauen und ehrlich zu
testen. Schreibvorgänge (Phase 4b) benötigen zuerst die fachlichen
Entscheidungen aus §11.

## 11. Offene Fachentscheidungen (vor Freigabe zu klären)

1. **Datenschutz/Freigabe**: Ist ein 24-h-Snapshot von Aufgaben- und
   Checklistentiteln auf privaten Diensthandys zulässig? Wer entscheidet
   (Wachenleitung, Datenschutzbeauftragte:r, Betriebsrat)?
2. **Gerätehoheit**: Sind private Geräte (BYOD) erlaubt oder nur verwaltete
   Dienstgeräte mit MDM und Remote-Wipe?
3. **Rollenausschluss**: Bleibt der Ausschluss von `auditor`, `admin` und
   `cashier` bestehen, oder braucht eine Wache offline auch Leitungssichten?
4. **Übergaben**: Reicht die Liste (Titel/Zeit/Dringend), oder wird der Body
   fachlich benötigt? Der Body erhöht das Datenvolumen und die Sensibilität
   deutlich.
5. **Offline-Fenster**: Sind 24 h fachlich richtig, oder braucht eine
   Schichtfolge (z. B. 48 h) eine längere Frist?
6. **Widerruf-Restrisiko**: Wird das 24-h-Fenster nach Rollenentzug akzeptiert
   oder ist eine kürzere Frist (z. B. 8 h) nötig?
7. **Schreibvorgänge**: Welche Aktionen dürfen überhaupt jemals offline
   geschrieben werden? Vorschlag: keine — stattdessen ehrliche Fehlerseite.
8. **Support**: Wer hilft beim „Cache löschen“, wenn ein Gerät hängt?

Bis diese Punkte entschieden sind, bleibt der Status: **nicht implementiert,
keine Zusage**.
