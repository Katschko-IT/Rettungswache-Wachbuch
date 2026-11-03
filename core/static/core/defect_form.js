/*
 * Mangel-Formular: Hinweis auf bereits gemeldete Mängel am gewählten Bezug,
 * Chip-Auswahl und Dateihinweis. Eigene Datei statt Inline-Skript (CSP).
 * Die Daten kommen per json_script (#defects-data); Werte werden nur als Text eingesetzt.
 */
(function() {
  var defectsData = {};
  try {
    var raw = document.getElementById("defects-data");
    if (raw) defectsData = JSON.parse(raw.textContent || "{}");
  } catch(e) {}

  var select = document.querySelector("[data-asset-select]");
  var banner = document.querySelector("[data-already-reported-banner]");
  var list = document.querySelector("[data-already-reported-list]");
  var countBadge = document.querySelector("[data-already-reported-count]");
  var customInput = document.getElementById("id_asset_ref_custom");

  function updateDuplicates() {
    if (!select || !banner) return;
    var val = select.value;
    if (val === "__custom__") {
      if (customInput) customInput.hidden = false;
      banner.hidden = true;
      return;
    }
    if (customInput) customInput.hidden = true;

    var opt = select.selectedOptions ? select.selectedOptions[0] : null;
    var assetId = opt ? opt.getAttribute("data-asset-id") : null;
    var items = defectsData[val] || (assetId ? defectsData[assetId] : null) || [];
    if (items && items.length > 0) {
      if (list) {
        list.innerHTML = "";
        items.forEach(function(item) {
          var li = document.createElement("li");
          var a = document.createElement("a");
          a.href = item.url;
          a.target = "_blank";
          a.rel = "noopener";
          var strong = document.createElement("strong");
          strong.textContent = "#" + item.pk + " " + item.title;
          a.appendChild(strong);
          li.appendChild(a);
          var badge1 = document.createElement("span");
          badge1.className = "badge";
          badge1.textContent = item.status;
          li.appendChild(badge1);
          var badge2 = document.createElement("span");
          badge2.className = "badge";
          badge2.textContent = item.priority;
          li.appendChild(badge2);
          if (item.asset_ref) {
            var sm = document.createElement("small");
            sm.className = "muted";
            sm.textContent = " (" + item.asset_ref + ")";
            li.appendChild(sm);
          }
          list.appendChild(li);
        });
      }
      if (countBadge) countBadge.textContent = items.length;
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  }

  if (select) {
    select.addEventListener("change", updateDuplicates);
  }

  document.querySelectorAll(".chip-group").forEach(function(group) {
    group.addEventListener("change", function(e) {
      if (e.target && e.target.type === "radio") {
        group.querySelectorAll(".chip-pill").forEach(function(lbl) {
          lbl.classList.remove("is-selected");
        });
        var label = e.target.closest(".chip-pill");
        if (label) label.classList.add("is-selected");
      }
    });
  });

  function onFileChange(e) {
    var hint = document.getElementById("photo-file-hint");
    if (!hint || !e.target.files || !e.target.files.length) return;
    var names = Array.from(e.target.files).map(function(f) { return f.name; }).join(", ");
    hint.textContent = (hint.getAttribute("data-selected-prefix") || "") + names;
  }
  var cam = document.getElementById("id_camera");
  var att = document.getElementById("id_attachments");
  if (cam) cam.addEventListener("change", onFileChange);
  if (att) att.addEventListener("change", onFileChange);
})();
