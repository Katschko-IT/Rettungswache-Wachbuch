#!/usr/bin/env bash
# Deprecated safety guard: the standalone Wachbuch-Client repository is the
# canonical source. Never publish the server-side mirror back to it.
set -euo pipefail

cat >&2 <<'EOF'
FEHLER: scripts/publish-mobile-client-repo.sh ist absichtlich deaktiviert.

Quelle der Wahrheit fuer Flutter/iOS/Android ist:
  https://github.com/Katschko-IT/Wachbuch-Client

Der Ordner clients/wachbuch-mobile/ im Server-Repo ist nur ein historischer
Entwicklungs-Spiegel und darf den Standalone-Client nicht ueberschreiben.
Insbesondere sind force/force-with-lease Publishes aus diesem Spiegel verboten,
weil dadurch neuere Client-Commits verloren gehen koennen.

Aenderungen am Mobile-Client bitte direkt im Wachbuch-Client-Repo entwickeln,
testen und mergen. Der Server koppelt sich ueber den dokumentierten /api/v1/
Vertrag und die kompatiblen Versionspaare an den Client.
EOF

exit 2
