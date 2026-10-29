# Hardware für Wachwerk

Stand: 29. Oktober 2026. Kurzfassung auch auf der Seite **„Selbst betreiben“**
(`/selbst-betreiben/#hardware`).

Es muss kein Raspberry Pi sein. Wachwerk läuft in Docker auf jedem
64-Bit-Rechner (x86-64 oder ARM64). Für eine Wache, die rund um die Uhr läuft,
zählen vor allem: wenig Strom, keine bewegten Teile, eine SSD statt SD-Karte
und ein Gerät, das nach einem Stromausfall von selbst wieder startet.

## Mindestens und empfohlen

| | Mindestens | Empfohlen |
| --- | --- | --- |
| Prozessor | 64 Bit, 2 Kerne | 4 Kerne, z. B. Intel Celeron J4105 oder besser |
| Arbeitsspeicher | 2 GB (1 GB nur zum Ausprobieren) | 4–8 GB |
| Speicher | 32 GB SSD | 120–256 GB SSD (SATA oder NVMe); keine SD-Karte, kein reiner eMMC-Speicher |
| Netzwerk | LAN | Gigabit-LAN; WLAN der Wache über eigenen Access Point |
| Strom | – | unter 15 W im Leerlauf, möglichst lüfterlos |
| Sonstiges | Docker mit Compose v2 (ab 2.20) | Uhr mit Pufferbatterie (PCs haben sie eingebaut, der Pi braucht ein RTC-Modul), BIOS-Option „Nach Stromausfall einschalten“, kleine USV |

Warum 2 GB als Untergrenze: Datenbank (PostgreSQL), Cache (Redis), Web-Prozess
und Hintergrunddienste laufen gleichzeitig. Die Raspberry-Pi-Konfiguration
(`deploy/pi/docker-compose.pi.yml`) begrenzt die Dienste zusammen auf gut 2,5 GB;
mit 4 GB bleibt Luft für Betriebssystem und Updates.

## Beispielgeräte

Die Angaben stammen aus Datenblättern, Händlerlisten und Erfahrungsberichten.
Sie unterscheiden sich je nach Ausführung – vor dem Kauf das konkrete Modell
prüfen. Stromwerte sind Richtwerte aus Messungen anderer.

| Gerät | Prozessor / Arbeitsspeicher / SSD | Leerlauf | Hinweise |
| --- | --- | --- | --- |
| Raspberry Pi 5 (4/8 GB), neu | ARM, 4 Kerne; RAM fest; SSD per M.2-Aufsatz oder USB 3 | wenige Watt | Einziger Weg mit Komplett-Skript (eigenes WLAN, Touch-Terminal, Zertifikat). Preise sind 2025/26 gestiegen ([Notebookcheck](https://www.notebookcheck.com/Raspberry-Pi-5-erhaelt-Preiserhoehung-wegen-teurem-RAM-neues-Basismodell-kommt-mit-nur-1-GB-Arbeitsspeicher.1174614.0.html)). |
| Raspberry Pi 4 (4 GB) | ARM, 4 Kerne; SSD über USB 3; aktiver Kühler | wenige Watt | Wie oben, etwas langsamer. |
| **Fujitsu Futro S740** (gebraucht) | Celeron J4105, 4 Kerne; 1 DDR4-Steckplatz (8 GB laut Datenblatt, 16 GB laut Nutzerberichten); M.2-**SATA** | ca. 3–4 W, lüfterlos | Beliebter Homeserver ([Futro-S740-Sammlung](https://immae1.github.io/Futro-S740-collection/hardware/specfication/index.html), [mydealz](https://www.mydealz.de/deals/fujitsu-futro-s740-mini-pc-ab-4499eur-intel-j4105-passiv-10w-tdp-2x-dp-wifi-raspberry-alternative-ha-pihole-proxmox-server-refurbished-2606434), [Digitec](https://www.digitec.ch/en/s1/product/fujitsu-futro-s740-intel-celeron-j4105-4-gb-16-gb-pc-12463144)). |
| **Dell Wyse 5070** (gebraucht) | Celeron J4105 oder Pentium J5005; bis 8 GB (Angaben zur Steckplatzzahl uneinheitlich); M.2-**SATA** 2260/2280 | niedrig, lüfterlos | [Parky Towers](https://www.parkytowers.me.uk/thin/wyse/5070/), [Bechtle](https://www.bechtle.com/be/shop/dell-wyse-5070-4-32gb-thinos-thin-client--4580978--p). |
| **HP t630** (gebraucht) | AMD GX-420GI, 4 Kerne; 2 DDR4-Steckplätze bis 32 GB; M.2-**SATA** | ca. 5–12 W (Baureihe) | Viel RAM-Reserve ([Kingston](https://www.kingston.com/en/memory/search/model/95261/hp-hpe-thin-client-t630), [HP-Thin-Clients als Homelab](https://minilabhq-com.pages.dev/posts/hp-t620-t630-t640-thin-client-homelab)). |
| **Lenovo ThinkCentre M720q / M920q Tiny** (gebraucht) | Core i3/i5 der 8./9. Generation; bis 32 GB; NVMe und SATA | ca. 11–27 W je nach CPU | Deutlich mehr Leistung, z. B. für mehrere Wachen oder zusätzliche Dienste ([ServeTheHome](https://www.servethehome.com/lenovo-thinkcentre-m720q-tiny-compact-pc-review/4/), [Notebookcheck](https://www.notebookcheck.com/Mini-PC-Deal-Lenovo-ThinkCentre-M720q-kostet-generalueberholt-derzeit-nur-85-Euro.798664.0.html)). |

**Nicht empfohlen:** Geräte mit fest verlötetem Arbeitsspeicher unter 2 GB und
nur 8–16 GB eMMC (z. B. Dell Wyse 3040), 32-Bit-Geräte, Betrieb von SD-Karte.

## Gebraucht kaufen – worauf achten?

- Thin Clients kommen oft mit 8–32 GB Flash und 4 GB RAM. Eine passende M.2-SSD
  (SATA oder NVMe, Baulänge 2242/2260/2280 je nach Gerät) und ggf. RAM einplanen.
- 64-Bit-Prozessor, Netzteil im Lieferumfang, RAM-Steckplätze prüfen.
- BIOS: Booten von USB erlauben, „AC Power Recovery“ / „Nach Stromausfall
  einschalten“ aktivieren.
- Betriebssystem: Debian oder Ubuntu Server (LTS, 64 Bit), dann Docker mit
  Compose v2, dann der Wachwerk-Installer.
- Preise schwanken stark; gebrauchte Thin Clients liegen oft im zweistelligen
  Euro-Bereich. Aktuelle Angebote vergleichen.

## Raspberry Pi oder anderer Rechner?

| | Raspberry Pi | Thin Client / Mini-PC |
| --- | --- | --- |
| Einrichtung | Komplett-Skript `deploy/pi/setup-pi.sh` (WLAN-Hotspot, Zertifikat, Kiosk-Browser, Einrichtungscode) | Installer `install.sh --mode lan`; WLAN über eigenen Access Point; Touch-Terminal: `TERMINAL_ENABLED=true` in `.env`, Browser im Vollbild auf `/terminal/`, Gerät registrieren unter Team → Wachenterminal |
| Uhr ohne Internet | RTC-Modul nötig | eingebaut (CMOS-Batterie) |
| Speicher | SSD über USB oder M.2-Aufsatz | M.2-SSD intern |
| Erweiterbar | RAM fest | RAM und SSD meist tauschbar |

Das Pi-Skript prüft auf `aarch64` und läuft deshalb nur auf ARM-Rechnern.
