/* Checklisten: Schnellaktion „Alle übrigen Punkte in Ordnung“.
   Eigene Datei (CSP ohne unsafe-inline), progressive Verbesserung: Ohne
   JavaScript bleibt die Schaltfläche verborgen und das Formular funktioniert
   wie gewohnt. Gesetzt werden nur Punkte ohne Messwert, die noch kein
   Ergebnis haben; Messpunkte und bereits gewählte Ergebnisse bleiben. */
(function () {
  "use strict";

  function setAllOk(form) {
    var changed = 0;
    var rows = form.querySelectorAll(".checklist-item-row[data-item-id]");
    Array.prototype.forEach.call(rows, function (row) {
      if (row.hasAttribute("data-measurement")) return;
      var radios = row.querySelectorAll('input[type="radio"]');
      var chosen = Array.prototype.some.call(radios, function (radio) { return radio.checked; });
      if (chosen) return;
      var ok = row.querySelector('input[type="radio"][value="ok"]');
      if (ok && !ok.disabled) {
        ok.checked = true;
        changed += 1;
      }
    });
    return changed;
  }

  var forms = document.querySelectorAll("[data-checklist-form]");
  Array.prototype.forEach.call(forms, function (form) {
    var button = form.querySelector("[data-checklist-all-ok]");
    if (!button) return;
    var hint = form.querySelector("[data-checklist-all-ok-hint]");
    var status = form.querySelector("[data-checklist-all-ok-status]");
    button.hidden = false;
    if (hint) hint.hidden = false;
    button.addEventListener("click", function () {
      var changed = setAllOk(form);
      if (status) {
        status.textContent = changed > 0
          ? (form.getAttribute("data-all-ok-done") || "")
          : (form.getAttribute("data-all-ok-none") || "");
      }
    });
  });
})();
