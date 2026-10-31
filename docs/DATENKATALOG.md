# Datenkatalog

Erzeugt – nicht von Hand ändern. Quelle: `core/data_catalog.py`; neu erzeugen mit `python manage.py data_catalog --write`.

Dieser Referenzkatalog nennt alle Module mit den Standardfristen. Für eine Wache (Anlage 1 der Vereinbarung) erzeugt der Betreiber die Fassung mit den dort aktiven Modulen und den eingestellten Fristen:

```bash
docker compose exec -T web python manage.py data_catalog --station auto > datenkatalog.md
```

Die Fristen in diesem Katalog sind die technisch umgesetzten. Verbindliche Fristen legt das Löschkonzept fest (docs/LOESCHKONZEPT.md); dort steht auch der Vorschlag für den Pilot.

## Übersicht

| Modul | Schalter | Personenbezug | Auswertungen mit Personenbezug | Fristen |
| --- | --- | --- | --- | --- |
| [Konten, Anmeldung und Rollen](#modul-konto) | immer aktiv | ja | 2 | Konto, Technische Tabelle, QR-Anmeldung, Zugangsschlüssel, Lücke |
| [Sitzungen und Anmeldeschutz](#modul-anmeldeschutz) | immer aktiv | ja | 0 | Sitzung, Sperrzähler, Anmeldeprotokoll, Rate-Limit-Zähler |
| [Wache, Betreiber und Datenschutzkontakt](#modul-wache) | immer aktiv | ja | 0 | Einstellung, Technische Tabelle |
| [Audit, Fehler und Verwaltungsprotokoll](#modul-audit) | immer aktiv | ja | 1 | Audit, Fehlerereignis, Lücke, Technische Tabelle |
| [Übergaben](#modul-uebergaben) | immer aktiv | ja | 2 | Organisationsdaten, Nachweis, Anhang |
| [Neuigkeiten mit Lesebestätigung](#modul-neuigkeiten) | immer aktiv | ja | 0 | Organisationsdaten, Nachweis, Anhang |
| [Wachen-Wiki](#modul-wiki) | immer aktiv | ja | 0 | Organisationsdaten, Nachweis |
| [Mängel](#modul-maengel) | immer aktiv | ja | 1 | Organisationsdaten, Nachweis, Anhang |
| [Geräte, Status und Ausgabe](#modul-geraete) | immer aktiv | ja | 2 | Organisationsdaten, Nachweis |
| [Kalender](#modul-kalender) | `Station.calendar_enabled` | ja | 0 | Lücke, Zugangsschlüssel |
| [Müllkalender](#modul-muellkalender) | `Station.waste_calendar_enabled` | Freitext möglich | 0 | Abholtermine |
| [Geburtstage (freiwillig)](#modul-geburtstage) | `Station.birthdays_enabled` | ja | 1 | Freiwillige Angabe |
| [Kaffeekasse (freiwillig)](#modul-kaffeekasse) | `Station.coffee_enabled` | ja | 4 | Nachweis, Organisationsdaten |
| [Tagesaufgaben](#modul-aufgaben) | `Station.tasks_enabled` | ja | 2 | Organisationsdaten, Nachweis |
| [Checklisten und Prüfintervalle](#modul-checklisten) | `Station.checklists_enabled` | ja | 1 | Organisationsdaten, Nachweis |
| [Meldungen, Verkehr und Wetter](#modul-lage) | `Station.feeds_enabled` | Freitext möglich | 0 | Einstellung, Meldungen |
| [Pinnwand](#modul-pinnwand) | `Station.pinboard_enabled` | ja | 0 | Lücke, Anhang |
| [Wachenchat, Privatnachrichten und Post (E2EE)](#modul-chat) | `Station.chat_enabled` | ja | 0 | Konto, Lücke |
| [Benachrichtigungen und Push](#modul-benachrichtigungen) | immer aktiv | ja | 0 | Lücke, Gerätebindung, Push-Warteschlange |
| [Signal-Benachrichtigungen](#modul-signal) | Einstellung SIGNAL_API_URL und SIGNAL_NUMBER | ja | 0 | Freiwillige Angabe, Signal-Warteschlange |
| [Medizinprodukte (MPBetreibV)](#modul-mpg) | `Station.mpg_enabled` | ja | 3 | Nachweis |
| [Lager und Material](#modul-lager) | `Station.warehouse_enabled` | ja | 2 | Organisationsdaten, Nachweis |
| [Fuhrpark](#modul-fuhrpark) | `Station.fleet_enabled` | ja | 2 | Nachweis, Einstellung |
| [Dienstanweisungen und Telefonbuch](#modul-orga) | `Station.orga_enabled` | ja | 2 | Nachweis, Organisationsdaten |
| [Wachen-Display](#modul-display) | `Station.display_enabled` | ja | 0 | Zugangsschlüssel |
| [Wachenterminal](#modul-terminal) | Einstellung TERMINAL_ENABLED | ja | 0 | Zugangsschlüssel, Einstellung, Kopplungscode |
| [Öffentliche Demo](#modul-demo) | Einstellung DEMO_SANDBOX | nein | 0 | Demo-Besuch, Technische Tabelle |
| [Rückmeldungen](#modul-feedback) | Einstellung FEEDBACK_ENABLED | ja | 0 | Rückmeldung |

## Rollen

| Rolle | Bedeutung |
| --- | --- |
| Inhaltsrollen | Mitglied, Schichtleitung, Kassenwart und Master-Admin einer Wache |
| Mitglied | Rolle `member` |
| Schichtleitung | Rolle `shift_lead` |
| Kassenwart | Rolle `cashier`, nur für die Kaffeekasse |
| Master-Admin | Rolle `admin`, Verwaltung der Wache |
| Auditor | Rolle `auditor`, liest nur das Audit-Protokoll, keine fachlichen Freitexte |
| die Person selbst | nur die eigenen Einträge |
| Wachenterminal (Dienstkonto) | gemeinsames Gerät an der Wache, Rolle Mitglied, nur Alltagsbereiche (docs/PI-WACHENTERMINAL.md) |
| Wachen-Display | Bildschirm mit Display-Link, ohne Anmeldung |
| öffentlich | ohne Anmeldung erreichbar |
| Superuser (Django-Admin) | technischer Betrieb unter `/django-admin/`, ohne Bindung an eine Wache |
| System | Hintergrunddienste (housekeeping, worker, Abgleich), keine Person |

## Zugriffswege

| Weg | Bedeutung |
| --- | --- |
| Web | Weboberfläche nach Anmeldung, immer an die eigene Wache gebunden |
| App (API) | App-Zugang über `/api/v1/` mit persönlichem App-Token |
| Wachenterminal | Alltagsmodus am registrierten Terminal unter dem Dienstkonto; geprüft gegen `core/terminal.py` (OPEN_MODE_PATHS) |
| Display | Wachen-Display sowie Sperrbildschirm und Startseite des Wachenterminals: nur Titel, Zählwerte und Ampeln, ohne Anmeldung sichtbar; geprüft gegen die Abfragen von `core/display.py` |
| öffentliche Seite | Impressum, Datenschutz und Anmeldung ohne Konto |
| Export/Datei | CSV-, ICS- oder Druckausgabe |
| E-Mail | Versand über den eingetragenen SMTP-Server (nur wenn eingerichtet) |
| Signal | Versand über Signal (nur wenn eingerichtet) |
| Push | Benachrichtigung an Browser oder App (nur wenn eingerichtet) |
| Django-Admin | aus `admin.site` abgeleitet: Superuser lesen oder ändern ohne Bindung an eine Wache |

## Arten von Feldern

Die Art leitet sich aus dem Datenmodell ab. „Person (Konto)“ ist ein Verweis auf ein Benutzerkonto; „Kontakt/Name“ sind Namen, Telefonnummern, Bankverbindungen oder E-Mail-Adressen als Text; „persönliche Angabe“ sind weitere freiwillige Angaben zu einer Person; „Freitext“ kann alles enthalten, was Menschen eintippen; „Netzwerk/Gerät“ sind IP-Adressen, Browserkennungen oder Geräteadressen; „Geheimnis/Prüfwert“ sind Hashes und Schlüssel, die niemand im Klartext liest. Auswahlfelder werden ohne ihre Werte aufgeführt. Die Spalte Bezeichnung zeigt nur ausdrücklich gesetzte Bezeichnungen.

<a id="modul-konto"></a>

## Konten, Anmeldung und Rollen

Anmeldung, Zwei-Faktor-Schutz, Rollen je Wache und App-Zugänge.

- Schalter: immer aktiv
- Bereiche: `/konto/`, `/team/`, `/anmelden/`, `/registrieren/`, `/aktivieren/`, `/abmelden/`, `/sprache/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Teamliste mit Namen, Rollen und Zwei-Faktor-Stand | `team` | Master-Admin | **ja** |  |
| Offene Einladungen mit Namen | `team_invites` | Master-Admin | **ja** |  |

### auth.Group

Django-Gruppen (in Wachwerk ungenutzt)

- Lesen: Superuser (Django-Admin)
- Schreiben: Superuser (Django-Admin)
- Zugriffswege: Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: ohne Personenbezug; bleibt, solange die Installation besteht

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `name` |  | Freitext |  |
| `permissions` |  | Verweis |  |

### auth.Permission

Django-Rechte für den Django-Admin

- Lesen: Superuser (Django-Admin)
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: ohne Personenbezug; bleibt, solange die Installation besteht

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `name` |  | Freitext |  |
| `content_type` |  | Verweis |  |
| `codename` |  | Wert |  |

### auth.User

Benutzerkonto: Anmeldename, Name, E-Mail, Passwort-Hash

- Lesen: die Person selbst, Master-Admin, Auditor, Wachen-Display, Superuser (Django-Admin)
- Schreiben: die Person selbst, Master-Admin, Superuser (Django-Admin)
- Zugriffswege: Web, App (API), Display, Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: solange das Konto besteht; Deaktivieren oder Löschen durch Master-Admin bzw. Superuser
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Andere Inhaltsrollen sehen Vor- und Nachnamen dort, wo Einträge einer Person zugeordnet sind; der Auditor sieht Namen im Audit-Protokoll; Display und Sperrbildschirm zeigen am Geburtstag Vorname und Anfangsbuchstaben (nur mit Einwilligung).

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `password` |  | Geheimnis/Prüfwert |  |
| `last_login` |  | Zeitpunkt |  |
| `is_superuser` |  | Wert |  |
| `username` |  | Kontakt/Name |  |
| `first_name` |  | Kontakt/Name |  |
| `last_name` |  | Kontakt/Name |  |
| `email` |  | Kontakt/Name |  |
| `is_staff` |  | Wert |  |
| `is_active` |  | Wert |  |
| `date_joined` |  | Zeitpunkt |  |
| `groups` |  | Verweis |  |
| `user_permissions` |  | Verweis |  |

### core.ApiToken

App-Zugänge (nur Hash und Präfix gespeichert)

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: gilt bis Ablauf oder Widerruf; widerrufene und abgelaufene Einträge bleiben ohne technische Löschung
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `label` |  | Freitext |  |
| `token_prefix` |  | Kennung | erste Zeichen zur Wiedererkennung, kein Geheimnis |
| `token_hash` |  | Geheimnis/Prüfwert |  |
| `scopes` |  | strukturierte Angaben |  |
| `is_active` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `last_used_at` |  | Zeitpunkt |  |
| `expires_at` |  | Zeitpunkt |  |

### core.EmployeeActivation

Einladungen zur Kontoaktivierung (nur Hash)

- Lesen: Master-Admin
- Schreiben: Master-Admin
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `station` |  | Verweis |  |
| `token_hash` |  | Geheimnis/Prüfwert |  |
| `role` |  | Auswahl |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `expires_at` |  | Zeitpunkt |  |
| `used_at` |  | Zeitpunkt |  |
| `revoked_at` |  | Zeitpunkt |  |

### core.Membership

Rolle einer Person in einer Wache

- Lesen: die Person selbst, Master-Admin
- Schreiben: Master-Admin
- Zugriffswege: Web, App (API), Django-Admin (lesen)
- Nachweis: nein
- Frist technisch: solange das Konto besteht; Deaktivieren oder Löschen durch Master-Admin bzw. Superuser
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Die eigene Rolle sieht jede Person; die Teamliste nur der Master-Admin.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `station` |  | Verweis |  |
| `role` |  | Auswahl |  |
| `is_active` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |

### core.QrLoginRequest

Anmeldung per QR-Code (Hashes, Status, Herkunft)

- Lesen: System
- Schreiben: die Person selbst, System
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: abgeschlossene oder abgelaufene Vorgänge nach 24 Stunden (`housekeeping`)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `secret_hash` |  | Geheimnis/Prüfwert |  |
| `manual_code_hash` |  | Geheimnis/Prüfwert |  |
| `browser_session_hash` |  | Geheimnis/Prüfwert |  |
| `browser_nonce_hash` |  | Geheimnis/Prüfwert |  |
| `station` |  | Verweis |  |
| `origin` |  | Netzwerk/Gerät | Adresse des anfragenden Browsers |
| `state` |  | Auswahl |  |
| `created_at` |  | Zeitpunkt |  |
| `expires_at` |  | Zeitpunkt |  |
| `approved_at` |  | Zeitpunkt |  |
| `consumed_at` |  | Zeitpunkt |  |
| `approved_by` |  | Person (Konto) |  |
| `approved_session_hash` |  | Geheimnis/Prüfwert |  |
| `attempts` |  | Wert |  |
| `check_word` |  | Wert |  |

### core.QrTotpUse

Schutz gegen doppelt benutzte TOTP-Codes

- Lesen: System
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: abgeschlossene oder abgelaufene Vorgänge nach 24 Stunden (`housekeeping`)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `time_step` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |

### core.RegistrationRequest

Selbstregistrierung mit Wunschwache und Notiz

- Lesen: Master-Admin
- Schreiben: öffentlich, Master-Admin
- Zugriffswege: Web, öffentliche Seite
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `preferred_station` |  | Verweis |  |
| `note` |  | Freitext |  |
| `status` |  | Auswahl |  |
| `created_at` |  | Zeitpunkt |  |
| `reviewed_at` |  | Zeitpunkt |  |
| `reviewed_by` |  | Person (Konto) |  |

### core.TotpDevice

Zwei-Faktor-Schlüssel (TOTP), verschlüsselt gespeichert

- Lesen: die Person selbst
- Schreiben: die Person selbst, Master-Admin
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: solange das Konto besteht; Deaktivieren oder Löschen durch Master-Admin bzw. Superuser
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Der Master-Admin kann den zweiten Faktor zurücksetzen, aber nicht lesen.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `secret` |  | Geheimnis/Prüfwert |  |
| `is_confirmed` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `confirmed_at` |  | Zeitpunkt |  |

### core.UserProfile

Sprache und Profilbild

- Lesen: Inhaltsrollen, die Person selbst, Wachenterminal (Dienstkonto)
- Schreiben: die Person selbst
- Zugriffswege: Web, App (API), Wachenterminal
- Nachweis: nein
- Frist technisch: solange das Konto besteht; Deaktivieren oder Löschen durch Master-Admin bzw. Superuser
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Profilbilder sehen Inhaltsrollen derselben Wache und das Wachenterminal (nur Anzeige).

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `language` |  | Wert |  |
| `avatar` |  | Datei/Bild | für Inhaltsrollen und am Wachenterminal sichtbar |
| `avatar_content_type` |  | Wert |  |
| `avatar_updated_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.WebAuthnCredential

Passkeys (öffentlicher Schlüssel, Gerätename)

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: solange das Konto besteht; Deaktivieren oder Löschen durch Master-Admin bzw. Superuser
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `credential_id` |  | Kennung | Kennung des Passkeys, kein Geheimnis |
| `public_key` |  | Schlüssel (öffentlich) |  |
| `sign_count` |  | Wert |  |
| `device_name` |  | Freitext |  |
| `created_at` |  | Zeitpunkt |  |
| `last_used_at` |  | Zeitpunkt |  |

<a id="modul-anmeldeschutz"></a>

## Sitzungen und Anmeldeschutz

Sitzungen, Sperre nach Fehlversuchen und Begrenzung der Anfragen.

- Schalter: immer aktiv

### axes.AccessAttempt

Fehlgeschlagene Anmeldungen je Benutzername und IP-Adresse (Sperrzähler)

- Lesen: Superuser (Django-Admin)
- Schreiben: System
- Zugriffswege: Django-Admin (lesen, ändern, löschen)
- Nachweis: nein
- Frist technisch: django-axes entfernt den Zähler nach erfolgreicher Anmeldung und nach Ablauf der Sperrzeit (1 Stunde) beim nächsten Anmeldeversuch
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user_agent` |  | Netzwerk/Gerät |  |
| `ip_address` |  | Netzwerk/Gerät |  |
| `username` |  | Kontakt/Name |  |
| `http_accept` |  | Netzwerk/Gerät |  |
| `path_info` |  | Wert | aufgerufene Anmeldeadresse |
| `attempt_time` |  | Zeitpunkt |  |
| `get_data` |  | Freitext | Abfrageparameter des Anmeldeversuchs |
| `post_data` |  | Freitext | Formulardaten des Anmeldeversuchs ohne Passwort |
| `failures_since_start` |  | Wert |  |

### axes.AccessAttemptExpiration

Ablaufzeit der Sperre

- Lesen: System
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: django-axes entfernt den Zähler nach erfolgreicher Anmeldung und nach Ablauf der Sperrzeit (1 Stunde) beim nächsten Anmeldeversuch
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `access_attempt` |  | Verweis |  |
| `expires_at` |  | Zeitpunkt |  |

### axes.AccessFailureLog

Protokoll fehlgeschlagener Anmeldungen

- Lesen: Superuser (Django-Admin)
- Schreiben: System
- Zugriffswege: Django-Admin (lesen, ändern, löschen)
- Nachweis: nein
- Frist technisch: 30 Tage (LOGIN_LOG_RETENTION_DAYS, `housekeeping`)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user_agent` |  | Netzwerk/Gerät |  |
| `ip_address` |  | Netzwerk/Gerät |  |
| `username` |  | Kontakt/Name |  |
| `http_accept` |  | Netzwerk/Gerät |  |
| `path_info` |  | Wert | aufgerufene Anmeldeadresse |
| `attempt_time` |  | Zeitpunkt |  |
| `locked_out` |  | Wert |  |

### axes.AccessLog

Anmeldeprotokoll: Benutzername, IP-Adresse, Browser, Zeit

- Lesen: Superuser (Django-Admin)
- Schreiben: System
- Zugriffswege: Django-Admin (lesen, ändern, löschen)
- Nachweis: nein
- Frist technisch: 30 Tage (LOGIN_LOG_RETENTION_DAYS, `housekeeping`)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user_agent` |  | Netzwerk/Gerät |  |
| `ip_address` |  | Netzwerk/Gerät |  |
| `username` |  | Kontakt/Name |  |
| `http_accept` |  | Netzwerk/Gerät |  |
| `path_info` |  | Wert | aufgerufene Anmeldeadresse |
| `attempt_time` |  | Zeitpunkt |  |
| `logout_time` |  | Zeitpunkt |  |
| `session_hash` |  | Geheimnis/Prüfwert |  |

### core.RateLimit

Zähler gegen zu viele Anfragen (nur Hash des Schlüssels)

- Lesen: System
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: abgelaufene Zähler stündlich (`housekeeping`); gespeichert ist nur ein Hash
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `bucket` |  | Wert |  |
| `key_hash` |  | Geheimnis/Prüfwert |  |
| `window_start` |  | Zeitpunkt |  |
| `count` |  | Wert |  |

### sessions.Session

Angemeldete Sitzungen (Inhalt verschlüsselt signiert)

- Lesen: System
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: läuft nach 12 Stunden ab; abgelaufene Sitzungen löscht `housekeeping` stündlich
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `session_key` |  | Geheimnis/Prüfwert |  |
| `session_data` |  | Geheimnis/Prüfwert |  |
| `expire_date` |  | Zeitpunkt |  |

<a id="modul-wache"></a>

## Wache, Betreiber und Datenschutzkontakt

Stammdaten der Wache, Impressum und Datenschutzinformation, Modulschalter.

- Schalter: immer aktiv
- Bereiche: `/einstellungen/`, `/datenschutz/`, `/impressum/`, `/setup/`

### core.AppVersion

Aktuelle App-Versionen für die Update-Prüfung

- Lesen: öffentlich
- Schreiben: Superuser (Django-Admin)
- Zugriffswege: App (API), Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: ohne Personenbezug; bleibt, solange die Installation besteht

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `platform` | Plattform | Auswahl |  |
| `version` | Version | Wert |  |
| `version_code` | Versionscode | Wert |  |
| `is_active` | Aktiv | Wert |  |
| `release_date` | Veröffentlichungsdatum | Zeitpunkt |  |
| `download_url` | Download-URL | Link |  |
| `changelog` | Änderungsprotokoll | Freitext |  |
| `is_forced` | Erzwungenes Update | Wert |  |
| `min_required_version` | Mindestversion | Wert |  |
| `created_at` | Erstellt am | Zeitpunkt |  |
| `updated_at` | Aktualisiert am | Zeitpunkt |  |

### core.DataProtectionOfficer

Kontakt der Datenschutzbeauftragten

- Lesen: öffentlich, Master-Admin, Superuser (Django-Admin)
- Schreiben: Master-Admin, Superuser (Django-Admin)
- Zugriffswege: öffentliche Seite, Wachenterminal, Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: solange die Installation besteht; Änderung durch Master-Admin
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Öffentlich nur, wenn „in der Datenschutzinformation veröffentlichen“ gesetzt ist; interne Notizen nie.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` | Wache | Verweis |  |
| `display_name` | Name / Bezeichnung | Kontakt/Name |  |
| `organization` | Organisation / externer Dienstleister | Freitext |  |
| `email` | E-Mail | Kontakt/Name |  |
| `phone` | Telefon | Kontakt/Name |  |
| `postal_address` | Postanschrift | Kontakt/Name |  |
| `is_external` | Extern bestellt | Wert |  |
| `is_primary` | Hauptkontakt | Wert |  |
| `is_active` | Aktiv | Wert |  |
| `publish_in_privacy_notice` | Auf Datenschutzseite veröffentlichen | Wert |  |
| `internal_notes` | Interne Notiz | Freitext |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.InstallationSetup

Abschluss der Ersteinrichtung

- Lesen: System
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: solange die Installation besteht; Änderung durch Master-Admin
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `singleton` |  | Wert |  |
| `completed_at` |  | Zeitpunkt |  |
| `station` |  | Verweis |  |
| `completed_by` |  | Person (Konto) |  |
| `bootstrap_fingerprint` |  | Geheimnis/Prüfwert |  |
| `created_at` |  | Zeitpunkt |  |

### core.SiteProfile

Betreiberangaben für Impressum und Datenschutzinformation

- Lesen: öffentlich
- Schreiben: Master-Admin
- Zugriffswege: öffentliche Seite, Wachenterminal
- Nachweis: nein
- Frist technisch: solange die Installation besteht; Änderung durch Master-Admin
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `singleton` |  | Wert |  |
| `operator_name` | Anbieter (Name oder Organisation) | Kontakt/Name | öffentlich im Impressum; bei Einzelpersonen ein Name |
| `legal_form` | Rechtsform | Freitext |  |
| `represented_by` | Vertreten durch | Kontakt/Name | öffentlich im Impressum |
| `street` | Straße und Hausnummer | Freitext |  |
| `postal_code` | Postleitzahl | Wert |  |
| `city` | Ort | Wert |  |
| `country` | Land | Wert |  |
| `email` | E-Mail | Kontakt/Name |  |
| `phone` | Telefon | Kontakt/Name |  |
| `register_entry` | Registereintrag | Freitext |  |
| `vat_id` | Umsatzsteuer-ID | Wert |  |
| `content_responsible` | Inhaltlich verantwortlich | Kontakt/Name | öffentlich im Impressum |
| `impressum_extra` | Weitere Angaben im Impressum | Freitext |  |
| `public_site` | Öffentlich im Internet erreichbar | Wert |  |
| `privacy_email` | Kontakt für Datenschutzfragen | Kontakt/Name |  |
| `hosting_provider` | Hosting-Anbieter | Freitext |  |
| `server_location` | Serverstandort | Auswahl |  |
| `supervisory_authority` | Zuständige Datenschutz-Aufsichtsbehörde | Freitext |  |
| `mfa_required` | Zwei-Faktor-Anmeldung für alle Konten | Wert |  |
| `updated_at` |  | Zeitpunkt |  |
| `updated_by` |  | Person (Konto) |  |

### core.Station

Wache: Name, Adresse, Modulschalter, Zahlungsangaben der Kaffeekasse

- Lesen: Inhaltsrollen, Superuser (Django-Admin)
- Schreiben: Master-Admin, Superuser (Django-Admin)
- Zugriffswege: Web, App (API), Display, Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: solange die Installation besteht; Änderung durch Master-Admin
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Der Auditor sieht nur den Namen der Wache. Zahlungsangaben (IBAN, BIC, Verwendungszweck) sehen Inhaltsrollen auf der Seite Kaffeekasse.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `name` |  | Freitext |  |
| `slug` |  | Wert |  |
| `organization_profile` | Organisationsprofil | Auswahl |  |
| `is_active` |  | Wert |  |
| `calendar_enabled` | Kalender aktiviert | Wert |  |
| `birthdays_enabled` | Geburtstage aktiviert | Wert |  |
| `coffee_enabled` | Kaffeekasse aktiviert | Wert |  |
| `feeds_enabled` | Externe Meldungen aktiviert | Wert |  |
| `tasks_enabled` | Tagesaufgaben aktiviert | Wert |  |
| `chat_enabled` | Wachenchat aktiviert | Wert |  |
| `pinboard_enabled` | Pinnwand aktiviert | Wert |  |
| `holidays_enabled` | Feiertage im Kalender | Wert |  |
| `holiday_state` | Bundesland für Feiertage | Auswahl |  |
| `checklists_enabled` | Checklisten aktiviert | Wert |  |
| `mpg_enabled` | MPG & Medizingeräte aktiviert | Wert |  |
| `warehouse_enabled` | Lager & Materialwirtschaft aktiviert | Wert |  |
| `fleet_enabled` | Fuhrpark & Fahrzeuge aktiviert | Wert |  |
| `display_enabled` | Wachen-Display aktiviert | Wert |  |
| `orga_enabled` | Organisation & Desk aktiviert | Wert |  |
| `waste_calendar_enabled` | Muellkalender aktiviert | Wert |  |
| `waste_calendar_url` | Muellkalender-ICS-URL | Link |  |
| `more_order` | Reihenfolge der Bereiche unter Mehr | Freitext |  |
| `nav_order` | Reihenfolge der Hauptnavigation | Freitext |  |
| `signal_group_url` | Signal-Gruppe (Einladungslink) | Link |  |
| `signal_group_id` | Signal-Gruppe für Benachrichtigungen | Freitext |  |
| `paypal_me_url` | PayPal.me-Link | Link |  |
| `wero_link` | Wero-Link | Link |  |
| `iban` | IBAN | Kontakt/Name | Zahlungsangabe der Kaffeekasse |
| `bic` | BIC | Wert | Zahlungsangabe der Kaffeekasse |
| `payment_note` | Zahlungshinweis | Freitext |  |
| `employee_count` | Mitarbeiterzahl | Wert |  |
| `street` | Straße und Hausnummer | Freitext |  |
| `postal_code` | Postleitzahl | Wert |  |
| `city` | Ort | Wert |  |
| `latitude` | Breitengrad | Wert | auf 4 Nachkommastellen gerundet, Standort der Wache |
| `longitude` | Längengrad | Wert | auf 4 Nachkommastellen gerundet, Standort der Wache |
| `timezone_name` | Zeitzone | Wert |  |
| `weather_enabled` | Wettervorhersage aktiviert | Wert |  |
| `traffic_enabled` | Verkehrslage (Baustellen und Sperrungen) | Wert |  |
| `traffic_roads` | Autobahnen und Bundesstraßen | Wert |  |
| `traffic_radius_km` | Umkreis in km | Wert |  |
| `traffic_warning_areas` | Gebiete für Bevölkerungswarnungen | Freitext |  |
| `traffic_local_sources` | Kommunale Quellen Steinhagen und Kreis Gütersloh | Wert |  |

<a id="modul-audit"></a>

## Audit, Fehler und Verwaltungsprotokoll

Nachvollziehbarkeit von Änderungen und Betrieb ohne fachliche Freitexte.

- Schalter: immer aktiv
- Bereiche: `/audit/`, `/system/`, `/django-admin/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Audit-Protokoll mit Person, Zeit, Aktion und geänderten Feldern | `audit_log` | Auditor, Master-Admin | **ja** |  |
| Fehlerereignisse ohne Personenbezug | `error_events` | Master-Admin | nein |  |
| Supportbericht (Fehlercodes, Version, ohne Personen) | `support_export` | Master-Admin | nein | Felder siehe SUPPORT_EXPORT_FIELDS in core/diagnostics_export.py |

### admin.LogEntry

Änderungsprotokoll des Django-Admin

- Lesen: Superuser (Django-Admin)
- Schreiben: Superuser (Django-Admin)
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `action_time` |  | Zeitpunkt |  |
| `user` |  | Person (Konto) |  |
| `content_type` |  | Verweis |  |
| `object_id` |  | Freitext |  |
| `object_repr` |  | Freitext | Bezeichnung des geänderten Objekts |
| `action_flag` |  | Auswahl |  |
| `change_message` |  | Freitext | Beschreibung der Änderung im Django-Admin |

### contenttypes.ContentType

Technische Liste der Datentypen

- Lesen: System
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: ohne Personenbezug; bleibt, solange die Installation besteht

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `app_label` |  | Wert |  |
| `model` |  | Wert |  |

### core.AuditEvent

Audit: wer hat wann was an welchem Objekt geändert

- Lesen: Auditor, Master-Admin, Superuser (Django-Admin)
- Schreiben: System
- Zugriffswege: Web, Django-Admin (lesen)
- Nachweis: ja, append-only (Datenbankrechte)
- Frist technisch: unbegrenzt, solange RETENTION_AUDIT_DAYS = 0 (Standard); sonst löscht `apply_retention` mit den Rechten des Datenbank-Eigentümers
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Append-only. Enthält Feldnamen und Statuswerte, keine fachlichen Freitexte.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `actor` |  | Person (Konto) |  |
| `station` |  | Verweis |  |
| `action` |  | Wert |  |
| `object_type` |  | Wert |  |
| `object_id` |  | Wert |  |
| `metadata` |  | strukturierte Angaben | Feldnamen, Statuswerte, vereinzelt Benutzernamen; keine fachlichen Freitexte |
| `created_at` |  | Zeitpunkt |  |

### core.ErrorEvent

Fehlerereignisse (Route, Kategorie, Status, Version)

- Lesen: Master-Admin
- Schreiben: System
- Zugriffswege: Web, Export/Datei
- Nachweis: nein
- Frist technisch: 30 Tage (ERROR_EVENT_RETENTION_DAYS, `housekeeping`)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `occurred_at` |  | Zeitpunkt |  |
| `correlation_id` |  | Freitext |  |
| `route_name` |  | Freitext |  |
| `category` |  | Auswahl |  |
| `http_status` |  | Wert |  |
| `app_version` |  | Wert |  |
| `station` |  | Verweis |  |

<a id="modul-uebergaben"></a>

## Übergaben

Informationen von Schicht zu Schicht mit Quittierung.

- Schalter: immer aktiv
- Bereiche: `/uebergaben/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Lesebestätigungen einer Übergabe mit Namen und Zeit | `handover_detail` | Inhaltsrollen, Wachenterminal (Dienstkonto) | **ja** | für alle Inhaltsrollen und am Wachenterminal sichtbar |
| Lesebestätigungen mit Namen und Zeit (App) | `api_v1_handover_acks` | Inhaltsrollen | **ja** |  |

### core.HandoverAck

Lesebestätigung: Person und Zeit

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, App (API), Wachenterminal
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `handover` |  | Verweis |  |
| `user` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.HandoverAttachment

Anhänge (Bild oder PDF)

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Zugriffswege: Web, App (API), Wachenterminal
- Nachweis: nein
- Frist technisch: keine automatische Löschung; Löschung zusammen mit dem Vorgang laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `handover` |  | Verweis |  |
| `station` |  | Verweis |  |
| `filename` |  | Freitext |  |
| `content_type` |  | Wert |  |
| `data` |  | Datei/Bild |  |
| `size` |  | Wert |  |
| `uploaded_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.HandoverEntry

Übergabe: Titel, Text, Kategorie, Priorität, Status, Autor

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto), Wachen-Display
- Schreiben: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Zugriffswege: Web, App (API), Wachenterminal, Display, Django-Admin (lesen)
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Display: nur die Zahl dringender offener Übergaben. Status und Bearbeitung: Schichtleitung und Master-Admin.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `category` |  | Auswahl |  |
| `priority` |  | Auswahl |  |
| `status` |  | Auswahl |  |
| `title` |  | Freitext |  |
| `details` |  | Freitext |  |
| `author` |  | Person (Konto) |  |
| `version` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |
| `completed_at` |  | Zeitpunkt |  |

### core.HandoverRevision

Versionen einer Übergabe (Schnappschuss, Person)

- Lesen: Inhaltsrollen
- Schreiben: System
- Zugriffswege: Web, Django-Admin (lesen)
- Nachweis: ja, append-only (Datenbankrechte)
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `handover` |  | Verweis |  |
| `version` |  | Wert |  |
| `snapshot` |  | strukturierte Angaben |  |
| `changed_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

<a id="modul-neuigkeiten"></a>

## Neuigkeiten mit Lesebestätigung

Mitteilungen der Wachleitung, die alle quittieren.

- Schalter: immer aktiv
- Bereiche: `/neuigkeiten/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Lesestand einer Neuigkeit als Anzahl („3 von 8 haben gelesen“) | `news_detail` | Inhaltsrollen, Wachenterminal (Dienstkonto) | nein | keine Namen; bei sehr kleinen Wachen lässt die Zahl Rückschlüsse zu |

### core.NewsAcknowledgement

Quittierung: Person und Zeit

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Andere sehen nur die Anzahl. Das Wachenterminal kann nicht quittieren.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `post` |  | Verweis |  |
| `user` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.NewsAttachment

Anhänge (Bild oder PDF)

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Schichtleitung, Master-Admin
- Zugriffswege: Web, Wachenterminal
- Nachweis: nein
- Frist technisch: keine automatische Löschung; Löschung zusammen mit dem Vorgang laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `post` |  | Verweis |  |
| `station` |  | Verweis |  |
| `filename` |  | Freitext |  |
| `content_type` |  | Wert |  |
| `data` |  | Datei/Bild |  |
| `size` |  | Wert |  |
| `uploaded_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.NewsPost

Neuigkeit: Titel, Text, Autor

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto), Wachen-Display
- Schreiben: Schichtleitung, Master-Admin
- Zugriffswege: Web, Wachenterminal, Display
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `title` |  | Freitext |  |
| `body` |  | Freitext |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `archived_at` |  | Zeitpunkt |  |

<a id="modul-wiki"></a>

## Wachen-Wiki

Wissen der Wache mit Versionsverlauf.

- Schalter: immer aktiv
- Bereiche: `/wiki/`

### core.WikiArticle

Artikel: Titel, Text, Autor

- Lesen: Inhaltsrollen
- Schreiben: Master-Admin
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` | Wache | Verweis |  |
| `slug` | Slug | Wert |  |
| `title` | Titel | Freitext |  |
| `body` | Text | Freitext |  |
| `is_archived` | Archiviert | Wert |  |
| `current_revision_number` | Aktuelle Revisionsnummer | Wert |  |
| `created_by` | Erstellt von | Person (Konto) |  |
| `created_at` | Erstellt am | Zeitpunkt |  |
| `updated_at` | Aktualisiert am | Zeitpunkt |  |

### core.WikiRevision

Versionen mit bearbeitender Person

- Lesen: Inhaltsrollen
- Schreiben: System
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `article` | Artikel | Verweis |  |
| `number` | Revisionsnummer | Wert |  |
| `title` | Titel | Freitext |  |
| `body` | Text | Freitext |  |
| `edited_by` | Bearbeitet von | Person (Konto) |  |
| `created_at` | Erstellt am | Zeitpunkt |  |
| `app_version` | Softwareversion | Wert |  |

<a id="modul-maengel"></a>

## Mängel

Mängel an Fahrzeugen, Geräten und Gebäude mit Frist und Verlauf.

- Schalter: immer aktiv
- Bereiche: `/maengel/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Verlauf eines Mangels mit Namen | `defect_detail_web` | Inhaltsrollen, Wachenterminal (Dienstkonto) | **ja** |  |

### core.Defect

Mangel: Titel, Beschreibung, Priorität, Status, zuständige Person

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Zugriffswege: Web, App (API), Wachenterminal
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `title` |  | Freitext |  |
| `description` |  | Freitext |  |
| `asset_ref` |  | Freitext |  |
| `priority` |  | Auswahl |  |
| `status` |  | Auswahl |  |
| `owner` |  | Person (Konto) |  |
| `due_at` |  | Zeitpunkt |  |
| `category` |  | Auswahl |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |
| `closed_at` |  | Zeitpunkt |  |
| `medical_device` |  | Verweis |  |

### core.DefectAttachment

Fotos zum Mangel (Metadaten entfernt)

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Zugriffswege: Web, App (API), Wachenterminal
- Nachweis: nein
- Frist technisch: keine automatische Löschung; Löschung zusammen mit dem Vorgang laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `defect` |  | Verweis |  |
| `station` |  | Verweis |  |
| `filename` |  | Freitext |  |
| `content_type` |  | Wert |  |
| `data` |  | Datei/Bild |  |
| `size` |  | Wert |  |
| `uploaded_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.DefectEvent

Verlauf: Statuswechsel mit Person

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: System
- Zugriffswege: Web, App (API), Wachenterminal
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `defect` |  | Verweis |  |
| `station` |  | Verweis |  |
| `kind` |  | Auswahl |  |
| `from_status` |  | Wert |  |
| `to_status` |  | Wert |  |
| `actor` |  | Person (Konto) |  |
| `metadata` |  | strukturierte Angaben |  |
| `created_at` |  | Zeitpunkt |  |

<a id="modul-geraete"></a>

## Geräte, Status und Ausgabe

Einsatzbereitschaft von Geräten und Ausgabe von Gegenständen (Funk, Schlüssel).

- Schalter: immer aktiv
- Bereiche: `/geraete/`, `/auswertung/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Ausgabeliste: wer hat welchen Gegenstand | `assets_inventory_web` | Inhaltsrollen | **ja** |  |
| Ausgabeliste mit Namen (App) | `api_v1_inventory` | Inhaltsrollen | **ja** |  |
| Kennzahlen der Wache; je Person nur die eigenen Quittierungen | `wachalltag_reports_web` | Inhaltsrollen | nein |  |
| Kennzahlen der Wache (App) | `api_v1_reports` | Inhaltsrollen | nein |  |

### core.AssetEvent

Statusverlauf mit Person

- Lesen: Inhaltsrollen
- Schreiben: System
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `asset` |  | Verweis |  |
| `station` |  | Verweis |  |
| `from_status` |  | Wert |  |
| `to_status` |  | Wert |  |
| `note` |  | Freitext |  |
| `actor` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.InventoryEvent

Ausgabe und Rückgabe mit Person

- Lesen: Inhaltsrollen
- Schreiben: System
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `item` |  | Verweis |  |
| `station` |  | Verweis |  |
| `action` |  | Auswahl |  |
| `actor` |  | Person (Konto) |  |
| `holder` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.InventoryItem

Ausgabegegenstand mit aktueller Inhaberin oder aktuellem Inhaber

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `item_id` |  | Wert |  |
| `label` |  | Freitext |  |
| `kind` |  | Auswahl |  |
| `holder` |  | Person (Konto) |  |
| `checked_out_at` |  | Zeitpunkt |  |
| `note` |  | Freitext |  |
| `updated_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.StationAsset

Gerät mit Status und Notiz

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `asset_id` |  | Wert |  |
| `label` |  | Freitext |  |
| `kind` |  | Auswahl |  |
| `status` |  | Auswahl |  |
| `note` |  | Freitext |  |
| `updated_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

<a id="modul-kalender"></a>

## Kalender

Termine der Wache, auch als Kalender-Abo.

- Schalter: `Station.calendar_enabled`
- Bereiche: `/kalender/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Kalender als ICS-Datei | `calendar_feed_ics` | Inhaltsrollen | nein |  |
| Kalender-Abo über geheimen Link (ohne Anmeldung) | `calendar_feed_token_ics` | öffentlich | nein | Termine der Wache ohne Personen; der Link wirkt wie ein Passwort |
| Einzeltermin als ICS-Datei | `calendar_event_ics` | Inhaltsrollen | nein |  |

### core.CalendarEvent

Termin: Titel, Beschreibung, Zeit, Autor

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto), Wachen-Display
- Schreiben: Schichtleitung, Master-Admin
- Zugriffswege: Web, App (API), Wachenterminal, Display, Export/Datei, Django-Admin (lesen)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `title` |  | Freitext |  |
| `description` |  | Freitext |  |
| `starts_at` |  | Zeitpunkt |  |
| `ends_at` |  | Zeitpunkt |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.CalendarFeedToken

Geheime Links für Kalender-Abos

- Lesen: Schichtleitung, Master-Admin
- Schreiben: Schichtleitung, Master-Admin
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: gilt bis Ablauf oder Widerruf; widerrufene und abgelaufene Einträge bleiben ohne technische Löschung
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `token` |  | Geheimnis/Prüfwert |  |
| `label` |  | Freitext |  |
| `created_by` |  | Person (Konto) |  |
| `is_active` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `last_used_at` |  | Zeitpunkt |  |

<a id="modul-muellkalender"></a>

## Müllkalender

Abholtermine aus einer ICS-Adresse der Gemeinde.

- Schalter: `Station.waste_calendar_enabled`

### core.WasteCollection

Abholtermin: Titel und Zeit

- Lesen: Inhaltsrollen, Wachen-Display
- Schreiben: System
- Zugriffswege: Web, Display, Django-Admin (lesen)
- Nachweis: nein
- Frist technisch: werden bei jedem Abgleich des Müllkalenders ersetzt
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `title` |  | Freitext |  |
| `starts_at` |  | Zeitpunkt |  |
| `ends_at` |  | Zeitpunkt |  |
| `created_at` |  | Zeitpunkt |  |

<a id="modul-geburtstage"></a>

## Geburtstage (freiwillig)

Freiwillige Anzeige von Tag und Monat, nie das Geburtsjahr.

- Schalter: `Station.birthdays_enabled`
- Bereiche: `/geburtstage/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Liste der freigegebenen Geburtstage mit Namen | `birthdays` | Inhaltsrollen | **ja** |  |

### core.BirthdayPreference

Tag und Monat mit Einwilligung und Widerruf

- Lesen: Inhaltsrollen, Wachen-Display
- Schreiben: die Person selbst
- Zugriffswege: Web, Display, Django-Admin (lesen)
- Nachweis: nein
- Frist technisch: beim Widerruf sofort entfernt (Geburtstag: Tag und Monat geleert; Signal: Nummer gelöscht)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Display und Sperrbildschirm des Terminals: Vorname und Anfangsbuchstabe am Tag selbst.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `station` |  | Verweis |  |
| `day` |  | persönliche Angabe | freiwillig, nur mit Einwilligung |
| `month` |  | persönliche Angabe | freiwillig, nur mit Einwilligung |
| `is_visible` |  | Wert |  |
| `consented_at` |  | Zeitpunkt |  |
| `withdrawn_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

<a id="modul-kaffeekasse"></a>

## Kaffeekasse (freiwillig)

Gemeinschaftskasse mit Monatsbeiträgen und Kassenbuch (docs/KAFFEEKASSE.md).

- Schalter: `Station.coffee_enabled`
- Bereiche: `/kaffeekasse/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Mappe: Stand aller Teilnehmenden | `coffee_book` | Kassenwart | **ja** |  |
| Buchungen aller Teilnehmenden | `coffee_ledger` | Kassenwart | **ja** |  |
| Teilnehmendenliste | `coffee_participants` | Kassenwart, Master-Admin | **ja** |  |
| Export aller Buchungen als CSV | `coffee_export` | Kassenwart | **ja** |  |

### core.CoffeeCashMovement

Kassenbewegung und Kassensturz mit Person

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, Export/Datei
- Nachweis: ja, append-only (Datenbankrechte)
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Append-only. Einkäufe können alle Inhaltsrollen erfassen.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `pot` |  | Auswahl |  |
| `kind` |  | Auswahl |  |
| `amount_cents` |  | Wert |  |
| `reason` |  | Freitext |  |
| `counted_cents` |  | Wert |  |
| `expected_cents` |  | Wert |  |
| `witness` |  | Person (Konto) |  |
| `created_by` |  | Person (Konto) |  |
| `correction_of` |  | Verweis |  |
| `created_at` |  | Zeitpunkt |  |

### core.CoffeeEntry

Buchung: Person, Betrag, Art, Monat, erfasst von

- Lesen: die Person selbst, Kassenwart
- Schreiben: Kassenwart, die Person selbst
- Zugriffswege: Web, App (API), Export/Datei, Django-Admin (lesen)
- Nachweis: ja, append-only (Datenbankrechte)
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Append-only. Jede Person sieht ihre eigenen Buchungen, der Kassenwart alle.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `member` |  | Person (Konto) |  |
| `amount_cents` |  | Wert |  |
| `reason` |  | Freitext |  |
| `kind` |  | Auswahl |  |
| `method` |  | Auswahl |  |
| `period` |  | Zeitpunkt |  |
| `created_by` |  | Person (Konto) |  |
| `correction_of` |  | Verweis |  |
| `created_at` |  | Zeitpunkt |  |

### core.CoffeeFund

Einstellungen der Kasse (Beitrag, Kontoinhaber, Erinnerungen)

- Lesen: Inhaltsrollen
- Schreiben: Kassenwart, Master-Admin
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `station` |  | Verweis |  |
| `monthly_fee_cents` | Monatsbeitrag in Cent | Wert |  |
| `reminder_day` | Erinnerung ab Tag | Wert |  |
| `account_holder` | Kontoinhaber für Überweisungen | Kontakt/Name |  |
| `email_reminder` | Monatliche Erinnerung per E-Mail | Wert |  |
| `signal_group_reminder` | Monatliche Erinnerung in die Signal-Gruppe | Wert |  |
| `signal_group_counts` | Kassensturz-Ergebnis in die Signal-Gruppe | Wert |  |
| `updated_at` |  | Zeitpunkt |  |
| `updated_by` |  | Person (Konto) |  |

### core.CoffeeParticipant

Teilnahme mit Zeitraum und E-Mail-Wunsch

- Lesen: die Person selbst, Kassenwart, Master-Admin
- Schreiben: Kassenwart, Master-Admin, die Person selbst
- Zugriffswege: Web, E-Mail
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `user` |  | Person (Konto) |  |
| `since` | Beitrag ab Monat | Zeitpunkt |  |
| `until` | Beitrag bis Monat | Zeitpunkt |  |
| `email_reminders` | Erinnerung per E-Mail | Wert |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

<a id="modul-aufgaben"></a>

## Tagesaufgaben

Wiederkehrende Aufgaben der Wache mit Erledigt-Vermerk.

- Schalter: `Station.tasks_enabled`
- Bereiche: `/aufgaben/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Tagesansicht mit Vorname der erledigenden Person und Uhrzeit | `tasks_today` | Inhaltsrollen, Wachenterminal (Dienstkonto) | **ja** |  |
| Wochenansicht mit erledigender Person | `tasks_week` | Inhaltsrollen, Wachenterminal (Dienstkonto) | **ja** |  |

### core.StationTask

Aufgabe mit Wiederholung

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto), Wachen-Display
- Schreiben: Schichtleitung, Master-Admin
- Zugriffswege: Web, Wachenterminal, Display, Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `title` |  | Freitext |  |
| `band` |  | Auswahl |  |
| `weekday` |  | Auswahl |  |
| `color` |  | Wert |  |
| `repeat` |  | Auswahl |  |
| `repeat_interval` |  | Wert |  |
| `weekdays` |  | Wert |  |
| `month_day` |  | Wert |  |
| `start_date` |  | Zeitpunkt |  |
| `end_date` |  | Zeitpunkt |  |
| `due_date` |  | Zeitpunkt |  |
| `notes` |  | Freitext |  |
| `sort_order` |  | Wert |  |
| `is_active` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.StationTaskCompletion

Erledigt-Vermerk: Person, Tag, Uhrzeit, Notiz

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto), Wachen-Display
- Schreiben: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Zugriffswege: Web, Wachenterminal, Display, Django-Admin (lesen)
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Display: nur Zählwerte. Am Wachenterminal erledigte Aufgaben tragen das Dienstkonto, keine Person.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `task` |  | Verweis |  |
| `station` |  | Verweis |  |
| `work_date` |  | Zeitpunkt |  |
| `completed_by` |  | Person (Konto) |  |
| `completed_at` |  | Zeitpunkt |  |
| `note` |  | Freitext |  |

<a id="modul-checklisten"></a>

## Checklisten und Prüfintervalle

Checklisten mit Abschluss und Fälligkeit.

- Schalter: `Station.checklists_enabled`
- Bereiche: `/checklisten/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Letzter Abschluss je Checkliste mit Vorname und Zeit | `checklists` | Inhaltsrollen, Wachenterminal (Dienstkonto) | **ja** |  |

### core.Checklist

Checkliste mit Beschreibung

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Schichtleitung, Master-Admin, Superuser (Django-Admin)
- Zugriffswege: Web, App (API), Wachenterminal, Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `title` |  | Freitext |  |
| `description` |  | Freitext |  |
| `is_active` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |

### core.ChecklistCompletion

Abschluss: Person, Zeit, Notiz

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Zugriffswege: Web, App (API), Wachenterminal, Django-Admin (lesen)
- Nachweis: ja, append-only (Datenbankrechte)
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Append-only.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `checklist` |  | Verweis |  |
| `completed_by` |  | Person (Konto) |  |
| `note` |  | Freitext |  |
| `created_at` |  | Zeitpunkt |  |

### core.ChecklistItem

Punkte einer Checkliste

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Schichtleitung, Master-Admin, Superuser (Django-Admin)
- Zugriffswege: Web, App (API), Wachenterminal, Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `checklist` |  | Verweis |  |
| `text` |  | Freitext |  |
| `position` |  | Wert |  |

### core.ChecklistSchedule

Prüfintervall und nächste Fälligkeit

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Schichtleitung, Master-Admin
- Zugriffswege: Web, App (API), Wachenterminal
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Die Seite /checklisten/intervalle/ hängt nicht am Modulschalter.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `checklist` |  | Verweis |  |
| `station` |  | Verweis |  |
| `interval` |  | Auswahl |  |
| `due_next` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

<a id="modul-lage"></a>

## Meldungen, Verkehr und Wetter

Öffentliche Meldungen aus eingetragenen Quellen.

- Schalter: `Station.feeds_enabled`
- Bereiche: `/lage/`

### core.FeedItem

Meldung aus einer Quelle

- Lesen: Inhaltsrollen
- Schreiben: System
- Zugriffswege: Web, Django-Admin (lesen)
- Nachweis: nein
- Frist technisch: 90 Tage nach dem letzten Abruf (RETENTION_FEED_DAYS, `housekeeping`)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `source` |  | Verweis |  |
| `external_id` |  | Freitext |  |
| `title` |  | Freitext |  |
| `summary` |  | Freitext |  |
| `url` |  | Link |  |
| `published_at` |  | Zeitpunkt |  |
| `starts_on` |  | Zeitpunkt |  |
| `ends_on` |  | Zeitpunkt |  |
| `first_imported_at` |  | Zeitpunkt |  |
| `last_seen_at` |  | Zeitpunkt |  |

### core.FeedSource

Quelle: Name, Adresse, Abrufstatus

- Lesen: Inhaltsrollen
- Schreiben: Superuser (Django-Admin)
- Zugriffswege: Web, Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: solange die Installation besteht; Änderung durch Master-Admin
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `name` |  | Freitext |  |
| `url` |  | Link |  |
| `kind` |  | Auswahl |  |
| `locality` |  | Wert |  |
| `attribution` |  | Freitext |  |
| `is_enabled` |  | Wert |  |
| `last_success_at` |  | Zeitpunkt |  |
| `last_error_at` |  | Zeitpunkt |  |
| `last_error` |  | Freitext |  |

<a id="modul-pinnwand"></a>

## Pinnwand

Aushänge der Wache.

- Schalter: `Station.pinboard_enabled`
- Bereiche: `/pinnwand/`

### core.PinboardAttachment

Anhänge (Bild oder PDF)

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Schreiben: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Zugriffswege: Web, Wachenterminal
- Nachweis: nein
- Frist technisch: keine automatische Löschung; Löschung zusammen mit dem Vorgang laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `note` |  | Verweis |  |
| `station` |  | Verweis |  |
| `filename` |  | Freitext |  |
| `content_type` |  | Wert |  |
| `data` |  | Datei/Bild |  |
| `size` |  | Wert |  |
| `uploaded_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.PinboardNote

Aushang: Titel, Text, Kategorie, Autor

- Lesen: Inhaltsrollen, Wachenterminal (Dienstkonto), Wachen-Display
- Schreiben: Inhaltsrollen, Wachenterminal (Dienstkonto)
- Zugriffswege: Web, App (API), Wachenterminal, Display
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Anpinnen: Schichtleitung und Master-Admin. Archivierte Aushänge bleiben gespeichert. Display: nur Titel angepinnter Aushänge.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `author` |  | Person (Konto) |  |
| `title` |  | Freitext |  |
| `body` |  | Freitext |  |
| `category` |  | Auswahl |  |
| `is_pinned` |  | Wert |  |
| `is_archived` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

<a id="modul-chat"></a>

## Wachenchat, Privatnachrichten und Post (E2EE)

Nachrichten unter Kolleginnen und Kollegen, Ende-zu-Ende-verschlüsselt (docs/SECURITY-PRIVACY.md).

- Schalter: `Station.chat_enabled`
- Bereiche: `/chat/`, `/post/`, `/konto/crypto/`
- Hinweis: Der Server speichert verschlüsselte Inhalte; der ausgelieferte Webclient und der Server bleiben Teil des Vertrauensmodells.

### core.ChatGroup

Gruppe: Name und anlegende Person

- Lesen: die Person selbst
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `name` |  | Freitext |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.ChatGroupMember

Gruppenmitglieder

- Lesen: die Person selbst
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `group` |  | Verweis |  |
| `user` |  | Person (Konto) |  |
| `added_at` |  | Zeitpunkt |  |

### core.ChatMessage

Wachenchat-Nachricht (verschlüsselt, Autor, Zeit)

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Ausblenden: Schichtleitung und Master-Admin.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `author` |  | Person (Konto) |  |
| `body` |  | Freitext | nur bei unverschlüsselten Altnachrichten; neue Nachrichten stehen verschlüsselt in ciphertext |
| `ciphertext` |  | verschlüsselt |  |
| `nonce` |  | verschlüsselt |  |
| `key_wraps` |  | verschlüsselt |  |
| `algo` |  | Wert |  |
| `is_encrypted` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `is_hidden` |  | Wert |  |

### core.GroupMessage

Gruppennachricht (verschlüsselt)

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `group` |  | Verweis |  |
| `author` |  | Person (Konto) |  |
| `ciphertext` |  | verschlüsselt |  |
| `nonce` |  | verschlüsselt |  |
| `key_wraps` |  | verschlüsselt |  |
| `algo` |  | Wert |  |
| `is_hidden` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |

### core.PrivateConversation

Privater Verlauf zwischen zwei Personen

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `user_low` |  | Person (Konto) |  |
| `user_high` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.PrivateMessage

Privatnachricht (verschlüsselt)

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `conversation` |  | Verweis |  |
| `author` |  | Person (Konto) |  |
| `ciphertext` |  | verschlüsselt |  |
| `nonce` |  | verschlüsselt |  |
| `key_wraps` |  | verschlüsselt |  |
| `algo` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `is_hidden` |  | Wert |  |

### core.SecureMail

Post (verschlüsselt) mit Absender

- Lesen: die Person selbst
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `sender` |  | Person (Konto) |  |
| `ciphertext` |  | verschlüsselt |  |
| `nonce` |  | verschlüsselt |  |
| `key_wraps` |  | verschlüsselt |  |
| `algo` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |

### core.SecureMailRecipient

Empfänger und Lesezeit

- Lesen: die Person selbst
- Schreiben: System
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `mail` |  | Verweis |  |
| `user` |  | Person (Konto) |  |
| `read_at` |  | Zeitpunkt |  |

### core.UserCryptoIdentity

Schlüsselpaar (privater Schlüssel nur verschlüsselt)

- Lesen: Inhaltsrollen, die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: solange das Konto besteht; Deaktivieren oder Löschen durch Master-Admin bzw. Superuser
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Den öffentlichen Schlüssel sehen Inhaltsrollen derselben Wache.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `public_jwk` |  | Schlüssel (öffentlich) |  |
| `wrapped_private_jwk` |  | verschlüsselt |  |
| `kdf_salt` |  | Geheimnis/Prüfwert |  |
| `kdf_iterations` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

<a id="modul-benachrichtigungen"></a>

## Benachrichtigungen und Push

Hinweise im Posteingang, Push an Browser und App.

- Schalter: immer aktiv
- Bereiche: `/benachrichtigungen/`, `/hinweise/`

### core.MobilePushDevice

App-Gerät für Push (Plattform, Geräte-Token, App-Version)

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: App (API)
- Nachweis: nein
- Frist technisch: beim Abmelden des Geräts oder wenn der Push-Dienst die Adresse als ungültig meldet
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `station` |  | Verweis |  |
| `platform` |  | Auswahl |  |
| `token` |  | Geheimnis/Prüfwert | Geräte-Token für Apple oder Google |
| `app_version` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `last_seen_at` |  | Zeitpunkt |  |

### core.PushOutbox

Warteschlange für Push-Nachrichten

- Lesen: System
- Schreiben: System
- Zugriffswege: Push
- Nachweis: nein
- Frist technisch: versendete oder verworfene Nachrichten nach 30 Tagen (`housekeeping`)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `user` |  | Person (Konto) |  |
| `subscription` |  | Verweis |  |
| `device` |  | Verweis |  |
| `payload` |  | strukturierte Angaben |  |
| `status` |  | Auswahl |  |
| `attempts` |  | Wert |  |
| `last_attempt_at` |  | Zeitpunkt |  |
| `next_attempt_at` |  | Zeitpunkt |  |
| `created_at` |  | Zeitpunkt |  |
| `sent_at` |  | Zeitpunkt |  |
| `error_message` |  | Freitext |  |

### core.PushSubscription

Browser-Push-Abo (Adresse beim Browserhersteller, Schlüssel, Browser)

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: beim Abmelden des Geräts oder wenn der Push-Dienst die Adresse als ungültig meldet
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `station` |  | Verweis |  |
| `endpoint` |  | Netzwerk/Gerät | Push-Adresse beim Browserhersteller |
| `p256dh` |  | Geheimnis/Prüfwert | Schlüssel des Push-Abos |
| `auth` |  | Geheimnis/Prüfwert | Schlüssel des Push-Abos |
| `user_agent` |  | Netzwerk/Gerät |  |
| `created_at` |  | Zeitpunkt |  |

### core.UserNotification

Persönlicher Hinweis: Titel, Text, Link, gelesen

- Lesen: die Person selbst
- Schreiben: System
- Zugriffswege: Web, App (API), Push
- Nachweis: nein
- Frist technisch: keine technische Löschung (siehe docs/LOESCHKONZEPT.md, Lücken)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `user` |  | Person (Konto) |  |
| `kind` |  | Auswahl |  |
| `title` |  | Freitext |  |
| `body` |  | Freitext |  |
| `url` |  | Freitext |  |
| `dedupe_key` |  | Freitext |  |
| `created_at` |  | Zeitpunkt |  |
| `read_at` |  | Zeitpunkt |  |

<a id="modul-signal"></a>

## Signal-Benachrichtigungen

Erinnerungen über Signal an Personen, die ihre Nummer selbst bestätigt haben (docs/SIGNAL.md).

- Schalter: Einstellung SIGNAL_API_URL und SIGNAL_NUMBER
- Bereiche: `/konto/signal/`, `/einstellungen/signal/`

### core.SignalContact

Signal-Nummer mit Bestätigung

- Lesen: die Person selbst
- Schreiben: die Person selbst
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: beim Widerruf sofort entfernt (Geburtstag: Tag und Monat geleert; Signal: Nummer gelöscht)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `user` |  | Person (Konto) |  |
| `number` |  | Kontakt/Name | Telefonnummer, erst nach Bestätigung genutzt |
| `verified_at` |  | Zeitpunkt |  |
| `code_hash` |  | Geheimnis/Prüfwert |  |
| `code_expires_at` |  | Zeitpunkt |  |
| `code_attempts` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |

### core.SignalOutbox

Warteschlange: Empfänger und Nachrichtentext

- Lesen: Superuser (Django-Admin)
- Schreiben: System
- Zugriffswege: Signal, Django-Admin (lesen)
- Nachweis: nein
- Frist technisch: gesendete Nachrichten nach 30 Tagen (Signal-Worker)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `recipient` |  | Kontakt/Name | Telefonnummer oder Gruppen-ID |
| `message` |  | Freitext |  |
| `dedupe_key` |  | Freitext |  |
| `created_at` |  | Zeitpunkt |  |
| `next_attempt_at` |  | Zeitpunkt |  |
| `sent_at` |  | Zeitpunkt |  |
| `attempts` |  | Wert |  |
| `last_error` |  | Freitext |  |

<a id="modul-mpg"></a>

## Medizinprodukte (MPBetreibV)

Bestandsverzeichnis, Prüffristen, Funktionskontrollen und Einweisungen.

- Schalter: `Station.mpg_enabled`
- Bereiche: `/mpg/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Letzte Prüfungen und Funktionskontrollen mit Namen | `mpg_dashboard` | Inhaltsrollen | **ja** |  |
| Einweisungen und Kontrollen eines Geräts mit Namen | `mpg_device_detail` | Inhaltsrollen | **ja** |  |
| Einweisungsmatrix aller Mitglieder mit Quote je Person | `mpg_geraetepass` | Inhaltsrollen | **ja** | für alle Inhaltsrollen sichtbar |
| Bestandsverzeichnis als CSV (ohne Personen) | `mpg_export_bestandsverzeichnis` | Inhaltsrollen | nein |  |

### core.DeviceRoutineCheck

Funktionskontrolle mit Person und Ergebnis

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `device` |  | Verweis |  |
| `performed_by` |  | Person (Konto) |  |
| `checked_at` |  | Zeitpunkt |  |
| `passed` | Funktionskontrolle bestanden | Wert |  |
| `battery_ok` | Akkus / Energieversorgung einsatzklar | Wert |  |
| `visual_ok` | Sichtprüfung / Zubehör vollständig | Wert |  |
| `function_ok` | Selbsttest / Funktionsprüfung OK | Wert |  |
| `notes` | Feststellungen / Notiz | Freitext |  |

### core.DeviceTrainingRecord

Einweisung: Person, einweisende Person, Datum

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `device` |  | Verweis |  |
| `trainee` |  | Person (Konto) |  |
| `instructor` | Einweiser / Gerätebeauftragter (§ 11 MPBetreibV) | Kontakt/Name | Name der einweisenden Person als Text |
| `trained_at` | Schulungsdatum | Zeitpunkt |  |
| `notes` | Bemerkung | Freitext |  |
| `created_at` |  | Zeitpunkt |  |

### core.MaintenanceLog

STK/MTK/DGUV-Prüfung mit prüfender Stelle

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `device` |  | Verweis |  |
| `station` |  | Verweis |  |
| `kind` | Prüfungsart | Auswahl |  |
| `performed_at` | Prüfungsdatum | Zeitpunkt |  |
| `performed_by` | Prüfer / Medizintechnik-Fachbetrieb | Kontakt/Name | Name der prüfenden Person oder Firma als Text |
| `passed` | Bestanden (Keine Sicherheitsmängel) | Wert |  |
| `next_due_date` | Nächste Fälligkeit | Zeitpunkt |  |
| `findings` | Prüfbefund / Festgestellte Mängel | Freitext |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |

### core.MedicalDevice

Medizingerät mit Fristen und Status

- Lesen: Inhaltsrollen, Wachen-Display
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, Display, Export/Datei
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `slug` |  | Wert |  |
| `name` | Gerätebezeichnung | Freitext |  |
| `category` | Gerätekategorie | Auswahl |  |
| `risk_class` | Risikoklasse | Auswahl |  |
| `manufacturer` | Hersteller | Freitext |  |
| `model_type` | Typ / Modell | Freitext |  |
| `serial_number` | Seriennummer | Freitext |  |
| `inventory_number` | Inventarnummer / Barcode | Wert |  |
| `udi_di` | UDI-DI (GTIN) | Wert |  |
| `ce_notified_body` | CE-Kennnummer (z. B. 0123) | Wert |  |
| `year_of_manufacture` | Baujahr | Wert |  |
| `acquired_at` | Anschaffungsdatum | Zeitpunkt |  |
| `decommissioned_at` | Außerbetriebnahme | Zeitpunkt |  |
| `location` | Standort / Fahrzeug | Freitext |  |
| `current_status` | Betriebsstatus | Auswahl |  |
| `status_note` | Status-Bemerkung | Freitext |  |
| `is_anlage_1` | Anlage 1 MPBetreibV (STK-Pflicht) | Wert |  |
| `is_anlage_2` | Anlage 2 MPBetreibV (MTK-Pflicht) | Wert |  |
| `stk_interval_months` | STK-Intervall (Monate) | Wert |  |
| `mtk_interval_months` | MTK-Intervall (Monate) | Wert |  |
| `dguv_interval_months` | DGUV V3 Intervall (Monate) | Wert |  |
| `next_stk_date` | Nächste STK | Zeitpunkt |  |
| `next_mtk_date` | Nächste MTK | Zeitpunkt |  |
| `next_dguv_date` | Nächste DGUV V3 | Zeitpunkt |  |
| `last_routine_check` | Letzter Funktionscheck | Zeitpunkt |  |
| `manual_url` | Online-Bedienungsanleitung | Link |  |
| `notes` | Hinweise / Medizinproduktebuch-Notizen | Freitext |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

<a id="modul-lager"></a>

## Lager und Material

Artikel, Chargen, Bestände und Bewegungen (FEFO, Kühlware, Rückruf).

- Schalter: `Station.warehouse_enabled`
- Bereiche: `/lager/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Letzte Bewegungen mit Namen | `warehouse_dashboard` | Inhaltsrollen | **ja** |  |
| Bewegungen eines Artikels mit Namen | `warehouse_item_detail` | Inhaltsrollen | **ja** |  |
| Verfallsliste als CSV (ohne Personen) | `warehouse_export_fefo` | Inhaltsrollen | nein |  |
| Nachbestellvorschlag (ohne Personen) | `warehouse_reorder_proposal` | Inhaltsrollen | nein |  |

### core.ItemBatch

Charge mit Verfall und Rückruf

- Lesen: Inhaltsrollen, Wachen-Display
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, Display, Export/Datei
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `item` |  | Verweis |  |
| `station` |  | Verweis |  |
| `batch_number` | Chargennummer (Lot) | Wert |  |
| `manufacturer_exp_date` | Hersteller-MHD (aufgedruckt) | Zeitpunkt |  |
| `out_of_fridge_date` | Datum der Kühlkettenunterbrechung | Zeitpunkt |  |
| `calculated_exp_date` | Effektives Verfallsdatum | Zeitpunkt |  |
| `is_recalled` | Charge zurückgerufen / gesperrt | Wert |  |
| `recall_reason` | Rückrufgrund | Freitext |  |
| `created_at` |  | Zeitpunkt |  |

### core.MedicalItem

Artikel mit Mindestbestand

- Lesen: Inhaltsrollen, Wachen-Display
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, Display
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `slug` |  | Wert |  |
| `name` | Artikelbezeichnung | Freitext |  |
| `category` |  | Auswahl |  |
| `unit` | Einheit | Auswahl |  |
| `pzn` | PZN (Pharmazentralnummer) | Wert |  |
| `gtin` | GTIN / EAN | Wert |  |
| `min_stock` | Mindestbestand Wache | Wert |  |
| `target_stock` | Sollbestand Wache | Wert |  |
| `requires_cooling` | Kühlpflichtig (2–8 °C) | Wert |  |
| `room_temp_max_days` | Max. Tage bei Raumtemperatur | Wert |  |
| `notes` | Dosierung / Lagerhinweise | Freitext |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.StockItem

Bestand je Lagerort

- Lesen: Inhaltsrollen, Wachen-Display
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, Display
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Display: nur Summe für den Mindestbestand.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `item` |  | Verweis |  |
| `batch` |  | Verweis |  |
| `location` |  | Verweis |  |
| `quantity` | Menge | Wert |  |
| `updated_at` |  | Zeitpunkt |  |

### core.StockMovement

Bewegung: Menge, Art, Person

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: ja, append-only (Datenbankrechte)
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Append-only. Nur Bestand, kein Verbrauch je Einsatz.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `item` |  | Verweis |  |
| `batch` |  | Verweis |  |
| `source_location` | Von Lagerort | Verweis |  |
| `target_location` | Nach Lagerort | Verweis |  |
| `quantity` | Menge | Wert |  |
| `kind` | Buchungsart | Auswahl |  |
| `actor` |  | Person (Konto) |  |
| `note` | Grund / Beleg | Freitext |  |
| `created_at` |  | Zeitpunkt |  |

### core.StorageLocation

Lagerort

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `slug` |  | Wert |  |
| `name` | Lagerort-Bezeichnung | Freitext |  |
| `kind` |  | Auswahl |  |
| `is_cold_storage` | Kühlpflichtiger Lagerort (Kühlschrank) | Wert |  |
| `parent` | Übergeordneter Lagerort | Verweis |  |
| `description` |  | Freitext |  |
| `created_at` |  | Zeitpunkt |  |

<a id="modul-fuhrpark"></a>

## Fuhrpark

Fahrzeuge, Fristen, Übernahme und Desinfektion.

- Schalter: `Station.fleet_enabled`
- Bereiche: `/fuhrpark/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Letzte Desinfektionen mit Namen | `fleet_dashboard` | Inhaltsrollen | **ja** |  |
| Übernahmen und Desinfektionen eines Fahrzeugs mit Namen | `fleet_vehicle_detail` | Inhaltsrollen | **ja** |  |
| Fahrzeugliste als CSV (ohne Personen) | `fleet_export_csv` | Inhaltsrollen | nein |  |

### core.DisinfectantMaster

Desinfektionsmittel

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen, Superuser (Django-Admin)
- Zugriffswege: Web, Django-Admin (lesen, anlegen, ändern, löschen)
- Nachweis: nein
- Frist technisch: solange die Installation besteht; Änderung durch Master-Admin
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `name` | Handelsname | Freitext |  |
| `manufacturer` | Hersteller | Freitext |  |
| `spectrum` | Wirkspektrum | Freitext |  |
| `default_exposure_minutes` | Standard-Einwirkzeit (Minuten) | Wert |  |
| `is_vah_listed` | VAH-gelistet | Wert |  |

### core.DisinfectionProtocol

Desinfektion: Fahrzeug, Mittel, Person, Beginn, Einwirkzeit

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `vehicle` |  | Verweis |  |
| `performed_by` |  | Person (Konto) |  |
| `disinfectant` |  | Verweis |  |
| `kind` |  | Auswahl |  |
| `started_at` | Beginn Desinfektion | Zeitpunkt |  |
| `exposure_minutes` | Einwirkzeit (Minuten) | Wert |  |
| `lock_timer_applied` | Einwirkzeit-Sperre angewendet | Wert |  |
| `notes` | Bemerkung (keine Patienten- oder Einsatzangaben) | Freitext |  |

### core.Vehicle

Fahrzeug mit Zustand, Füllständen und Fristen

- Lesen: Inhaltsrollen, Wachen-Display
- Schreiben: Inhaltsrollen
- Zugriffswege: Web, App (API), Display, Export/Datei
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `slug` |  | Wert |  |
| `call_sign` | Funkrufname (OPTA) | Freitext |  |
| `license_plate` | Amtliches Kennzeichen | Wert |  |
| `vehicle_type` |  | Auswahl |  |
| `chassis_manufacturer` | Fahrgestell | Freitext |  |
| `body_manufacturer` | Kofferaufbau | Freitext |  |
| `year_of_manufacture` | Baujahr | Wert |  |
| `tactical_status` |  | Auswahl |  |
| `status_note` | Status-Bemerkung | Freitext |  |
| `current_mileage` | Kilometerstand (km) | Wert |  |
| `fuel_level_percent` | Kraftstoff (%) | Wert |  |
| `adblue_level_percent` | AdBlue (%) | Wert |  |
| `o2_pressure_bar` | Sauerstoffdruck (bar) | Wert |  |
| `next_hu_date` | Nächste Hauptuntersuchung (§ 29 StVZO) | Zeitpunkt |  |
| `next_sp_date` | Nächste Sicherheitsprüfung (SP) | Zeitpunkt |  |
| `next_uvv_date` | Nächste UVV-Prüfung (DGUV V70) | Zeitpunkt |  |
| `next_stretcher_service_date` | Tragentisch-Wartung (10g / DIN EN 1789) | Zeitpunkt |  |
| `last_disinfection` | Letzte Desinfektion | Zeitpunkt |  |
| `disinfection_locked_until` | Desinfektions-Sperre aktiv bis | Zeitpunkt |  |
| `is_active` | Im aktiven Wachdienst | Wert |  |
| `notes` | Fahrzeugakte / Besonderheiten | Freitext |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.VehicleHandover

Fahrzeugübernahme: Person, Kilometerstand, Füllstände, Prüfpunkte

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `vehicle` |  | Verweis |  |
| `crew_member` |  | Person (Konto) |  |
| `performed_at` |  | Zeitpunkt |  |
| `mileage` | Kilometerstand | Wert |  |
| `fuel_percent` | Tankfüllstand (%) | Wert |  |
| `adblue_percent` | AdBlue (%) | Wert |  |
| `o2_pressure_bar` | Sauerstoffdruck (bar) | Wert |  |
| `btm_seal_intact` | BTM-Plombe unversehrt | Wert |  |
| `medical_devices_checked` | Medizingeräte-Selbsttests OK | Wert |  |
| `vehicle_clean` | Patientenraum & Fahrerkabine sauber | Wert |  |
| `notes` | Feststellungen / Bemerkung | Freitext |  |

<a id="modul-orga"></a>

## Dienstanweisungen und Telefonbuch

Dienstanweisungen mit Version und Lesequittung, Telefonbuch der Wache.

- Schalter: `Station.orga_enabled`
- Bereiche: `/orga/`

**Auswertungen und Personenlisten**

| Ausgabe | URL-Name | Rollen | Personenbezug | Hinweis |
| --- | --- | --- | --- | --- |
| Quittierungsliste einer Dienstanweisung mit Namen | `sop_detail` | Schichtleitung, Master-Admin | **ja** |  |
| Quittierungsnachweis als CSV mit Namen | `sop_export_audit` | Schichtleitung, Master-Admin | **ja** |  |

### core.SOPDocument

Dienstanweisung: Nummer, Titel, Status, Fristen

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `slug` |  | Wert |  |
| `doc_number` | Dokumentennummer | Wert |  |
| `title` | Titel der Dienstanweisung | Freitext |  |
| `category` |  | Auswahl |  |
| `status` |  | Auswahl |  |
| `current_version` | Aktuelle Version | Wert |  |
| `valid_from` | Gültig ab | Zeitpunkt |  |
| `review_due_date` | Nächste Überprüfung (QM) | Zeitpunkt |  |
| `requires_acknowledgment` | Pflichtquittierung für Personal | Wert |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `updated_at` |  | Zeitpunkt |  |

### core.SOPReceipt

Lesequittung: Person, Version, Zeit

- Lesen: die Person selbst, Schichtleitung, Master-Admin
- Schreiben: die Person selbst
- Zugriffswege: Web, Export/Datei
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Mitglieder sehen nur ihren eigenen Stand.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `sop` |  | Verweis |  |
| `revision` |  | Verweis |  |
| `user` |  | Person (Konto) |  |
| `acknowledged_at` | Quittiert am | Zeitpunkt |  |
| `ip_address` | IP-Adresse | Netzwerk/Gerät | seit 0.26.1 nicht mehr befüllt; Altwerte entfernt der einmalige Bereinigungsbefehl (Paket C, D1); Sicherungen behalten sie bis zum Ablauf |
| `user_agent` | Browser / Gerät | Netzwerk/Gerät | seit 0.26.1 nicht mehr befüllt; Altwerte entfernt der einmalige Bereinigungsbefehl (Paket C, D1); Sicherungen behalten sie bis zum Ablauf |

### core.SOPRevision

Version mit Text, Prüfsumme und Freigabe

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: ja
- Frist technisch: keine Löschung vorgesehen (Nachweis, Korrektur nur als neuer Eintrag); Aufbewahrung laut Löschkonzept
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `sop` |  | Verweis |  |
| `version_label` | Versionsnummer | Wert |  |
| `content_markdown` | Volltext / Anweisungsinhalt | Freitext |  |
| `content_hash` | SHA-256 Prüfsumme | Wert | SHA-256 des Dokumenttexts, kein Geheimnis |
| `change_summary` | Änderungsbegründung / Changelog | Freitext |  |
| `approved_by` | Freigegeben durch (ÄLRD / Wachleitung) | Person (Konto) |  |
| `effective_date` | Inkrafttreten | Zeitpunkt |  |
| `created_at` |  | Zeitpunkt |  |

### core.StationContact

Telefonbuch: Einrichtung, Ansprechperson, Nummern

- Lesen: Inhaltsrollen
- Schreiben: Inhaltsrollen
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: keine automatische Löschung; bleibt, bis die Wache den Eintrag nicht mehr braucht
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `name` | Einrichtung / Name | Kontakt/Name | Einrichtung oder Person |
| `contact_person` | Ansprechpartner / Funktion | Kontakt/Name |  |
| `category` |  | Auswahl |  |
| `phone_primary` | Hauptrufnummer | Kontakt/Name |  |
| `phone_secondary` | Notfalltelefon / Direktwahl | Kontakt/Name |  |
| `notes` | Zuständigkeit / Erreichbarkeit | Freitext |  |
| `is_speed_dial` | In Schnellwahlleiste anzeigen | Wert |  |
| `order_rank` | Sortierung | Wert |  |

<a id="modul-display"></a>

## Wachen-Display

Anzeige für einen Monitor in der Wache über einen Display-Link.

- Schalter: `Station.display_enabled`
- Bereiche: `/display/`, `/einstellungen/display/`

### core.DisplayToken

Display-Link (nur Hash) mit Anzeigeauswahl

- Lesen: Master-Admin
- Schreiben: Master-Admin
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: gilt bis Ablauf oder Widerruf; widerrufene und abgelaufene Einträge bleiben ohne technische Löschung
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `label` | Bezeichnung | Wert |  |
| `token_hash` |  | Geheimnis/Prüfwert |  |
| `layout_config` | Bildschirm-Konfiguration | strukturierte Angaben |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `expires_at` |  | Zeitpunkt |  |
| `revoked_at` |  | Zeitpunkt |  |
| `last_used_at` |  | Zeitpunkt |  |

<a id="modul-terminal"></a>

## Wachenterminal

Gemeinsames Touch-Gerät an der Wache mit Wachen-Code (docs/PI-WACHENTERMINAL.md).

- Schalter: Einstellung TERMINAL_ENABLED
- Bereiche: `/terminal/`, `/team/terminal/`

### core.StationTerminal

Registriertes Terminal (nur Hash), Fehlversuche, letzte Nutzung

- Lesen: Master-Admin
- Schreiben: Master-Admin, System
- Zugriffswege: Web, Wachenterminal
- Nachweis: nein
- Frist technisch: gilt bis Ablauf oder Widerruf; widerrufene und abgelaufene Einträge bleiben ohne technische Löschung
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `label` |  | Wert |  |
| `token_hash` |  | Geheimnis/Prüfwert |  |
| `created_by` |  | Person (Konto) |  |
| `created_at` |  | Zeitpunkt |  |
| `last_used_at` |  | Zeitpunkt |  |
| `revoked_at` |  | Zeitpunkt |  |
| `failed_attempts` |  | Wert |  |
| `locked_until` |  | Zeitpunkt |  |

### core.StationTerminalCode

Wachen-Code (nur Hash) und Dienstkonto

- Lesen: Master-Admin
- Schreiben: Master-Admin
- Zugriffswege: Web
- Nachweis: nein
- Frist technisch: solange die Installation besteht; Änderung durch Master-Admin
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `code_hash` |  | Geheimnis/Prüfwert |  |
| `service_user` |  | Person (Konto) |  |
| `set_by` |  | Person (Konto) |  |
| `updated_at` |  | Zeitpunkt |  |

### core.TerminalPairing

Einmaliger Code zum Koppeln eines Handys

- Lesen: System
- Schreiben: die Person selbst, System
- Zugriffswege: Web, App (API)
- Nachweis: nein
- Frist technisch: gilt 120 Sekunden; abgelaufene Codes löscht die nächste Kopplung nach einem Tag
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `membership` |  | Verweis |  |
| `code_hash` |  | Geheimnis/Prüfwert |  |
| `created_at` |  | Zeitpunkt |  |
| `expires_at` |  | Zeitpunkt |  |
| `used_at` |  | Zeitpunkt |  |

<a id="modul-demo"></a>

## Öffentliche Demo

Zeitlich begrenzte Demo-Wache je Besuch.

- Schalter: Einstellung DEMO_SANDBOX
- Bereiche: `/demo/`, `/demo-einstieg/`

### core.DemoDailyStat

Tageszähler der Demo ohne Personenbezug

- Lesen: Superuser (Django-Admin)
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: ohne Personenbezug; bleibt, solange die Installation besteht

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `day` |  | Zeitpunkt |  |
| `started` |  | Wert |  |
| `tour_completed` |  | Wert |  |
| `feedback` |  | Wert |  |

### core.DemoSandbox

Demo-Besuch mit eigener Demo-Wache

- Lesen: System
- Schreiben: System
- Zugriffswege: nur intern
- Nachweis: nein
- Frist technisch: beim Abmelden, nach 30 Minuten ohne Aktivität oder spätestens nach 120 Minuten (DEMO_SANDBOX_IDLE_MINUTES, DEMO_SANDBOX_MAX_MINUTES)
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `station` |  | Verweis |  |
| `token` |  | Geheimnis/Prüfwert |  |
| `created_at` |  | Zeitpunkt |  |
| `last_seen_at` |  | Zeitpunkt |  |
| `ended_at` |  | Zeitpunkt |  |
| `ready_at` |  | Zeitpunkt |  |

<a id="modul-feedback"></a>

## Rückmeldungen

Rückmeldungen über ein öffentliches Formular, Name und E-Mail freiwillig.

- Schalter: Einstellung FEEDBACK_ENABLED
- Bereiche: `/feedback/`, `/einstellungen/feedback/`

### core.Feedback

Rückmeldung mit Text, Bewertung, freiwillig Name und E-Mail

- Lesen: Master-Admin
- Schreiben: öffentlich, Master-Admin
- Zugriffswege: öffentliche Seite, Web
- Nachweis: nein
- Frist technisch: 365 Tage (FEEDBACK_RETENTION_DAYS, `housekeeping`); vorher von Hand löschbar
- Frist festgelegt: laut freigegebenem Löschkonzept: [festlegen]
- Hinweis: Lesen nur der Master-Admin der Betreiber-Wache.

| Feld | Bezeichnung | Art | Hinweis |
| --- | --- | --- | --- |
| `id` |  | Wert |  |
| `created_at` |  | Zeitpunkt |  |
| `kind` | Art | Auswahl |  |
| `message` | Nachricht | Freitext |  |
| `role` | Ich bin | Auswahl |  |
| `rating` | Bewertung | Wert |  |
| `name` | Name | Kontakt/Name | freiwillig |
| `email` | E-Mail für eine Antwort | Kontakt/Name |  |
| `from_demo` |  | Wert |  |
| `status` |  | Auswahl |  |

## Daten auf Endgeräten

| Name | Art | Zweck und Dauer |
| --- | --- | --- |
| `rwsth_session` | Cookie, HttpOnly | Anmeldung; 12 Stunden |
| `rwsth_csrf` | Cookie, HttpOnly | Schutz vor gefälschten Formularen; 364 Tage |
| `wachbuch_language` | Cookie, HttpOnly | gewählte Sprache; 365 Tage; gesetzt beim Sprachwechsel und bei der Anmeldung, wenn im Profil eine Sprache hinterlegt ist |
| `wb_theme` | Cookie, per JavaScript lesbar | helle oder dunkle Darstellung; 365 Tage |
| `rwsth_terminal` | Cookie, HttpOnly | Gerätegeheimnis eines registrierten Wachenterminals; 5 Jahre; nur auf Terminals |
| `rwsth_display` | Cookie, HttpOnly | Display-Link; 365 Tage; nur auf Display-Geräten |
| `rwsth-installed`, `rwsth-install-dismissed` | localStorage | Hinweis zur Installation als App ausgeblendet |
| privater Chat-Schlüssel | sessionStorage | nur während der Sitzung im Browser, nur bei eingeschaltetem Chat |
| Service Worker | Browser-Cache | Programmdateien, Offline-Seite und zuletzt aufgerufene Seiten für die Anzeige ohne Netz; Abmelden leert den Cache; auf Wachenterminals gesperrt |
| App | Gerät | App-Token im sicheren Speicher; Lesecache ab App 1.1 laut docs/CLIENT-OFFLINE-CONTRACT.md |

## Außerhalb der Datenbank

| Ort | Inhalt | Frist |
| --- | --- | --- |
| Sicherungen (Backup-Volume, `./backups`) | vollständige Datenbank | 7 Tage (BACKUP_RETENTION_DAYS in scripts/backup-loop.sh) |
| Docker-Protokolle | Ausgaben der Dienste, darunter das Zugriffsprotokoll von Gunicorn mit Absenderadresse, Pfad und Browserkennung; Aktivierungslinks geschwärzt (core/gunicorn_logging.py) | nur Größe: 3 × 10 MB je Dienst (docker-compose.yml), keine Zeitgrenze |
| Proxy-Protokolle (Caddy oder eigener Proxy) | Zugriffe mit IP-Adresse | laut Betreiber |
| Offsite-Kopie | verschlüsselte Sicherung | laut Betreiber (docs/OPERATIONS.md) |

Externe Dienste und Datenflüsse an Dritte: docs/DATENFLUESSE.md.
