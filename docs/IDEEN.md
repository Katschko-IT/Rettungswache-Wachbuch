# Ideen und spätere Ausbaustufen

Diese Datei sammelt bewusst zurückgestellte Ideen. Nichts davon ist implementiert.

## Wissensbasis aus dem Neuigkeiten-Archiv (RAG, lokal)

**Stand:** Notiz vom 19.10.2026, nicht umgesetzt.

Das Archiv der Neuigkeiten (und später Wachen-Wiki, Übergaben) kann als Grundlage
für einen lokalen Chatbot dienen:

- Quittierte und archivierte Neuigkeiten sind inhaltlich geprüft und
  wachenbezogen – brauchbare Dokumente für eine Wissensbasis.
- Aufbau: Chunking der Texte, lokale Embeddings, Vektorsuche, Antwort mit
  Quellenangabe auf den jeweiligen Neuigkeiten-Eintrag.
- Betrieb bewusst lokal (kein Cloud-Dienst), damit keine Wacheninhalte das
  Haus verlassen.
- Voraussetzung: klare Trennung von Mandanten (eine Wache sieht nur eigene
  Dokumente), Löschkonzept und ein Hinweis, dass Antworten keine
  Rechtsverbindlichkeit haben.

**Offene Fragen vor einer Umsetzung**

- Welche Quellen zählen: nur Archiv, oder auch Wiki und abgeschlossene Übergaben?
- Wer darf fragen (alle Mitglieder oder nur bestimmte Rollen)?
- Wie wird verhindert, dass personenbezogene Angaben in Antworten auftauchen?
- Wo läuft das Modell: auf dem Server, auf dem Gerät, oder beides?
