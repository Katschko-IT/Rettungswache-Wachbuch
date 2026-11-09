/* Wachen-Display: Uhr, Daten, Hintergrundwechsel, Vollbild und Esc.
 *
 * Grundsätze (siehe docs/DISPLAY.md):
 * - Aktualisierung ausschließlich über textContent, nie über innerHTML.
 * - Ein einziger rekursiver Timer statt vieler Intervalle (kein Speicherleck).
 * - Bei Rückkehr in den sichtbaren Zustand wird sofort neu geladen.
 */
(function () {
  "use strict";

  var BACKGROUND_COUNT = 18;
  var BACKGROUND_INTERVAL_MS = 5 * 60 * 1000;
  var POLL_INTERVAL_MS = 60 * 1000;
  var RELOAD_CHECK_MS = 60 * 1000;

  var roots = [];
  var pollTimer = null;
  var clockTimer = null;
  var backgroundTimer = null;
  var backgroundIndex = 0;
  var currentVersion = null;
  var overlayRoot = null;

  function text(root, selector, value) {
    var node = root.querySelector(selector);
    if (node) {
      node.textContent = value;
    }
  }

  function show(node, visible) {
    if (node) {
      node.hidden = !visible;
    }
  }

  function formatDate(date) {
    try {
      return new Intl.DateTimeFormat(document.documentElement.lang || "de", {
        weekday: "long",
        day: "2-digit",
        month: "long",
        year: "numeric"
      }).format(date);
    } catch (error) {
      return date.toLocaleDateString();
    }
  }

  function formatClock(date) {
    var hours = String(date.getHours()).padStart(2, "0");
    var minutes = String(date.getMinutes()).padStart(2, "0");
    return hours + ":" + minutes;
  }

  function tickClock() {
    var now = new Date();
    roots.forEach(function (root) {
      text(root, "[data-display-clock]", formatClock(now));
      text(root, "[data-display-date]", formatDate(now));
    });
  }

  function setBackground(root) {
    var layer = root.querySelector("[data-display-background]");
    if (!layer) {
      return;
    }
    backgroundIndex = (backgroundIndex % BACKGROUND_COUNT) + 1;
    var number = String(backgroundIndex).padStart(2, "0");
    var url = "/static/core/display/bg-" + number + ".jpg";
    layer.style.backgroundImage = "url('" + url + "')";
  }

  function rotateBackground() {
    roots.forEach(function (root) {
      var layer = root.querySelector("[data-display-background]");
      if (!layer) {
        return;
      }
      layer.classList.add("is-fading");
      window.setTimeout(function () {
        setBackground(root);
        layer.classList.remove("is-fading");
      }, 1400);
    });
  }

  /* Dichte begrenzen: höchstens data-max-rows Zeilen je Liste, der Rest als
   * „+N weitere“. Abgeschnitten wird nie still (Wand-Display, ROADMAP 0.28). */
  function moreLabel(list) {
    var root = list.closest("[data-display-root]");
    return (root && root.getAttribute("data-more-label")) || "weitere";
  }

  function dataRows(list) {
    return Array.prototype.filter.call(list.children, function (child) {
      return !child.hasAttribute("data-display-more");
    });
  }

  function setMore(list, hiddenCount) {
    var more = list.querySelector("[data-display-more]");
    if (!hiddenCount) {
      if (more) {
        more.remove();
      }
      return;
    }
    if (!more) {
      more = document.createElement(list.tagName === "UL" || list.tagName === "OL" ? "li" : "p");
      more.className = "display-more";
      more.setAttribute("data-display-more", "");
      list.appendChild(more);
    }
    more.textContent = "+" + hiddenCount + " " + moreLabel(list);
  }

  function capList(list) {
    var max = parseInt(list.getAttribute("data-max-rows") || "0", 10);
    var rows = dataRows(list);
    var limit = max && rows.length > max ? max : rows.length;
    rows.forEach(function (row, index) {
      row.hidden = index >= limit;
    });
    setMore(list, rows.length - limit);
  }

  function overflows(element) {
    return element.scrollHeight > element.clientHeight + 1;
  }

  /* Passt eine Spalte trotz Obergrenze nicht in ihre Rasterzeile (lange
   * Titel, kleiner Bildschirm), wird die längste Liste darin um je eine Zeile
   * gekürzt, bis alles passt. Reicht auch das nicht (sehr niedriges Fenster
   * über die Sitzung), bleiben die Listen bei ihrer Obergrenze und die Spalte
   * lässt sich scrollen (is-scrollable), statt still abzuschneiden. Im
   * Kiosk-Rahmen prüft das die CI (Job a11y). Auf schmalen Bildschirmen
   * scrollt die Seite. */
  function fitRegions(root) {
    var regions = root.querySelectorAll(".display-column, .display-traffic-strip");
    Array.prototype.forEach.call(regions, function (region) {
      region.classList.remove("is-scrollable");
    });
    if (window.matchMedia && window.matchMedia("(max-width: 900px)").matches) {
      return;
    }
    Array.prototype.forEach.call(regions, function (region) {
      var guard = 60;
      while (overflows(region) && guard > 0) {
        guard -= 1;
        var best = null;
        var bestCount = 0;
        var lists = Array.prototype.filter.call(region.querySelectorAll("[data-max-rows]"), function (list) {
          return !list.closest("[hidden]");
        });
        // Zuerst Listen mit mehreren Zeilen kürzen, zur Not bis auf „+N weitere“.
        [1, 0].some(function (threshold) {
          lists.forEach(function (list) {
            var visible = dataRows(list).filter(function (row) { return !row.hidden; });
            if (visible.length > threshold && visible.length > (best ? bestCount : threshold)) {
              best = list;
              bestCount = visible.length;
            }
          });
          return best !== null;
        });
        if (!best) {
          break;
        }
        var rows = dataRows(best);
        var shown = rows.filter(function (row) { return !row.hidden; });
        shown[shown.length - 1].hidden = true;
        setMore(best, rows.length - shown.length + 1);
      }
      if (overflows(region)) {
        Array.prototype.forEach.call(region.querySelectorAll("[data-max-rows]"), capList);
        region.classList.add("is-scrollable");
      }
    });
  }

  function renderEvents(root, events) {
    var list = root.querySelector("[data-display-events]");
    if (!list) {
      return;
    }
    list.textContent = "";
    if (!events || !events.length) {
      var empty = document.createElement("li");
      empty.className = "display-empty";
      empty.textContent = list.getAttribute("data-empty-label") || "Keine Termine";
      list.appendChild(empty);
      return;
    }
    events.forEach(function (event) {
      var item = document.createElement("li");
      var time = document.createElement("time");
      time.textContent = event.time;
      var title = document.createElement("span");
      title.textContent = event.title;
      item.appendChild(time);
      item.appendChild(title);
      list.appendChild(item);
    });
    capList(list);
  }

  function renderWaste(root, waste) {
    var list = root.querySelector("[data-display-waste]");
    if (!list) {
      return;
    }
    list.textContent = "";
    (waste || []).forEach(function (entry) {
      var item = document.createElement("li");
      item.textContent = entry.day + " · " + entry.title;
      list.appendChild(item);
    });
    capList(list);
  }

  function renderTasks(root, tasks) {
    var total = tasks && typeof tasks.total === "number" ? tasks.total : 0;
    var done = tasks && typeof tasks.done === "number" ? tasks.done : 0;
    var open = tasks && typeof tasks.open === "number" ? tasks.open : 0;
    text(root, "[data-display-tasks-open]", String(open));
    var bar = root.querySelector("[data-display-progress]");
    if (bar) {
      var percent = total > 0 ? Math.round((done / total) * 100) : 0;
      bar.style.width = percent + "%";
    }
    text(root, "[data-display-tasks-detail]", done + " von " + total + " erledigt");
    var urgentEl = root.querySelector("[data-display-tasks-urgent]");
    if (urgentEl) {
      urgentEl.textContent = "";
      if (tasks && Array.isArray(tasks.urgent_items) && tasks.urgent_items.length > 0) {
        tasks.urgent_items.forEach(function (item) {
          // Farbe nur als Randstreifen über die Stufe (CSS), der Text sagt es.
          var row = document.createElement("li");
          row.className = "display-task-urgent display-level-" + safeClass(item.level);
          var strong = document.createElement("strong");
          strong.textContent = item.title;
          var span = document.createElement("span");
          span.className = "display-task-urgent-label";
          span.textContent = item.label;
          row.appendChild(strong);
          row.appendChild(span);
          urgentEl.appendChild(row);
        });
        capList(urgentEl);
        show(urgentEl, true);
      } else {
        show(urgentEl, false);
      }
    }
  }

  function renderWeather(root, weather) {
    var box = root.querySelector("[data-display-weather]");
    var empty = root.querySelector("[data-display-weather-empty]");
    if (!weather) {
      show(box, false);
      show(empty, true);
      return;
    }
    show(box, true);
    show(empty, false);
    text(root, "[data-display-temp]", String(weather.max));
    text(root, "[data-display-weather-label]", weather.label || "");
    var range = "min " + weather.min + " °C";
    if (typeof weather.precipitation === "number") {
      range += " · " + weather.precipitation.toFixed(1) + " mm";
    }
    if (weather.stale) {
      range += " · ältere Daten";
    }
    text(root, "[data-display-weather-range]", range);
  }

  function renderBirthdays(root, birthdays) {
    var list = root.querySelector("[data-display-birthdays]");
    if (!list) {
      return;
    }
    list.textContent = "";
    (birthdays || []).forEach(function (entry) {
      var item = document.createElement("li");
      var label = document.createElement("span");
      label.className = "display-birthday-label";
      label.textContent = list.getAttribute("data-label") || "Geburtstag";
      var name = document.createElement("strong");
      name.textContent = entry.name;
      item.appendChild(label);
      item.appendChild(name);
      list.appendChild(item);
    });
    capList(list);
  }

  function formatPeriod(start, end) {
    function short(value) {
      var parts = String(value || "").split("-");
      return parts.length === 3 ? parts[2] + "." + parts[1] + "." : "";
    }
    var from = short(start);
    var to = short(end);
    if (from && to && start !== end) {
      return from + " – " + to;
    }
    return from || to;
  }

  function renderTraffic(root, traffic) {
    var section = root.querySelector("[data-display-traffic-section]");
    var list = root.querySelector("[data-display-traffic]");
    if (!section || !list) {
      return;
    }
    var items = (traffic && traffic.items) || [];
    list.textContent = "";
    if (!items.length) {
      show(section, false);
      return;
    }
    items.forEach(function (entry) {
      var item = document.createElement("li");
      item.className = "display-traffic-item";
      if (entry.closed) {
        item.className += " is-closed";
      } else if (entry.restricted) {
        item.className += " is-restricted";
      }

      var source = document.createElement("span");
      source.className = "display-traffic-source";
      source.textContent = entry.source || "";
      if (entry.closed) {
        var badge = document.createElement("span");
        badge.className = "display-traffic-badge";
        badge.textContent = list.getAttribute("data-closed-label") || "Gesperrt";
        source.appendChild(badge);
      }

      var title = document.createElement("strong");
      title.className = "display-traffic-title";
      title.textContent = entry.title || "";

      var meta = document.createElement("span");
      meta.className = "display-traffic-meta";
      var bits = [];
      if (entry.section) {
        bits.push(entry.section);
      }
      var period = formatPeriod(entry.starts_at, entry.ends_at);
      if (period) {
        bits.push(period);
      }
      if (typeof entry.distance_km === "number") {
        bits.push(Math.round(entry.distance_km) + " km");
      }
      meta.textContent = bits.join(" · ");

      item.appendChild(source);
      item.appendChild(title);
      item.appendChild(meta);
      list.appendChild(item);
    });
    capList(list);
    show(section, true);
  }

  /* Listen, die nur erscheinen, wenn es etwas zu sehen gibt (Fahrzeuge,
   * Gerätefristen, Material). Ein in der Konfiguration abgeschaltetes Modul
   * bleibt verborgen (data-module-off aus applyLayout). */
  function renderModuleList(root, selector, items, build) {
    var list = root.querySelector(selector);
    if (!list) {
      return;
    }
    var container = list.closest("[data-module-container]");
    list.textContent = "";
    (items || []).forEach(function (item) {
      list.appendChild(build(item, list));
    });
    capList(list);
    if (container) {
      container.hidden = container.hasAttribute("data-module-off") || !(items && items.length);
    }
  }

  function safeClass(value) {
    return String(value || "").replace(/[^a-z0-9_-]/gi, "");
  }

  function textNode(tag, className, value) {
    var node = document.createElement(tag);
    node.className = className;
    node.textContent = value;
    return node;
  }

  function renderFleet(root, vehicles) {
    renderModuleList(root, "[data-display-fleet]", vehicles, function (vehicle, list) {
      var item = document.createElement("li");
      item.className = "display-vehicle display-status-" + safeClass(vehicle.status);
      item.appendChild(textNode("strong", "display-vehicle-name", vehicle.call_sign || ""));
      item.appendChild(textNode("span", "display-vehicle-status", vehicle.status_label || ""));
      var bits = [];
      if (vehicle.is_locked && vehicle.locked_until) {
        bits.push((list.getAttribute("data-locked-label") || "Desinfektion bis") + " " + vehicle.locked_until);
      }
      if (vehicle.awaiting_release) {
        bits.push(list.getAttribute("data-release-label") || "Freigabe offen");
      }
      if (typeof vehicle.fuel === "number") {
        bits.push((list.getAttribute("data-fuel-label") || "Kraftstoff") + " " + vehicle.fuel + " %");
      }
      if (typeof vehicle.o2 === "number") {
        bits.push("O₂ " + vehicle.o2 + " bar");
      }
      item.appendChild(textNode("span", "display-vehicle-meta", bits.join(" · ")));
      return item;
    });
  }

  function renderAlerts(root, selector, alerts) {
    renderModuleList(root, selector, alerts, function (alert) {
      var item = document.createElement("li");
      item.className = "display-alert display-level-" + safeClass(alert.level);
      item.appendChild(textNode("strong", "display-alert-name", alert.name || ""));
      item.appendChild(textNode("span", "display-alert-label", alert.label || ""));
      return item;
    });
  }

  function renderUrgent(root, count) {
    var block = root.querySelector("[data-display-urgent-block]");
    var value = root.querySelector("[data-display-urgent]");
    if (value) {
      value.textContent = String(count || 0);
    }
    show(block, (count || 0) > 0);
  }

  function applyLayout(root, layoutConfig) {
    if (!layoutConfig || !Array.isArray(layoutConfig.modules)) {
      return;
    }
    layoutConfig.modules.forEach(function (mod) {
      var container = root.querySelector('[data-module-container="' + mod.id + '"]');
      if (!container) {
        return;
      }
      if (mod.enabled === false) {
        container.hidden = true;
        container.setAttribute("data-module-off", "");
        return;
      }
      container.removeAttribute("data-module-off");
      container.hidden = false;

      if (typeof mod.header === "string" && mod.header.trim() !== "") {
        var heading = container.querySelector('[data-module-heading="' + mod.id + '"]') || container.querySelector("h2");
        if (heading) {
          heading.textContent = mod.header;
        }
      }

      if (mod.position) {
        var targetRegion = root.querySelector('[data-region="' + mod.position + '"]');
        if (targetRegion && container.parentNode !== targetRegion) {
          targetRegion.appendChild(container);
        }
      }
    });
  }

  /* Laufschrift aus Pinnwand und Neuigkeiten: höchstens data-max-items Titel
   * und nur so viele, wie in die Zeile passen; der Rest steht als
   * „+N weitere“ daneben. Ein einzelner zu langer Titel endet sichtbar mit
   * „…“ (CSS). Abgeschnitten wird nie still. */
  function renderPinboardNews(root, pinboard, news) {
    var container = root.querySelector("[data-display-pinboard-news]");
    var textNode = root.querySelector("[data-display-ticker-text]");
    if (!container || !textNode) {
      return;
    }
    var ticker = textNode.parentNode;
    var moreNode = root.querySelector("[data-display-ticker-more]");
    var items = [];
    (pinboard || []).concat(news || []).forEach(function (entry) {
      if (entry && entry.title) {
        items.push(entry.title);
      }
    });
    if (!items.length || container.hasAttribute("data-module-off")) {
      container.hidden = true;
      return;
    }
    container.hidden = false;
    var max = parseInt(ticker.getAttribute("data-max-items") || "0", 10) || items.length;
    var shown = Math.min(items.length, max);

    function paint(count) {
      textNode.textContent = items.slice(0, count).join("   ·   ");
      var rest = items.length - count;
      if (moreNode) {
        moreNode.textContent = rest ? "+" + rest + " " + moreLabel(ticker) : "";
        moreNode.hidden = !rest;
      }
    }

    paint(shown);
    while (shown > 1 && textNode.scrollWidth > textNode.clientWidth + 1) {
      shown -= 1;
      paint(shown);
    }
  }

  var audioCtx = null;
  var lastUrgentHandovers = null;

  function playAlarmGong() {
    try {
      var AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return;
      if (!audioCtx) audioCtx = new AudioContext();
      if (audioCtx.state === "suspended") {
        audioCtx.resume();
      }
      var now = audioCtx.currentTime;
      var osc1 = audioCtx.createOscillator();
      var gain1 = audioCtx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(440, now);
      gain1.gain.setValueAtTime(0.3, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc1.connect(gain1);
      gain1.connect(audioCtx.destination);
      osc1.start(now);
      osc1.stop(now + 0.35);

      var osc2 = audioCtx.createOscillator();
      var gain2 = audioCtx.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(880, now + 0.3);
      gain2.gain.setValueAtTime(0.35, now + 0.3);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.85);
      osc2.connect(gain2);
      gain2.connect(audioCtx.destination);
      osc2.start(now + 0.3);
      osc2.stop(now + 0.85);
    } catch (e) {}
  }

  var lastPayload = null;

  function apply(payload) {
    lastPayload = payload;
    if (typeof payload.urgent_handovers === "number") {
      if (lastUrgentHandovers !== null && payload.urgent_handovers > lastUrgentHandovers) {
        playAlarmGong();
      }
      lastUrgentHandovers = payload.urgent_handovers;
    }
    roots.forEach(function (root) {
      applyLayout(root, payload.layout_config);
      renderEvents(root, payload.events);
      renderWaste(root, payload.waste);
      renderTasks(root, payload.tasks);
      renderWeather(root, payload.weather);
      renderBirthdays(root, payload.birthdays);
      renderTraffic(root, payload.traffic);
      renderUrgent(root, payload.urgent_handovers);
      renderPinboardNews(root, payload.pinboard, payload.news);
      renderFleet(root, payload.fleet_vehicles);
      renderAlerts(root, "[data-display-mpg]", payload.mpg_alerts);
      renderAlerts(root, "[data-display-warehouse]", payload.warehouse_alerts);
      fitRegions(root);
    });
  }

  // Webfonts laden erst, wenn Text sie braucht, und ändern die Zeilenhöhen:
  // danach noch einmal einpassen.
  function refit() {
    if (lastPayload) {
      apply(lastPayload);
    }
  }
  if (document.fonts) {
    if (document.fonts.addEventListener) {
      document.fonts.addEventListener("loadingdone", refit);
    }
    if (document.fonts.ready) {
      document.fonts.ready.then(refit);
    }
  }

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(function () {
      if (lastPayload) {
        apply(lastPayload);
      }
    }, 250);
  });

  var sseSource = null;
  function initSSE() {
    if (!window.EventSource) return false;
    // Flächen ohne Display-Token (z. B. Wachenterminal) fragen nur periodisch ab.
    var streamUrl = roots[0] ? roots[0].getAttribute("data-stream-url") : null;
    if (streamUrl === "none") return false;
    try {
      if (sseSource) {
        sseSource.close();
      }
      sseSource = new EventSource(streamUrl || "/display/stream/");
      sseSource.addEventListener("update", function (e) {
        try {
          var payload = JSON.parse(e.data);
          apply(payload);
          if (currentVersion && payload.app_version && payload.app_version !== currentVersion) {
            window.setTimeout(function () {
              window.location.reload();
            }, 3000);
          }
          currentVersion = payload.app_version || currentVersion;
        } catch (err) {}
      });
      sseSource.addEventListener("ping", function () {});
      sseSource.addEventListener("revoked", function () {
        // Zugang entzogen: Stream schließen, der nächste Abruf zeigt den Status.
        sseSource.close();
        sseSource = null;
        schedulePoll(0);
      });
      sseSource.onerror = function () {
        if (sseSource) {
          sseSource.close();
          sseSource = null;
        }
        schedulePoll(POLL_INTERVAL_MS);
      };
      return true;
    } catch (e) {
      return false;
    }
  }

  function schedulePoll(delay) {
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(poll, delay);
  }

  function poll() {
    var root = roots[0];
    if (!root) {
      return;
    }
    var url = root.getAttribute("data-data-url");
    if (!url) {
      return;
    }
    fetch(url, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (payload) {
        apply(payload);
        if (currentVersion && payload.app_version && payload.app_version !== currentVersion) {
          window.setTimeout(function () {
            window.location.reload();
          }, 3000);
        }
        currentVersion = payload.app_version || currentVersion;
        if (!sseSource) {
          initSSE();
        }
        schedulePoll(POLL_INTERVAL_MS);
      })
      .catch(function () {
        schedulePoll(POLL_INTERVAL_MS);
      });
  }

  function requestWakeLock() {
    if (!("wakeLock" in navigator) || !window.isSecureContext) {
      return;
    }
    navigator.wakeLock.request("screen").catch(function () {
      /* Browser verweigert – Anzeige läuft trotzdem. */
    });
  }

  function openOverlay() {
    overlayRoot = document.querySelector("[data-display-overlay='true']");
    if (!overlayRoot) {
      return;
    }
    overlayRoot.hidden = false;
    document.body.classList.add("is-display-open");
    var element = document.documentElement;
    if (element.requestFullscreen) {
      element.requestFullscreen({ navigationUI: "hide" }).catch(function () {
        /* Ohne Vollbild als Overlay weiterführen. */
      });
    }
    requestWakeLock();
    roots = Array.prototype.slice.call(document.querySelectorAll("[data-display-root]:not([hidden])"));
    setBackground(roots[0]);
    tickClock();
    poll();
    if (!clockTimer) {
      clockTimer = window.setInterval(tickClock, 1000);
    }
    if (!backgroundTimer) {
      backgroundTimer = window.setInterval(rotateBackground, BACKGROUND_INTERVAL_MS);
    }
  }

  function closeOverlay() {
    if (!overlayRoot) {
      return;
    }
    overlayRoot.hidden = true;
    document.body.classList.remove("is-display-open");
    window.clearTimeout(pollTimer);
    if (document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch(function () {});
    }
    overlayRoot = null;
  }

  function initStandalone() {
    var prompt = document.querySelector("[data-display-prompt]");
    var button = document.querySelector("[data-display-fullscreen]");
    var element = document.documentElement;

    /* Die Leiste (Rückweg-Link, Vollbild-Knopf) verschwindet nur im Vollbild.
     * Ohne Vollbild-Funktion (z. B. iPhone) bleibt der Rückweg sichtbar. */
    function syncPrompt() {
      if (!prompt) {
        return;
      }
      var anyVisible = Array.prototype.some.call(prompt.children, function (child) {
        return !child.hidden;
      });
      prompt.hidden = Boolean(document.fullscreenElement) || !anyVisible;
    }

    /* Kiosk über den Display-Link: Die Leiste erscheint beim Start und nach
     * einer Bewegung oder Taste für einige Sekunden, sonst verdeckte sie die
     * Fußzeile (dringende Übergaben) auf einem Fernseher ohne Maus dauerhaft. */
    if (prompt && document.documentElement.classList.contains("display-kiosk")) {
      var idleTimer = null;
      var wake = function () {
        prompt.classList.remove("is-idle");
        window.clearTimeout(idleTimer);
        idleTimer = window.setTimeout(function () {
          prompt.classList.add("is-idle");
        }, 6000);
      };
      ["mousemove", "pointerdown", "keydown", "touchstart"].forEach(function (name) {
        document.addEventListener(name, wake, { passive: true });
      });
      wake();
    }

    if (button) {
      if (!element.requestFullscreen) {
        button.hidden = true;
      }
      button.addEventListener("click", function () {
        requestWakeLock();
        if (!element.requestFullscreen) {
          return;
        }
        element.requestFullscreen({ navigationUI: "hide" }).catch(function () {
          button.hidden = true;
          syncPrompt();
        });
      });
    }
    syncPrompt();
    document.addEventListener("fullscreenchange", syncPrompt);
  }

  function init() {
    // Nur wirklich sichtbare Flächen zählen: Ein verstecktes Overlay darf
    // weder Daten abrufen noch einen Livestream (Server-Thread) öffnen.
    var visibleRoots = Array.prototype.slice.call(
      document.querySelectorAll("[data-display-root]")
    ).filter(function (el) {
      return !el.closest("[hidden]");
    });

    // Ereignisbehandlung immer registrieren – auch wenn das Overlay noch
    // verborgen ist und erst später per Monitor-Symbol geöffnet wird.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible" && roots.length) {
        tickClock();
        poll();
        requestWakeLock();
      }
    });

    var overlayPresent = document.querySelector("[data-display-overlay='true']");
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-display-open]"),
      function (button) {
        button.addEventListener("click", function (event) {
          event.preventDefault();
          openOverlay();
        });
      }
    );
    if (overlayPresent) {
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && overlayRoot) {
          closeOverlay();
        }
      });
      document.addEventListener("fullscreenchange", function () {
        if (!document.fullscreenElement && overlayRoot) {
          closeOverlay();
        }
      });
    }

    if (visibleRoots.length) {
      roots = visibleRoots;
      if (visibleRoots[0].getAttribute("data-display-overlay") === "true") {
        overlayRoot = visibleRoots[0];
      } else {
        initStandalone();
        if (!visibleRoots[0].hasAttribute("data-no-escape")) {
          document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !document.fullscreenElement) {
              window.location.href = "/uebersicht/";
            }
          });
        }
      }
      setBackground(roots[0]);
      tickClock();
      poll();
      clockTimer = window.setInterval(tickClock, 1000);
      backgroundTimer = window.setInterval(rotateBackground, BACKGROUND_INTERVAL_MS);
    }
  }

  window.WachbuchDisplay = { open: openOverlay, close: closeOverlay };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
