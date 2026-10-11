/* Wachwerk – Präsentations-Landing: lokale, serverunabhängige Produktvorschau.
   Keine Serveraufrufe, kein Login, keine Speicherung, kein Tracking.
   DOM-Text wird ausschließlich über textContent gesetzt – kein innerHTML. */
(function () {
  "use strict";

  var root = document.querySelector("[data-pw-demo]");
  if (!root) {
    return;
  }

  var steps = Array.prototype.slice.call(root.querySelectorAll("[data-pw-view]"));
  var panels = Array.prototype.slice.call(root.querySelectorAll("[data-pw-panel]"));
  var status = root.querySelector("[data-pw-status]");
  var mobileMenu = document.querySelector(".pw-mobile-menu");
  if (mobileMenu) {
    Array.prototype.slice.call(mobileMenu.querySelectorAll("a")).forEach(function (link) {
      link.addEventListener("click", function () { mobileMenu.removeAttribute("open"); });
    });
    mobileMenu.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        mobileMenu.removeAttribute("open");
        mobileMenu.querySelector("summary").focus();
      }
    });
  }


  function announce(msg) {
    if (status) {
      status.textContent = msg;
    }
  }

  /* Opt-in presentation: one pass, no mutations or automatic restart. */
  var playButton = root.querySelector("[data-pw-play]");
  var playback = root.querySelector("[data-pw-playback]");
  var tourTimer = null;
  var tourPlaying = false;
  var tourIndex = 0;
  var tourViews = ["overview", "handover", "tasks", "calendar"];
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function stopTour() {
    window.clearTimeout(tourTimer);
    tourTimer = null;
    tourPlaying = false;
    if (playButton) {
      playButton.textContent = "Rundgang starten";
      playButton.setAttribute("aria-pressed", "false");
    }
  }

  function advanceTour() {
    if (!tourPlaying || document.hidden) { stopTour(); return; }
    tourIndex += 1;
    if (tourIndex >= tourViews.length) {
      stopTour();
      announce("Rundgang beendet. Du kannst die Vorschau selbst bedienen.");
      return;
    }
    show(tourViews[tourIndex]);
    announce("Rundgang: " + steps[tourIndex].textContent.trim());
    tourTimer = window.setTimeout(advanceTour, 6500);
  }

  if (playButton && playback) {
    playback.removeAttribute("hidden");
    playButton.addEventListener("click", function () {
      if (tourPlaying) { stopTour(); announce("Rundgang angehalten."); return; }
      tourPlaying = true;
      tourIndex = 0;
      show("overview");
      playButton.textContent = "Rundgang stoppen";
      playButton.setAttribute("aria-pressed", "true");
      root.querySelector(".pw-device").scrollIntoView({
        block: "center", behavior: reducedMotion.matches ? "auto" : "smooth"
      });
      announce("Rundgang gestartet. Vier Ansichten, jeweils sechseinhalb Sekunden.");
      tourTimer = window.setTimeout(advanceTour, 6500);
    });
    root.addEventListener("click", function (event) {
      if (event.target.closest("button, input, label, a") && !event.target.closest("[data-pw-play]")) {
        stopTour();
      }
    }, true);
    root.addEventListener("keydown", function (event) {
      if (event.key === "Escape" || event.key === "Tab") { stopTour(); }
    });
    root.querySelector(".pw-screen").addEventListener("wheel", stopTour, { passive: true });
    root.querySelector(".pw-screen").addEventListener("touchstart", stopTour, { passive: true });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { stopTour(); }
    });
  }

  /* Progressive enhancement: content stays visible without JS/observer. */
  if ("IntersectionObserver" in window && !reducedMotion.matches) {
    var revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("pw-entered");
          revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    Array.prototype.slice.call(root.querySelectorAll(".pw-section, .pw-final")).forEach(function (section) {
      section.classList.add("pw-reveal");
      revealObserver.observe(section);
    });
  }
  if ("IntersectionObserver" in window) {
    var tourObserver = new IntersectionObserver(function (entries) {
      if (!entries[0].isIntersecting) { stopTour(); }
    });
    tourObserver.observe(root.querySelector("#demo"));
  }

  function show(name) {
    panels.forEach(function (panel) {
      var on = panel.getAttribute("data-pw-panel") === name;
      panel.classList.toggle("is-on", on);
      if (on) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "");
      }
    });
    if (playback) { playback.setAttribute("data-view", name); }
    var screen = root.querySelector(".pw-screen");
    if (screen) { screen.scrollTop = 0; }
    steps.forEach(function (step) {
      var on = step.getAttribute("data-pw-view") === name;
      step.classList.toggle("is-on", on);
      step.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function currentPanel() {
    for (var i = 0; i < panels.length; i += 1) {
      if (panels[i].classList.contains("is-on")) {
        return panels[i];
      }
    }
    return panels[0];
  }

  /* Guided journey: scenario selection */
  steps.forEach(function (step) {
    step.addEventListener("click", function () {
      var name = step.getAttribute("data-pw-view");
      show(name);
      announce("Ansicht: " + (step.textContent || "").replace(/\s+/g, " ").trim());
    });
  });

  /* Back links inside the screen */
  Array.prototype.slice.call(root.querySelectorAll("[data-pw-target]")).forEach(function (btn) {
    btn.addEventListener("click", function () {
      show(btn.getAttribute("data-pw-target"));
    });
  });

  /* Handover detail: acknowledge a specific, loaded revision (never "done") */
  var detailTitle = root.querySelector("[data-pw-ho-title]");
  var detailSummary = root.querySelector("[data-pw-ho-summary]");
  var detailPri = root.querySelector("[data-pw-ho-pri]");
  var revEls = Array.prototype.slice.call(root.querySelectorAll("[data-pw-panel='handover'] [data-pw-rev]"));
  var revTotalEl = root.querySelector("[data-pw-rev-total]");
  var revItems = Array.prototype.slice.call(root.querySelectorAll("[data-pw-rev-item]"));
  var ackStatus = root.querySelector("[data-pw-ack-status]");

  function resetAck() {
    if (ackStatus) {
      ackStatus.classList.remove("is-done");
      ackStatus.textContent = "Noch nicht gelesen.";
    }
  }

  function openHandover(btn) {
    var rev = btn.getAttribute("data-pw-rev") || "1";
    if (detailTitle) {
      detailTitle.textContent = btn.getAttribute("data-pw-title") || "";
    }
    if (detailSummary) {
      detailSummary.textContent = btn.getAttribute("data-pw-summary") || "";
    }
    if (detailPri) {
      detailPri.textContent = btn.getAttribute("data-pw-pri") || "Offen";
      detailPri.className = "pw-pri " + (btn.getAttribute("data-pw-pri-class") || "pw-pri-normal");
    }
    revEls.forEach(function (el) { el.textContent = rev; });
    if (revTotalEl) {
      revTotalEl.textContent = rev;
    }
    revItems.forEach(function (li, index) {
      if (index + 1 <= parseInt(rev, 10)) {
        li.removeAttribute("hidden");
      } else {
        li.setAttribute("hidden", "");
      }
    });
    resetAck();
    show("handover");
    announce("Übergabe geöffnet: " + (btn.getAttribute("data-pw-title") || "") + ", Revision " + rev + " geladen.");
  }

  Array.prototype.slice.call(root.querySelectorAll("[data-pw-ho]")).forEach(function (btn) {
    btn.addEventListener("click", function () { openHandover(btn); });
  });

  var ackBtn = root.querySelector("[data-pw-ack]");
  if (ackBtn) {
    ackBtn.addEventListener("click", function () {
      var revEl = revEls.length ? revEls[0] : null;
      var rev = revEl ? revEl.textContent : "";
      if (ackStatus) {
        ackStatus.classList.add("is-done");
        ackStatus.textContent = "Kenntnis genommen: Revision " + rev + " bestätigt. Der Vorgang bleibt offen – Kenntnisnahme erledigt die Übergabe nicht.";
      }
      announce("Kenntnisnahme vermerkt für Revision " + rev + ". Der Vorgang bleibt offen.");
    });
  }

  /* Day tasks – separate checkboxes (green daily / yellow weekday / blue extra) */
  var tasks = Array.prototype.slice.call(root.querySelectorAll("[data-pw-task]"));
  var taskCount = root.querySelector("[data-pw-task-count]");

  function updateTasks() {
    var done = tasks.filter(function (t) { return t.checked; }).length;
    if (taskCount) {
      taskCount.textContent = done + " von " + tasks.length + " erledigt";
    }
  }

  tasks.forEach(function (task) {
    task.addEventListener("change", function () {
      updateTasks();
      var label = task.parentNode ? (task.parentNode.textContent || "").replace(/\s+/g, " ").trim() : "";
      announce((task.checked ? "Aufgabe erledigt: " : "Aufgabe wieder offen: ") + label);
    });
  });
  updateTasks();

  /* Reset – clears local preview state only */
  var resetBtn = root.querySelector("[data-pw-reset]");
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      tasks.forEach(function (t) { t.checked = false; });
      updateTasks();
      var initialHandover = root.querySelector("[data-pw-ho]");
      if (initialHandover) { openHandover(initialHandover); }
      resetAck();
      show("overview");
      announce("Vorschau zurückgesetzt. Ansicht: Übersicht.");
    });
  }

  /* Hero CTA: scroll (anchor) and move focus into the interactive preview */
  Array.prototype.slice.call(document.querySelectorAll("[data-pw-start]")).forEach(function (link) {
    link.addEventListener("click", function () {
      window.setTimeout(function () {
        var panel = currentPanel();
        var focusable = panel ? panel.querySelector("button, input, summary, a[href]") : null;
        if (!focusable) {
          focusable = steps.length ? steps[0] : null;
        }
        if (focusable && focusable.focus) {
          focusable.focus({ preventScroll: true });
        }
      }, 80);
    });
  });
})();
