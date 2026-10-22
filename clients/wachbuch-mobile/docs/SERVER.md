# Server-Kopplung

Dieses Client-Repo gehört zu:

**https://github.com/Katschko-IT/Rettungswache-Wachbuch**

| Client | Server |
| --- | --- |
| App 0.2.x | API `/api/v1/` ab Server **0.14.1** |
| Adresse / QR → Login | Discovery `GET /api/v1/` |
| User / Passwort | `POST /api/v1/token/` (Alias `/anmeldung/`) |
| MFA | App-Token unter `/konto/api/` |
| Station | nur aus `GET /api/v1/me/` / `uebersicht/` |
| Übergaben | `/handovers/` oder `/uebergaben/` |
| Kalender / Kasse / Checklisten | `/kalender/`, `/kaffeekasse/`, `/checklisten/` |

Header: `Authorization: Token <wb_…>` (widerrufbar)

Ausführlich: [docs/API.md im Server](https://github.com/Katschko-IT/Rettungswache-Wachbuch/blob/main/docs/API.md)
