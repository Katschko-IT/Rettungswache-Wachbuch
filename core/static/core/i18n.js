/* Uebersetzungshilfe fuer JavaScript: liest den vom Server gerenderten
   Katalog aus #js-i18n (siehe templates/core/_js_i18n.html). Keine
   Netzwerkabfrage, keine externen Dienste, CSP-konform (eigene Datei). */
(function () {
  "use strict";

  var catalog = {};
  var element = document.getElementById("js-i18n");
  if (element && element.textContent) {
    try {
      catalog = JSON.parse(element.textContent) || {};
    } catch (error) {
      catalog = {};
    }
  }

  /**
   * Liefert die uebersetzte Fassung zu einem Schluessel.
   * @param {string} key Schluessel aus dem Katalog
   * @param {string} fallback deutscher Ausgangstext
   * @returns {string}
   */
  window.wbT = function (key, fallback) {
    var value = catalog[key];
    return typeof value === "string" && value !== "" ? value : fallback;
  };
})();
