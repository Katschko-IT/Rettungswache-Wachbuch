/*
 * Deklarative UI-Bausteine für CSP ohne 'unsafe-inline'.
 *
 * Templates beschreiben Verhalten nur über data-Attribute; dieses Script
 * verdrahtet sie. Damit gibt es keine Inline-Handler (onclick=…), keine
 * Inline-Skripte und keine style-Attribute, die die Content-Security-Policy
 * blockieren würde. Werte aus Attributen werden nie als HTML interpretiert.
 *
 *   data-order="3"                 CSS-Reihenfolge (Leiste, „Mehr“)
 *   data-band="#aabbcc"            Farbband einer Aufgabe (--band)
 *   data-bar="42"                  Füllstand 0–100 % eines Balkens
 *   data-modal-open="id"           öffnet <div class="wb-modal" id="id" hidden>
 *     data-modal-action="/pfad/"   … und setzt action des [data-modal-form]
 *     data-modal-label="Text"      … und den Text von [data-modal-label-target]
 *   data-modal-close               schließt das umgebende Modal
 *   data-auto-submit               sendet das Formular bei Änderung ab
 *   data-print                     öffnet den Druckdialog
 *   data-confirm="Frage?"          Formular nur nach Bestätigung absenden
 *   data-scanner                   Kamera-Scanner im Modal (siehe unten)
 *   data-filter-input="selector"   Live-Filter über Karten (Seite „Mehr“)
 *   data-pin-pad="input-id"        Ziffernblock für ein PIN-Feld (Wachenterminal)
 *     data-pin-key="7|back|clear"  … Taste; bei voller Länge wird abgesendet
 *   data-idle-logout="120"         sendet dieses Formular nach N Sekunden ohne
 *                                  Eingabe ab; Restzeit in [data-idle-countdown]
 */
