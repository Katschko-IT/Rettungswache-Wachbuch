# Mitwirken am Wachbuch Client

*Letzte Aktualisierung: August 2026 | Version: 0.5.1+*

---

**Danke für dein Interesse am Wachbuch Client!** 🎉

Der **Wachbuch Client** ist die offizielle Mobile-App für das [Rettungswache-Wachbuch](https://github.com/darkspike1988/Rettungswache-Wachbuch). Beiträge sind herzlich willkommen – egal ob du Code beisteuern, Bugs melden, die Dokumentation verbessern oder Feature-Ideen einbringen möchtest.

---

## 📋 **Inhaltsverzeichnis**

1. [Wie du helfen kannst](#-wie-du-helfen-kannst)
2. [Vor dem Start](#-vor-dem-start)
3. [Entwicklungsumgebung einrichten](#-entwicklungsumgebung-einrichten)
4. [Code-Standards](#-code-standards)
5. [Pull Request Prozess](#-pull-request-prozess)
6. [Code Review](#-code-review)
7. [Sicherheitsmeldungen](#-sicherheitsmeldungen)
8. [Lizenz](#-lizenz)

---

## 🤝 **Wie du helfen kannst**

### **🐛 Bugs melden**

- **Issue erstellen**: [GitHub Issues](https://github.com/darkspike1988/Wachbuch-Client/issues/new/choose)
- **Vorlage verwenden**: Nutze die Bug-Report-Vorlage
- **Reproduktionsschritte**: Klare Anleitung, wie der Bug ausgelöst wird
- **Umgebung**: 
  - Flutter-Version (`flutter --version`)
  - Dart-Version (`dart --version`)
  - Betriebssystem (Android/iOS + Version)
  - Gerätemodell
  - Server-Version
- **Logs**: Relevante Log-Auszüge (ohne sensible Daten!)

### **💡 Feature-Ideen einreichen**

- **Issue erstellen**: [Feature Request](https://github.com/darkspike1988/Wachbuch-Client/issues/new?template=feature_request.md)
- **Use Case beschreiben**: Welches Problem löst das Feature?
- **Akzeptanzkriterien**: Was muss das Feature können?
- **Mockups**: Bei UI-Änderungen (optional)
- **Abhängigkeiten**: Gibt es neue Pakete, die benötigt werden?

### **📝 Dokumentation verbessern**

- **Typos korrigieren**: Pull Request mit Fixes
- **Anleitungen ergänzen**: Fehlende Schritte hinzufügen
- **Übersetzungen**: App in andere Sprachen übersetzen (`lib/l10n/`)
- **Beispiele hinzufügen**: Code-Snippets, Screenshots

### **💻 Code beisteuern**

- **Issues kommentieren**: Vor dem Entwickeln ein Issue auswählen
- **Fork erstellen**: Eigene Kopie des Repositories
- **Branch erstellen**: `feature/xxx` oder `fix/xxx`
- **Pull Request**: Mit klarer Beschreibung und Tests

### **🔍 Code Review**

- **Pull Requests kommentieren**: Konstruktives Feedback geben
- **Tests prüfen**: Funktionieren die Änderungen wie erwartet?
- **UI/UX prüfen**: Ist die Benutzerführung intuitiv?

### **📢 Community unterstützen**

- **Fragen beantworten**: In [Discussions](https://github.com/darkspike1988/Wachbuch-Client/discussions)
- **Anfänger helfen**: Bei den ersten Schritten unterstützen
- **Erfahrungen teilen**: Wie du die App einsetzt

---

## 🚀 **Vor dem Start**

### **1. Projekt verstehen**

- **README lesen**: [README.md](README.md)
- **Server-Repository kennenlernen**: [Rettungswache-Wachbuch](https://github.com/darkspike1988/Rettungswache-Wachbuch)
- **API verstehen**: [Server API Docs](https://github.com/darkspike1988/Rettungswache-Wachbuch/blob/main/docs/API.md)
- **Architektur**: [Server Architecture](https://github.com/darkspike1988/Rettungswache-Wachbuch/blob/main/docs/ARCHITECTURE.md)

### **2. Issue auswählen oder erstellen**

- **Existing Issues**: [GitHub Issues](https://github.com/darkspike1988/Wachbuch-Client/issues)
- **Labels prüfen**: `good first issue`, `help wanted`, `bug`, `enhancement`, `ui`, `performance`
- **Priorität**: Issues mit `P0`, `P1`, `P2` haben höhere Priorität

### **3. Issue zuweisen lassen**

- **Kommentieren**: "Ich arbeite daran"
- **Warten auf Bestätigung**: Maintainer weisen das Issue zu
- **Fragen klären**: Bei Unklarheiten nachfragen

---

## 🛠️ **Entwicklungsumgebung einrichten**

### **Voraussetzungen**

| Komponente | Version | Download |
|------------|---------|----------|
| **Flutter SDK** | ≥ 3.8.0 | [flutter.dev](https://flutter.dev/docs/get-started/install) |
| **Dart SDK** | ≥ 3.8.0 | In Flutter enthalten |
| **Android Studio** | Latest | [developer.android.com](https://developer.android.com/studio) |
| **Xcode** | Latest | App Store (macOS only) |
| **Java** | 17+ | [adoptium.net](https://adoptium.net/) |
| **Git** | Latest | [git-scm.com](https://git-scm.com/) |

### **Schritt-für-Schritt**

#### **1. Repository klonen**

```bash
git clone https://github.com/darkspike1988/Wachbuch-Client.git
cd Wachbuch-Client
```

#### **2. Branch erstellen**

```bash
# Für ein neues Feature
git checkout -b feature/mein-feature

# Für einen Bugfix
git checkout -b fix/mein-bugfix

# Für Dokumentation
git checkout -b docs/meine-dokumentation
```

#### **3. Abhängigkeiten installieren**

```bash
flutter pub get
```

#### **4. Code-Qualität prüfen**

```bash
# Linting
flutter analyze

# Formatierung
flutter format .

# Tests
flutter test
```

#### **5. App starten**

```bash
# Standard (Debug)
flutter run

# Auf spezifischem Gerät
flutter run -d <device-id>

# Mit Hot Reload
flutter run --hot-reload
```

### **Nützliche Befehle**

```bash
# Geräte auflisten
flutter devices

# Emulator starten (Android)
flutter emulators --launch <emulator-name>

# Build für Android (Test)
flutter build apk --release --flavor internal

# Build für Android (Produktion)
flutter build apk --release --flavor production

# Build für iOS (Simulator)
flutter build ios --simulator --debug

# Build für iOS (Release)
flutter build ios --release --no-codesign

# Abhängigkeiten aktualisieren
flutter pub upgrade

# Abhängigkeiten prüfen
flutter pub outdated

# Clean Build
flutter clean
flutter pub get
```

---

## 📜 **Code-Standards**

### **Dart/Flutter**

#### **Formatierung**

- **dart format**: Automatische Formatierung
  ```bash
  dart format .
  # Oder für einzelne Dateien
  dart format lib/screens/home_shell.dart
  ```

#### **Linting**

- **flutter_lints**: Standard-Lint-Regeln
- **very_good_analysis**: Strengere Regeln
- **Konfiguration**: Siehe `analysis_options.yaml`

```bash
# Linting prüfen
flutter analyze

# Linting für einzelne Datei
flutter analyze lib/screens/home_shell.dart
```

#### **Type Safety**

✅ **DO:**
```dart
// Immer spezifische Typen verwenden
List<Handover> handovers = [];

// Null Safety
String? optionalName;

// Final für unveränderliche Variablen
final api = WachbuchApi(baseUrl: 'https://example.org');

// Explizite Typen für Funktionen
Future<List<Handover>> fetchHandovers() async { ... }
```

❌ **DON'T:**
```dart
// Vermeide dynamic
var data = jsonDecode(response.body);  // ❌
Map<String, dynamic> data = jsonDecode(response.body);  // ✅

// Vermeide implizite Typen
dynamic result;  // ❌
Object? result;  // ✅ (wenn wirklich nötig)

// Vermeide nullable ohne Grund
String name;  // ❌ (wenn null möglich sein soll)
String? name;  // ✅
```

#### **Widget-Struktur**

✅ **DO:**
```dart
// Kleine, fokussierte Widgets
class HandoverCard extends StatelessWidget {
  final Handover handover;
  
  const HandoverCard({super.key, required this.handover});
  
  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(handover.title),
            const SizedBox(height: 8),
            Text(handover.details),
          ],
        ),
      ),
    );
  }
}
```

❌ **DON'T:**
```dart
// Zu große Widgets (schwer zu warten)
class HomeScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          // 500+ Zeilen Code...
        ],
      ),
    );
  }
}
```

#### **State Management**

- **Einfache Zustände**: `setState` ist ausreichend
- **Komplexe Zustände**: `Provider` oder `Riverpod` verwenden
- **Globaler Zustand**: In `lib/state/` organisieren
- **Vermeide**: `global variables`, `singletons` (außer für Services)

#### **Dokumentation**

- **Doc Comments**: Für alle öffentlichen Mitglieder
- **Format**: Dartdoc-Format
- **Beispiele**: Code-Snippets in Doc Comments

✅ **DO:**
```dart
/// Fetches the list of handovers from the server.
///
/// Returns a [List] of [Handover] objects for the current station.
/// 
/// Throws:
/// - [ApiException] if the request fails
/// - [AuthException] if the user is not authenticated
Future<List<Handover>> fetchHandovers() async {
  ...
}
```

❌ **DON'T:**
```dart
// Keine Dokumentation
Future<List<Handover>> fetchHandovers() async { ... }
```

---

## 🔄 **Pull Request Prozess**

### **1. Vor dem Commit**

- [ ] **Code formatieren**: `dart format .`
- [ ] **Linting prüfen**: `flutter analyze`
- [ ] **Tests ausführen**: `flutter test`
- [ ] **App testen**: Manuelles Testen auf mindestens einem Gerät
- [ ] **Dokumentation aktualisieren** (falls nötig)
- [ ] **Changelog aktualisieren** (falls nötig)

### **2. Commit-Nachricht**

Verwende **[Conventional Commits](https://www.conventionalcommits.org/)**:

```text
<type>([<scope>]): <description>

[body]

[footer]
```

**Beispiele:**

```bash
# Feature
git commit -m "feat(handovers): add filter by priority"

# Bugfix
git commit -m "fix(auth): handle token expiration gracefully"

# UI-Verbesserung
git commit -m "feat(ui): improve handover card design"

# Dokumentation
git commit -m "docs: add installation guide for Android"

# Refactoring
git commit -m "refactor(api): extract auth logic into service"

# Performance
git commit -m "perf: implement lazy loading for module screens"

# Chore (Maintenance)
git commit -m "chore: update dependencies"
```

**Typen:**
- `feat`: Neue Funktion
- `fix`: Bugfix
- `docs`: Dokumentationsänderung
- `style`: Formatierung, fehlende Semikolons
- `refactor`: Code-Refactoring (keine Funktionsänderung)
- `perf`: Performance-Verbesserung
- `test`: Tests hinzufügen/korrigieren
- `chore`: Maintenance (Dependencies, Build-Konfiguration)
- `revert`: Revert eines Commits

**Scopes:**
- `handovers`: Übergaben
- `calendar`: Kalender
- `coffee`: Kaffeekasse
- `auth`: Authentifizierung
- `api`: API-Client
- `ui`: Benutzeroberfläche
- `theme`: Design/Stile

### **3. Pull Request erstellen**

1. **Branch pushen**:
   ```bash
   git push origin feature/mein-feature
   ```

2. **Pull Request erstellen**: [GitHub PR](https://github.com/darkspike1988/Wachbuch-Client/compare)

3. **Vorlage ausfüllen**:
   - **Titel**: Klar und präzise (z.B. "feat: Add dark mode support")
   - **Beschreibung**: 
     - Was ändert sich?
     - Warum ist die Änderung nötig?
     - Wie wurde es getestet?
   - **Verknüpftes Issue**: `#123` (automatisches Closing mit `Closes #123`)
   - **Screenshots**: Bei UI-Änderungen
   - **Checkliste**: Alle Punkte abhaken

### **4. CI prüfen**

- **GitHub Actions**: Alle Checks müssen grün sein
  - `flutter analyze` (Linting)
  - `flutter test` (Tests)
  - Android Build
  - iOS Build (falls konfiguriert)

---

## 👀 **Code Review**

### **Was Reviewer prüfen**

1. **Funktionalität**: Macht der Code das, was er soll?
2. **UI/UX**: Ist die Benutzerführung intuitiv?
3. **Performance**: Gibt es Performance-Probleme?
4. **Code-Qualität**: Ist der Code lesbar und wartbar?
5. **Tests**: Sind die Änderungen ausreichend getestet?
6. **Dokumentation**: Ist die Dokumentation aktualisiert?
7. **Plattform-Kompatibilität**: Funktioniert es auf Android UND iOS?

### **Feedback geben**

- **Konstruktiv**: "Könnten wir das so machen, weil..." statt "Das ist falsch"
- **Spezifisch**: Konkrete Vorschläge machen
- **Begründet**: Warum ist die Änderung nötig?
- **Freundlich**: Respektvoller Ton

### **Auf Feedback reagieren**

- **Dankbar sein**: "Danke für das Feedback!"
- **Fragen klären**: Bei Unklarheiten nachfragen
- **Änderungen vornehmen**: Feedback umsetzen oder begründen
- **Neu commiten**: Änderungen als neuen Commit pushen

---

## 🔒 **Sicherheitsmeldungen**

⚠️ **WICHTIG**: Sicherheitslücken **nicht** in öffentlichen Issues oder Pull Requests melden!

### **Verantwortliche Offenlegung**

1. **E-Mail**: Sende eine E-Mail an die Maintainer
2. **GitHub Security Advisory**: Erstelle einen [Security Advisory](https://github.com/darkspike1988/Wachbuch-Client/security/advisories/new)
3. **Warten**: Gib dem Team Zeit zur Reaktion (mind. 72 Stunden)

### **Was als Sicherheitslücke gilt**

- **Token-Leaks**: App-Tokens in Logs oder Speicher
- **Man-in-the-Middle**: Unsichere HTTPS-Implementierung
- **Datenlecks**: Sensible Daten in lokaler Speicherung
- **Authentifizierungsumgehung**: Schwache Token-Validierung
- **Insecure Storage**: Unsichere Speicherung von Credentials

### **Was NICHT als Sicherheitslücke gilt**

- **Feature Requests**
- **Bugs ohne Sicherheitsauswirkung**
- **Performance-Probleme**
- **UI/UX-Verbesserungen**

---

## 📄 **Lizenz**

Alle Beiträge unterliegen der **GNU Affero General Public License v3.0 oder später**.

### **Was das bedeutet**

- **Du behältst das Copyright** an deinem Code
- **Du gewährst eine Lizenz** für die Nutzung unter AGPL
- **Änderungen müssen offen** sein, wenn sie als Netzwerkdienst betrieben werden

### **DCA (Developer Certificate of Origin)**

Durch das Einreichen von Code bestätigst du:

```text
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

### **Sign-Off**

Füge am Ende deiner Commit-Nachricht hinzu:

```bash
git commit -m "feat: add new feature" -s
```

Dies fügt automatisch deinen Sign-Off hinzu:
```text
Signed-off-by: Dein Name <deine@email.com>
```

---

## 🙏 **Danke!**

Vielen Dank, dass du zum Wachbuch Client beiträgst! 🎉

Deine Beiträge helfen, die App besser zu machen und Rettungswachen bei ihrer wichtigen Arbeit zu unterstützen. Gemeinsam können wir eine **sichere, zuverlässige und benutzfreundliche** Lösung für die interne Organisation von Rettungswachen schaffen.

---

*Letzte Aktualisierung: August 2026 | [GitHub](https://github.com/darkspike1988/Wachbuch-Client)*