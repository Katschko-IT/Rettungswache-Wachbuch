/*
 * Sperrbildschirm des Wachenterminals: Uhr, Datum und Glas-Karten.
 *
 * Der Server rendert den ersten Stand; dieses Script aktualisiert die Karten
 * jede Minute aus /terminal/daten/ und lädt die Seite beim Datumswechsel neu
 * (neues Hintergrundbild des Tages). Ausgabe nur über textContent.
 * Texte für leere Listen kommen aus data-empty-text der Templates.
 */
(function () {
  "use strict";

  var POLL_MS = 60 * 1000;
  var root = document.querySelector("[data-lock-root]");
  if (!root) {
    return;
  }
  var lang = document.documentElement.lang || "de";
  var startDay = new Date().toDateString();

  function $(selector) {
    return root.querySelector(selector);
  }

  function setText(selector, value) {
    var node = $(selector);
    if (node) {
      node.textContent = value;
    }
  }

  function tick() {
    var now = new Date();
    setText("[data-lock-clock]", String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0"));
    try {
      setText("[data-lock-date]", new Intl.DateTimeFormat(lang, { weekday: "long", day: "numeric", month: "long" }).format(now));
    } catch (error) {
      setText("[data-lock-date]", now.toLocaleDateString());
    }
    var panel = document.querySelector("[data-unlock-panel]");
    if (now.toDateString() !== startDay && (!panel || panel.hidden)) {
      window.location.reload();
    }
  }

  function fillList(selector, items, render) {
    var list = $(selector);
    if (!list) {
      return;
    }
    while (list.firstChild) {
      list.removeChild(list.firstChild);
    }
    if (!items || !items.length) {
      var empty = document.createElement("li");
      empty.className = "lock-empty";
      empty.textContent = list.getAttribute("data-empty-text") || "";
      list.appendChild(empty);
      return;
    }
    items.forEach(function (item) {
      var li = document.createElement("li");
      render(li, item);
      list.appendChild(li);
    });
  }

  function pair(li, strong, rest) {
    var b = document.createElement("strong");
    b.textContent = strong;
    li.appendChild(b);
    li.appendChild(document.createTextNode(" " + rest));
  }

  function apply(data) {
    var weather = data.weather;
    var weatherCard = $("[data-lock-weather]");
    if (weatherCard) {
      weatherCard.classList.toggle("is-empty", !weather);
      if (weather) {
        setText("[data-lock-weather-temp]", weather.max + "° / " + weather.min + "°");
        setText("[data-lock-weather-label]", weather.label || "");
      }
    }
    fillList("[data-lock-events]", (data.events || []).slice(0, 3), function (li, item) {
      pair(li, item.time, item.title);
    });
    fillList("[data-lock-waste]", (data.waste || []).slice(0, 3), function (li, item) {
      pair(li, item.day, item.title);
    });
    var tasks = data.tasks || {};
    setText("[data-lock-tasks-open]", String(tasks.open || 0));
    setText("[data-lock-tasks-done]", String(tasks.done || 0) + " / " + String(tasks.total || 0));
    var bar = $("[data-lock-tasks-bar]");
    if (bar) {
      var percent = tasks.total ? Math.round((100 * (tasks.done || 0)) / tasks.total) : 0;
      bar.style.width = percent + "%";
    }
    setText("[data-lock-handovers-open]", String(data.open_handovers || 0));
    setText("[data-lock-handovers-urgent]", String(data.urgent_handovers || 0));
    var urgentRow = $("[data-lock-handovers-urgent-row]");
    if (urgentRow) {
      urgentRow.hidden = !data.urgent_handovers;
    }
    fillList("[data-lock-fleet]", (data.fleet_vehicles || []).slice(0, 8), function (li, item) {
      li.className = "lock-chip lock-status-" + String(item.status || "").replace(/[^a-z0-9_-]/gi, "");
      pair(li, item.call_sign, item.status_short || item.status_label || "");
    });
  }

  function poll() {
    var url = root.getAttribute("data-data-url");
    fetch(url, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(apply)
      .catch(function () {})
      .then(function () {
        window.setTimeout(poll, POLL_MS);
      });
  }

  tick();
  window.setInterval(tick, 1000);
  window.setTimeout(poll, POLL_MS);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      tick();
    }
  });
})();