(function () {
  "use strict";

  function each(selector, root, fn) {
    Array.prototype.forEach.call((root || document).querySelectorAll(selector), fn);
  }

  function applyLayoutHints(root) {
    each("[data-order]", root, function (el) {
      var value = parseInt(el.getAttribute("data-order"), 10);
      if (!isNaN(value)) {
        el.style.order = String(value);
      }
    });
    each("[data-band]", root, function (el) {
      var color = el.getAttribute("data-band") || "";
      if (/^#[0-9a-fA-F]{3,8}$/.test(color)) {
        el.style.setProperty("--band", color);
      }
    });
    each("[data-bar]", root, function (el) {
      var value = parseFloat(el.getAttribute("data-bar"));
      if (!isNaN(value)) {
        el.style.width = Math.max(0, Math.min(100, value)) + "%";
      }
    });
  }

  // --- Modals -------------------------------------------------------------

  var lastTrigger = null;

  function openModal(modal, trigger) {
    if (!modal) {
      return;
    }
    if (trigger) {
      var action = trigger.getAttribute("data-modal-action");
      if (action) {
        each("[data-modal-form]", modal, function (form) {
          form.setAttribute("action", action);
        });
      }
      var label = trigger.getAttribute("data-modal-label");
      if (label !== null) {
        each("[data-modal-label-target]", modal, function (el) {
          el.textContent = label;
        });
      }
    }
    lastTrigger = trigger || null;
    modal.hidden = false;
    document.body.classList.add("has-open-modal");
    var focusTarget = modal.querySelector("[autofocus], input:not([type=hidden]), select, textarea, button");
    if (focusTarget) {
      focusTarget.focus();
    }
    modal.dispatchEvent(new CustomEvent("wb:modal-open", { bubbles: true }));
  }

  function closeModal(modal) {
    if (!modal || modal.hidden) {
      return;
    }
    modal.hidden = true;
    if (!document.querySelector(".wb-modal:not([hidden])")) {
      document.body.classList.remove("has-open-modal");
    }
    modal.dispatchEvent(new CustomEvent("wb:modal-close", { bubbles: true }));
    if (lastTrigger && document.contains(lastTrigger)) {
      lastTrigger.focus();
    }
    lastTrigger = null;
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-modal-open]");
    if (opener) {
      event.preventDefault();
      openModal(document.getElementById(opener.getAttribute("data-modal-open")), opener);
      return;
    }
    var closer = event.target.closest("[data-modal-close]");
    if (closer) {
      event.preventDefault();
      closeModal(closer.closest(".wb-modal"));
      return;
    }
    // Klick auf den abgedunkelten Hintergrund schließt das Modal.
    if (event.target.classList && event.target.classList.contains("wb-modal")) {
      closeModal(event.target);
      return;
    }
    if (event.target.closest("[data-print]")) {
      event.preventDefault();
      window.print();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      each(".wb-modal:not([hidden])", document, closeModal);
    }
  });

  document.addEventListener("change", function (event) {
    var field = event.target.closest("[data-auto-submit]");
    if (field && field.form) {
      if (typeof field.form.requestSubmit === "function") {
        field.form.requestSubmit();
      } else {
        field.form.submit();
      }
    }
  });

  document.addEventListener("submit", function (event) {
    var form = event.target;
    var question = form.getAttribute && form.getAttribute("data-confirm");
    if (question && !window.confirm(question)) {
      event.preventDefault();
    }
  });

  // --- Scanner ------------------------------------------------------------
  //
  // <div class="wb-modal" data-scanner data-scanner-search="/mpg/"
  //      data-scanner-formats="qr_code,data_matrix" data-scanner-gs1
  //      data-msg-active="…" data-msg-detected="…" data-msg-manual="…"
  //      data-msg-denied="…">
  //   <video data-scanner-video></video><span data-scanner-status></span>
  //   <input data-scanner-input><button data-scanner-submit></button>
  // </div>
  //
  // Erkannte Werte führen nur zu Adressen derselben Origin. Ein gescannter
  // fremder Link wird wie ein Suchbegriff behandelt, damit präparierte
  // Aufkleber nicht auf externe Seiten umleiten.

  function parseGS1(raw) {
    var gtin = raw.match(/\(01\)(\d{14})|^01(\d{14})/);
    var lot = raw.match(/\(10\)([^()]+)/);
    return (gtin && (gtin[1] || gtin[2])) || (lot && lot[1]) || raw;
  }

  function scannerTarget(modal, raw) {
    var value = (raw || "").trim();
    if (!value) {
      return null;
    }
    try {
      var url = new URL(value, window.location.href);
      if (/^https?:\/\//i.test(value) && url.origin === window.location.origin) {
        return url.pathname + url.search;
      }
    } catch (err) {
      /* kein URL-Wert */
    }
    if (modal.hasAttribute("data-scanner-gs1")) {
      value = parseGS1(value);
    }
    var base = modal.getAttribute("data-scanner-search") || window.location.pathname;
    return base + "?q=" + encodeURIComponent(value.slice(0, 120));
  }

  function setupScanner(modal) {
    var video = modal.querySelector("[data-scanner-video]");
    var status = modal.querySelector("[data-scanner-status]");
    var input = modal.querySelector("[data-scanner-input]");
    var submit = modal.querySelector("[data-scanner-submit]");
    var stream = null;
    var timer = null;

    function say(key, suffix) {
      if (status) {
        status.textContent = (modal.getAttribute("data-msg-" + key) || "") + (suffix || "");
      }
    }

    function go(raw) {
      var target = scannerTarget(modal, raw);
      if (target) {
        window.location.assign(target);
      }
    }

    function stop() {
      window.clearInterval(timer);
      timer = null;
      if (stream) {
        stream.getTracks().forEach(function (track) { track.stop(); });
        stream = null;
      }
      if (video) {
        video.srcObject = null;
      }
    }

    function start() {
      if (!video || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.isSecureContext) {
        say("manual");
        return;
      }
      navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }).then(function (media) {
        if (modal.hidden) {
          media.getTracks().forEach(function (track) { track.stop(); });
          return;
        }
        stream = media;
        video.srcObject = media;
        video.setAttribute("playsinline", "");
        return video.play().then(function () {
          if (!("BarcodeDetector" in window)) {
            say("manual");
            return;
          }
          say("active");
          var formats = (modal.getAttribute("data-scanner-formats") || "qr_code").split(",");
          var detector = new window.BarcodeDetector({ formats: formats });
          timer = window.setInterval(function () {
            if (!stream) {
              return;
            }
            detector.detect(video).then(function (codes) {
              if (codes.length && stream) {
                var value = codes[0].rawValue;
                stop();
                say("detected", value);
                go(value);
              }
            }).catch(function () { /* nächster Versuch */ });
          }, 300);
        });
      }).catch(function () {
        say("denied");
      });
    }

    modal.addEventListener("wb:modal-open", start);
    modal.addEventListener("wb:modal-close", stop);
    if (submit && input) {
      submit.addEventListener("click", function () { go(input.value); });
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          go(input.value);
        }
      });
    }
  }

  // --- Live-Filter --------------------------------------------------------

  function setupFilter(input) {
    var scope = document.querySelector(input.getAttribute("data-filter-input")) || document;
    var hint = input.getAttribute("data-filter-hint");
    var hintEl = hint ? document.getElementById(hint) : null;

    function run() {
      var query = input.value.toLowerCase().trim();
      if (hintEl) {
        hintEl.hidden = query === "";
      }
      each("[data-filter-group]", scope, function (group) {
        var visible = 0;
        each("[data-filter-item]", group, function (item) {
          var match = query === "" || item.textContent.toLowerCase().indexOf(query) !== -1;
          item.hidden = !match;
          if (match) {
            visible += 1;
          }
        });
        group.hidden = query !== "" && visible === 0;
      });
    }

    input.addEventListener("input", run);
    input.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        input.value = "";
        run();
        input.blur();
      }
    });
  }

  function setupPinPad(pad) {
    var input = document.getElementById(pad.getAttribute("data-pin-pad") || "");
    if (!input) {
      return;
    }
    var length = parseInt(input.getAttribute("maxlength"), 10) || 6;
    each("[data-pin-key]", pad, function (key) {
      key.addEventListener("click", function () {
        var value = key.getAttribute("data-pin-key");
        if (value === "back") {
          input.value = input.value.slice(0, -1);
        } else if (value === "clear") {
          input.value = "";
        } else if (/^[0-9]$/.test(value) && input.value.length < length) {
          input.value += value;
        }
        input.dispatchEvent(new Event("input"));
        if (input.value.length === length && input.form && pad.hasAttribute("data-pin-autosubmit")) {
          input.form.requestSubmit ? input.form.requestSubmit() : input.form.submit();
        }
      });
    });
  }

  function setupIdleLogout(form) {
    var seconds = parseInt(form.getAttribute("data-idle-logout"), 10);
    if (!seconds || seconds < 10) {
      return;
    }
    var counter = document.querySelector("[data-idle-countdown]");
    var deadline = Date.now() + seconds * 1000;
    var sent = false;
    function reset() {
      deadline = Date.now() + seconds * 1000;
    }
    ["pointerdown", "keydown", "touchstart", "wheel"].forEach(function (name) {
      document.addEventListener(name, reset, { passive: true });
    });
    window.setInterval(function () {
      var left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      if (counter) {
        counter.textContent = String(left);
      }
      if (left === 0 && !sent) {
        sent = true;
        form.submit();
      }
    }, 1000);
  }

  function init() {
    applyLayoutHints(document);
    each("[data-scanner]", document, setupScanner);
    each("[data-filter-input]", document, setupFilter);
    each("[data-pin-pad]", document, setupPinPad);
    each("form[data-idle-logout]", document, setupIdleLogout);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.WachbuchUI = { applyLayoutHints: applyLayoutHints, scannerTarget: scannerTarget };
})();
