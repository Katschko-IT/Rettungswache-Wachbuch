# Push-Relay für die iOS-/Android-App

Stand: 0.24.0. Status: **Schnittstelle vorbereitet, Relay noch nicht in Betrieb.**

## Warum ein Relay?

Native Push-Nachrichten laufen zwingend über Apple (APNs) und Google (FCM). Die
dafür nötigen Schlüssel gehören zum Herausgeber der App, nicht zu jeder einzelnen
selbst gehosteten Wache. Deshalb sendet der Wachenserver nicht direkt an
Apple/Google, sondern an ein Relay des App-Herausgebers, das die Schlüssel hält.

Solange kein Relay konfiguriert ist, gilt:

- Jede Benachrichtigung landet im persönlichen Posteingang (Web-Übersicht „Für
  dich“, `GET /api/v1/benachrichtigungen/`).
- Die App plant aus `GET /api/v1/fahrzeuge/sperren/` eine **lokale Erinnerung**
  zur Sperrzeit; dafür braucht sie zum Ablaufzeitpunkt weder Netz noch Server.
- Web-Push für die installierte Web-App funktioniert unabhängig davon
  (`WEB_PUSH_ENABLED`, VAPID).

## Konfiguration auf dem Wachenserver

```dotenv
PUSH_RELAY_URL=https://push.example.org/v1/push   # nur https://
PUSH_RELAY_TOKEN=<zufälliges Geheimnis je Wache>
```

`notify-worker` reiht Nachrichten für registrierte Geräte nur ein, wenn
`PUSH_RELAY_URL` gesetzt ist. Der `push-worker` sendet sie mit dem Token.

## Vertrag Wachenserver → Relay

`POST {PUSH_RELAY_URL}`

```http
Authorization: Bearer <PUSH_RELAY_TOKEN>
Content-Type: application/json
X-Idempotency-Key: <UUID der Outbox-Zeile>

{
  "platform": "ios" | "android",
  "token": "<APNs- bzw. FCM-Gerätetoken>",
  "title": "RTW 2: Einwirkzeit abgelaufen",
  "body": "Desinfektion abgeschlossen. Bitte Fahrzeug prüfen und den Status selbst freigeben.",
  "url": "/fuhrpark/v/rtw-2/"
}
```

| Antwort | Bedeutung für den Wachenserver |
| --- | --- |
| `2xx` | zugestellt an Apple/Google, Zeile `sent` |
| `404` / `410` | Token ungültig, Gerät wird gelöscht |
| sonst / Netzfehler | erneuter Versuch mit Backoff (1 min … 6 h, max. 10) |

Datensparsamkeit: Es werden nur Plattform, Gerätetoken und der kurze
organisatorische Text übertragen – keine Namen, keine Patienten- oder
Einsatzdaten. Das Relay speichert nichts über die Zustellung hinaus.

## Geräteregistrierung durch die App

```http
POST   /api/v1/push/geraete/   {"platform": "ios", "token": "...", "app_version": "1.0.1"}
DELETE /api/v1/push/geraete/   {"platform": "ios", "token": "..."}
```

Ein Token gehört immer dem zuletzt angemeldeten Konto des Geräts. Beim Abmelden
meldet die App das Token ab.

## Offene Schritte bis zum echten Push

1. Apple-Developer-Konto: APNs-Schlüssel (`.p8`), Push-Capability im iOS-Projekt.
2. Firebase-Projekt für Android (FCM HTTP v1, Service-Account).
3. Relay betreiben (z. B. kleiner Dienst beim App-Herausgeber) gemäß obigem Vertrag.
4. App: Push-SDK einbinden, Token holen und registrieren.
