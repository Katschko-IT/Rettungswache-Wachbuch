/* Mangel melden: Bezug, Hinweis „bereits gemeldet“, Chips und Fotos.
   Ausgelagert aus defect_form.html (CSP ohne unsafe-inline); Daten kommen per
   json_script, Texte aus dem <template> der Seite. Nutzerdaten nur über
   textContent, nie über innerHTML. Ohne JavaScript bleibt das Formular voll
   bedienbar (Freitextfeld sichtbar, Fotos werden auf dem Server geprüft). */
(function () {
  "use strict";

  var MAX_BYTES = 4 * 1024 * 1024;   // größere Bilder werden verkleinert
  var MAX_EDGE = 2560;                // längste Seite in Pixeln
  var MIN_EDGE = 1280;                // so weit wird höchstens verkleinert
  var QUALITY = 0.85;                 // JPEG-Qualität

  var form = document.querySelector("[data-defect-form]");
  if (!form) {
    return;
  }

  var data = { by_key: {}, by_text: {}, defects: {}, categories: {} };
  try {
    var raw = document.getElementById("defects-data");
    if (raw) {
      var parsed = JSON.parse(raw.textContent || "{}");
      if (parsed && typeof parsed === "object") {
        data.by_key = parsed.by_key || {};
        data.by_text = parsed.by_text || {};
        data.defects = parsed.defects || {};
        data.categories = parsed.categories || {};
      }
    }
  } catch (error) { /* Hinweis entfällt, Formular funktioniert weiter */ }

  var select = form.querySelector("[data-asset-select]");
  var customBox = form.querySelector("[data-custom-reference]");
  var customInput = document.getElementById("id_asset_ref_custom");
  var hintRegion = form.querySelector("[data-duplicate-hint]");
  var deviceHint = form.querySelector("[data-device-hint]");
  var template = document.getElementById("duplicate-hint-template");
  var categoryTouched = false;

  // Entspricht core.defect_refs.normalize_ref.
  function normalizeRef(value) {
    return String(value || "").trim().split(/\s+/).join(" ").toLowerCase();
  }

  function renderDuplicates(ids) {
    if (!hintRegion) {
      return;
    }
    var items = (ids || []).map(function (id) { return data.defects[String(id)]; }).filter(Boolean);
    hintRegion.textContent = "";
    if (!items.length || !template || !template.content) {
      return;
    }
    var banner = template.content.firstElementChild.cloneNode(true);
    var count = banner.querySelector("[data-already-reported-count]");
    var list = banner.querySelector("[data-already-reported-list]");
    if (count) {
      count.textContent = String(items.length);
    }
    items.forEach(function (item) {
      var li = document.createElement("li");
      var link = document.createElement("a");
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener";
      var strong = document.createElement("strong");
      strong.textContent = "#" + item.pk + " " + item.title;
      link.appendChild(strong);
      li.appendChild(link);
      [item.status, item.priority].forEach(function (label) {
        var badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = label;
        li.appendChild(document.createTextNode(" "));
        li.appendChild(badge);
      });
      if (item.asset_ref) {
        var small = document.createElement("small");
        small.className = "muted";
        small.textContent = " (" + item.asset_ref + ")";
        li.appendChild(small);
      }
      list.appendChild(li);
    });
    hintRegion.appendChild(banner);
  }

  function chooseCategory(value) {
    if (categoryTouched || !value) {
      return;
    }
    var radio = form.querySelector('input[name="category"][value="' + value.replace(/[^a-z_]/g, "") + '"]');
    if (radio && !radio.checked) {
      radio.checked = true;
      syncChips(radio);
    }
  }

  function updateReference() {
    if (!select) {
      return;
    }
    var value = select.value;
    var custom = value === "__custom__";
    if (customBox) {
      customBox.hidden = !custom;
    }
    var option = select.selectedOptions ? select.selectedOptions[0] : null;
    if (deviceHint) {
      deviceHint.hidden = !(option && option.getAttribute("data-kind") === "device");
    }
    if (custom) {
      renderDuplicates(data.by_text[normalizeRef(customInput ? customInput.value : "")]);
      return;
    }
    renderDuplicates(data.by_key[value]);
    chooseCategory(data.categories[value]);
  }

  var typingTimer = null;
  function onCustomInput() {
    window.clearTimeout(typingTimer);
    typingTimer = window.setTimeout(function () {
      if (select && select.value !== "__custom__") {
        return;
      }
      renderDuplicates(data.by_text[normalizeRef(customInput.value)]);
    }, 250);
  }

  if (select) {
    // Ohne Wahl, aber mit Freitext (z. B. nach einem Fehler): Freitext zeigen.
    if (!select.value && customInput && customInput.value.trim()) {
      select.value = "__custom__";
    }
    if (customBox) {
      customBox.hidden = select.value !== "__custom__";
    }
    select.addEventListener("change", updateReference);
  }
  if (customInput) {
    customInput.addEventListener("input", onCustomInput);
  }

  function syncChips(radio) {
    var group = radio.closest(".chip-group");
    if (!group) {
      return;
    }
    group.querySelectorAll(".chip-pill").forEach(function (label) {
      label.classList.remove("is-selected");
    });
    var label = radio.closest(".chip-pill");
    if (label) {
      label.classList.add("is-selected");
    }
  }

  form.querySelectorAll(".chip-group").forEach(function (group) {
    group.addEventListener("change", function (event) {
      var target = event.target;
      if (target && target.type === "radio") {
        if (target.hasAttribute("data-category-choice")) {
          categoryTouched = true;
        }
        syncChips(target);
      }
    });
  });

  /* ---------------------------------------------------------------- Fotos */

  var hint = document.getElementById("photo-file-hint");
  var submit = form.querySelector('button[type="submit"]');
  var pending = 0;

  function setPending(delta) {
    pending += delta;
    if (submit) {
      submit.disabled = pending > 0;
    }
  }

  function describe(files, shrunk) {
    if (!hint || !files.length) {
      return;
    }
    var names = files.map(function (file) {
      return shrunk.indexOf(file) >= 0
        ? file.name + " (" + (hint.getAttribute("data-shrunk-label") || "verkleinert") + ")"
        : file.name;
    });
    hint.textContent = (hint.getAttribute("data-selected-label") || "Ausgewählt:") + " " + names.join(", ");
  }

  function jpegName(name) {
    var stem = String(name || "foto").replace(/\.[^.]+$/, "") || "foto";
    return stem + ".jpg";
  }

  function decode(file) {
    if (!window.createImageBitmap) {
      return Promise.reject(new Error("createImageBitmap fehlt"));
    }
    // EXIF-Drehung übernehmen; ältere Browser kennen die Option nicht.
    return window.createImageBitmap(file, { imageOrientation: "from-image" }).catch(function () {
      return window.createImageBitmap(file);
    });
  }

  function encode(bitmap, edge) {
    var scale = Math.min(1, edge / Math.max(bitmap.width, bitmap.height));
    var canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    var context = canvas.getContext("2d");
    context.fillStyle = "#ffffff"; // Transparenz wird weiß, wie auf dem Server
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (blob) {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("toBlob"));
        }
      }, "image/jpeg", QUALITY);
    });
  }

  function shrink(file) {
    return decode(file).then(function (bitmap) {
      var needsWork = file.size > MAX_BYTES || Math.max(bitmap.width, bitmap.height) > MAX_EDGE;
      if (!needsWork) {
        if (bitmap.close) { bitmap.close(); }
        return null;
      }
      var edge = Math.min(MAX_EDGE, Math.max(bitmap.width, bitmap.height));
      function attempt() {
        return encode(bitmap, edge).then(function (blob) {
          if (blob.size > MAX_BYTES && edge > MIN_EDGE) {
            edge = Math.max(MIN_EDGE, Math.round(edge * 0.8));
            return attempt();
          }
          return blob;
        });
      }
      return attempt().then(function (blob) {
        if (bitmap.close) { bitmap.close(); }
        return new File([blob], jpegName(file.name), { type: "image/jpeg", lastModified: Date.now() });
      });
    });
  }

  function onFiles(event) {
    var input = event.target;
    var files = Array.prototype.slice.call(input.files || []);
    if (!files.length) {
      return;
    }
    describe(files, []);
    var images = files.filter(function (file) { return /^image\//.test(file.type); });
    if (!images.length || typeof window.DataTransfer !== "function") {
      return;
    }
    if (hint) {
      hint.textContent = hint.getAttribute("data-shrinking-label") || "";
    }
    setPending(1);
    Promise.all(files.map(function (file) {
      if (!/^image\//.test(file.type)) {
        return Promise.resolve(null);
      }
      return shrink(file).catch(function () { return null; });
    })).then(function (results) {
      var shrunk = [];
      var finalFiles = files.map(function (file, index) {
        if (results[index]) {
          shrunk.push(results[index]);
          return results[index];
        }
        return file;
      });
      if (shrunk.length) {
        try {
          var transfer = new window.DataTransfer();
          finalFiles.forEach(function (file) { transfer.items.add(file); });
          input.files = transfer.files;
        } catch (error) {
          shrunk = [];
          finalFiles = files;
        }
      }
      describe(finalFiles, shrunk);
    }).then(function () { setPending(-1); }, function () { setPending(-1); });
  }

  form.querySelectorAll("[data-photo-input]").forEach(function (input) {
    input.addEventListener("change", onFiles);
  });

  form.addEventListener("submit", function (event) {
    if (pending > 0) {
      event.preventDefault();
    }
  });
})();
