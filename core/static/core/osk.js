/*
 * Bildschirmtastatur für das Wachenterminal (Touch-Bildschirm am Raspberry Pi).
 *
 * Erscheint nur, wenn ein Textfeld angetippt wird und gerade weder eine
 * Hardware-Tastatur noch eine Maus benutzt wird:
 *   - ein echter Tastendruck blendet sie aus und unterdrückt sie 10 Minuten,
 *   - eine frei bewegte Maus (Zeiger bewegt sich ohne gedrückte Taste) ebenso.
 * Ist sie unterdrückt, bietet eine kleine Taste unten rechts sie trotzdem an.
 *
 * Nur für Linux-Kiosk-Browser: Handys, Tablets, Windows und ChromeOS bringen
 * eigene Bildschirmtastaturen mit. Der Server bindet die Datei nur auf
 * registrierten Terminals und am Server selbst (localhost) ein.
 * Texte kommen aus data-osk-* von #osk-root; Ausgabe nur über textContent.
 */
(function () {
  "use strict";

  var root = document.getElementById("osk-root");
  var ua = navigator.userAgent || "";
  if (!root || !/Linux/.test(ua) || /Android|CrOS/.test(ua)) {
    return;
  }

  var SUPPRESS_MS = 10 * 60 * 1000;
  var TEXT_TYPES = { "": 1, text: 1, search: 1, email: 1, url: 1, tel: 1, password: 1, number: 1 };
  var LETTERS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "ß", "{bksp}"],
    ["q", "w", "e", "r", "t", "z", "u", "i", "o", "p", "ü"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ö", "ä", "{enter}"],
    ["{shift}", "y", "x", "c", "v", "b", "n", "m", ",", ".", "-", "{shift}"],
    ["{sym}", "@", "{space}", "?", "{hide}"]
  ];
  var SYMBOLS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "{bksp}"],
    ["!", "\"", "§", "$", "%", "&", "/", "(", ")", "=", "?"],
    ["+", "*", "#", "'", "_", ":", ";", "<", ">", "€", "{enter}"],
    ["@", "[", "]", "{", "}", "\\", "|", "~", "^", "°"],
    ["{abc}", "{space}", "{hide}"]
  ];

  var hardwareAt = 0;
  var mouseAt = 0;
  var hoverMoves = 0;
  var hoverSince = 0;
  var target = null;
  var layer = "letters";
  var shift = false;
  var caps = false;
  var lastShiftAt = 0;

  function text(name, fallback) {
    return root.getAttribute("data-osk-" + name) || fallback;
  }

  function editable(el) {
    if (!el || el.disabled || el.readOnly || root.contains(el)) {
      return false;
    }
    if (el.tagName === "TEXTAREA") {
      return true;
    }
    return el.tagName === "INPUT" &&
      Object.prototype.hasOwnProperty.call(TEXT_TYPES, (el.getAttribute("type") || "").toLowerCase());
  }

  function numericKind(el) {
    var mode = (el.getAttribute("inputmode") || "").toLowerCase();
    var type = (el.getAttribute("type") || "").toLowerCase();
    if (type === "tel" || mode === "tel") {
      return "+";
    }
    if (type === "number") {
      return ".";
    }
    if (mode === "decimal") {
      return ",";
    }
    return mode === "numeric" ? " " : "";
  }

  function suppressed() {
    var now = Date.now();
    return now - hardwareAt < SUPPRESS_MS || now - mouseAt < SUPPRESS_MS;
  }

  // ---- Darstellung ---------------------------------------------------------

  var toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "osk-toggle";
  toggle.hidden = true;
  toggle.tabIndex = -1;
  toggle.textContent = "⌨";
  toggle.setAttribute("aria-label", text("show", "Tastatur einblenden"));
  document.body.appendChild(toggle);

  function keyLabel(key) {
    switch (key) {
      case "{bksp}": return ["⌫", text("backspace", "Löschen")];
      case "{enter}": return ["↵", text("enter", "Weiter")];
      case "{shift}": return ["⇧", text("shift", "Umschalt")];
      case "{sym}": return ["&123", text("symbols", "Sonderzeichen")];
      case "{abc}": return ["ABC", text("letters", "Buchstaben")];
      case "{space}": return [" ", text("space", "Leertaste")];
      case "{hide}": return ["⌨ ▾", text("hide", "Tastatur ausblenden")];
      default: return [(shift || caps) ? key.toUpperCase() : key, ""];
    }
  }

  function rowsFor() {
    var kind = target ? numericKind(target) : "";
    if (kind) {
      return [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        [kind === " " ? "{gap}" : kind, "0", "{bksp}"],
        ["{hide}", "{enter}"]
      ];
    }
    return layer === "symbols" ? SYMBOLS : LETTERS;
  }

  function render() {
    while (root.firstChild) {
      root.removeChild(root.firstChild);
    }
    var rows = rowsFor();
    root.classList.toggle("osk-numeric", Boolean(target && numericKind(target)));
    rows.forEach(function (row) {
      var line = document.createElement("div");
      line.className = "osk-row";
      row.forEach(function (key) {
        if (key === "{gap}") {
          var gap = document.createElement("span");
          gap.className = "osk-key osk-gap";
          line.appendChild(gap);
          return;
        }
        var button = document.createElement("button");
        var label = keyLabel(key);
        button.type = "button";
        button.tabIndex = -1;
        button.className = "osk-key";
        button.setAttribute("data-key", key);
        button.textContent = label[0];
        if (label[1]) {
          button.setAttribute("aria-label", label[1]);
          button.classList.add("osk-special", "osk-" + key.replace(/[{}]/g, ""));
        }
        if (key === "{shift}" && (shift || caps)) {
          button.classList.add(caps ? "is-locked" : "is-active");
        }
        line.appendChild(button);
      });
      root.appendChild(line);
    });
  }

  function show() {
    if (!target) {
      return;
    }
    render();
    root.hidden = false;
    toggle.hidden = true;
    keepVisible();
  }

  // Das aktive Feld liegt immer über der Tastatur: Platz unten schaffen und
  // nur so weit scrollen wie nötig.
  function keepVisible() {
    var height = root.getBoundingClientRect().height;
    document.body.style.paddingBottom = Math.ceil(height + 16) + "px";
    var rect = target.getBoundingClientRect();
    var limit = window.innerHeight - height - 24;
    if (rect.bottom > limit || rect.top < 0) {
      window.scrollBy(0, rect.top < 0 ? rect.top - 24 : rect.bottom - limit);
    }
  }

  function hide(keepToggle) {
    root.hidden = true;
    document.body.style.paddingBottom = "";
    toggle.hidden = !(keepToggle && target);
  }

  // ---- Eingabe -------------------------------------------------------------

  function selection(el) {
    try {
      if (typeof el.selectionStart === "number") {
        return [el.selectionStart, el.selectionEnd];
      }
    } catch (error) {
      // type=email/number kennen keine Auswahl
    }
    return null;
  }

  function changed(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function insert(value) {
    var el = target;
    var range = selection(el);
    var removed = range ? range[1] - range[0] : 0;
    if (el.maxLength >= 0 && el.value.length - removed + value.length > el.maxLength) {
      return;
    }
    if (range) {
      el.setRangeText(value, range[0], range[1], "end");
    } else {
      el.value += value;
    }
    changed(el);
  }

  function backspace() {
    var el = target;
    var range = selection(el);
    if (!range) {
      el.value = el.value.slice(0, -1);
    } else if (range[0] !== range[1]) {
      el.setRangeText("", range[0], range[1], "end");
    } else if (range[0] > 0) {
      el.setRangeText("", range[0] - 1, range[0], "end");
    }
    changed(el);
  }

  function fieldsAfter(el) {
    var scope = el.form || document;
    var fields = Array.prototype.filter.call(scope.querySelectorAll("input, textarea"), function (field) {
      return editable(field) && field.offsetParent !== null;
    });
    return fields.slice(fields.indexOf(el) + 1);
  }

  function enter() {
    var el = target;
    if (el.tagName === "TEXTAREA") {
      insert("\n");
      return;
    }
    var next = fieldsAfter(el)[0];
    if (next) {
      target = next;
      next.focus();
      show();
      return;
    }
    hide(false);
    if (el.form && typeof el.form.requestSubmit === "function") {
      el.form.requestSubmit();
    }
  }

  function press(key) {
    if (!target) {
      return;
    }
    switch (key) {
      case "{bksp}": backspace(); return;
      case "{enter}": enter(); return;
      case "{space}": insert(" "); return;
      case "{hide}": hide(true); return;
      case "{sym}": layer = "symbols"; render(); return;
      case "{abc}": layer = "letters"; render(); return;
      case "{shift}":
        // Einmal: nächster Buchstabe groß; zweimal schnell: Feststelltaste.
        var now = Date.now();
        if (caps) {
          caps = false;
          shift = false;
        } else if (shift && now - lastShiftAt < 400) {
          caps = true;
          shift = false;
        } else {
          shift = !shift;
        }
        lastShiftAt = now;
        render();
        return;
      default:
        insert((shift || caps) ? key.toUpperCase() : key);
        if (shift) {
          shift = false;
          render();
        }
    }
  }

  // Tasten nehmen dem Textfeld nie den Fokus.
  function keepFocus(event) {
    if (event.target.closest(".osk-key, .osk-toggle")) {
      event.preventDefault();
    }
  }
  document.addEventListener("pointerdown", keepFocus, true);
  document.addEventListener("mousedown", keepFocus, true);

  root.addEventListener("click", function (event) {
    var key = event.target.closest("[data-key]");
    if (key) {
      press(key.getAttribute("data-key"));
    }
  });

  toggle.addEventListener("click", function () {
    hardwareAt = 0;
    mouseAt = 0;
    show();
  });

  // ---- Erkennung -----------------------------------------------------------

  document.addEventListener("keydown", function (event) {
    // Nur echte Tasten; die Bildschirmtastatur erzeugt keine keydown-Ereignisse.
    if (event.isTrusted && event.key && event.key !== "Unidentified") {
      hardwareAt = Date.now();
      if (!root.hidden) {
        hide(false);
      }
    }
  }, true);

  document.addEventListener("pointermove", function (event) {
    // Eine echte Maus bewegt den Zeiger ohne gedrückte Taste; Touch (auch als
    // Maus emuliert) nicht. Erst viele solche Bewegungen zählen als Maus.
    if (event.pointerType !== "mouse" || event.buttons !== 0) {
      return;
    }
    var now = Date.now();
    if (now - hoverSince > 1500) {
      hoverSince = now;
      hoverMoves = 0;
    }
    hoverMoves += 1;
    if (hoverMoves > 12) {
      mouseAt = now;
    }
  }, { passive: true });

  document.addEventListener("pointerdown", function (event) {
    if (event.pointerType === "touch" || event.pointerType === "pen") {
      mouseAt = 0;
      hoverMoves = 0;
    }
  }, { capture: true, passive: true });

  document.addEventListener("click", function (event) {
    var el = event.target;
    if (!editable(el)) {
      return;
    }
    target = el;
    layer = "letters";
    if (suppressed()) {
      hide(true);
    } else {
      show();
    }
  });

  document.addEventListener("focusin", function (event) {
    if (editable(event.target)) {
      target = event.target;
      if (root.hidden) {
        toggle.hidden = false;
      } else {
        render();
        keepVisible();
      }
    }
  });

  document.addEventListener("focusout", function () {
    window.setTimeout(function () {
      if (!editable(document.activeElement)) {
        target = null;
        hide(false);
      }
    }, 0);
  });
})();
