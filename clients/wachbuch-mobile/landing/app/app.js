(() => {
  const PROFILES = window.WACHBUCH_DEMO;
  const STORAGE_KEY = "wachbuch-demo-service";
  const ACK_KEY = "wachbuch-demo-acks";

  const PRIORITY_LABEL = {
    urgent: "Dringend",
    important: "Wichtig",
    normal: "Normal",
    done: "Erledigt",
  };

  const STATUS_LABEL = {
    open: "Offen",
    in_progress: "In Bearbeitung",
    waiting: "Wartend",
    done: "Erledigt",
  };

  const ASSET_STATUS = {
    ready: "Einsatzklar",
    limited: "Eingeschränkt",
    oob: "Außer Betrieb",
    workshop: "Werkstatt",
  };

  const state = {
    service: null,
    view: "overview",
    query: "",
    statusFilter: null,
    priorityFilter: null,
    defectStatusFilter: null,
    detailId: null,
    defectId: null,
    acks: loadAcks(),
  };

  const els = {
    setup: document.getElementById("setup"),
    shell: document.getElementById("shell"),
    serviceList: document.getElementById("service-list"),
    main: document.getElementById("main"),
    rail: document.getElementById("rail-nav"),
    bottom: document.getElementById("bottom-nav"),
    topStation: document.getElementById("top-station"),
    demoLabel: document.getElementById("demo-label"),
    dialog: document.getElementById("dialog-root"),
    switchBtn: document.getElementById("btn-switch"),
  };

  function loadAcks() {
    try {
      return JSON.parse(localStorage.getItem(ACK_KEY) || "{}");
    } catch {
      return {};
    }
  }

  function saveAcks() {
    localStorage.setItem(ACK_KEY, JSON.stringify(state.acks));
  }

  function profile() {
    return PROFILES[state.service];
  }

  function ackKey(handoverId) {
    return `${state.service}:${handoverId}`;
  }

  function acksFor(handoverId) {
    return state.acks[ackKey(handoverId)] || [];
  }

  function metrics(handovers) {
    return {
      open: handovers.filter((h) => h.status === "open").length,
      progress: handovers.filter((h) => h.status === "in_progress").length,
      urgent: handovers.filter((h) => h.priority === "urgent").length,
    };
  }

  function defectMetrics() {
    const defects = profile().defects || [];
    return {
      open: defects.filter((d) => d.status !== "done").length,
      urgent: defects.filter((d) => d.priority === "urgent" && d.status !== "done")
        .length,
    };
  }

  function unackedUrgentCount() {
    return profile().handovers.filter(
      (h) =>
        h.priority === "urgent" &&
        h.status !== "done" &&
        acksFor(h.id).length === 0,
    ).length;
  }

  function filteredHandovers() {
    const p = profile();
    const q = state.query.trim().toLowerCase();
    return p.handovers.filter((item) => {
      if (state.statusFilter && item.status !== state.statusFilter) return false;
      if (state.priorityFilter && item.priority !== state.priorityFilter) {
        return false;
      }
      if (!q) return true;
      return (
        item.title.toLowerCase().includes(q) ||
        item.description.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q)
      );
    });
  }

  function filteredDefects() {
    const defects = profile().defects || [];
    if (!state.defectStatusFilter) return defects;
    return defects.filter((d) => d.status === state.defectStatusFilter);
  }

  function icon(name) {
    const labels = {
      home: "⌂",
      list: "☰",
      user: "◎",
      cal: "▦",
      coffee: "♨",
      check: "☑",
      defect: "⚠",
      asset: "▣",
      chart: "▥",
    };
    return `<span class="icon" aria-hidden="true">${labels[name] || "•"}</span>`;
  }

  function chipsFor(item) {
    const statusClass =
      item.status === "done"
        ? "done-status"
        : item.status === "waiting"
          ? "waiting"
          : item.status;
    return `
      <span class="chip chip-${item.priority}">${PRIORITY_LABEL[item.priority] || item.priority}</span>
      <span class="chip chip-${statusClass}">${STATUS_LABEL[item.status] || item.status}</span>
    `;
  }

  function assetChip(status) {
    return `<span class="asset-chip asset-${status}">${ASSET_STATUS[status] || status}</span>`;
  }

  function isNavCurrent(id) {
    if (state.view === id) return true;
    if (
      ["calendar", "coffee", "checklists"].includes(state.view) &&
      id === "overview"
    ) {
      return true;
    }
    return false;
  }

  function renderNav() {
    const items = [
      { id: "overview", label: "Übersicht", glyph: "home" },
      { id: "handovers", label: "Übergaben", glyph: "list" },
      { id: "defects", label: "Mängel", glyph: "defect" },
      { id: "assets", label: "Geräte", glyph: "asset" },
      { id: "reports", label: "Auswertung", glyph: "chart" },
      { id: "account", label: "Konto", glyph: "user" },
    ];
    const html = items
      .map(
        (item) => `
      <button type="button" class="nav-btn" data-view="${item.id}" aria-current="${
        isNavCurrent(item.id) ? "page" : "false"
      }">
        ${icon(item.glyph)}
        <span>${item.label}</span>
      </button>`,
      )
      .join("");
    els.rail.innerHTML = html;
    els.bottom.innerHTML = html;
  }

  function renderAssetBoard() {
    const assets = profile().assets || [];
    if (!assets.length) return "";
    return `
      <h2 class="section-label">Statusboard</h2>
      <div class="asset-board">
        ${assets
          .map(
            (a) => `
          <button type="button" class="asset-card asset-${a.status}" data-view="assets">
            <strong>${a.label}</strong>
            ${assetChip(a.status)}
            <span>${a.note || "—"}</span>
          </button>`,
          )
          .join("")}
      </div>
    `;
  }

  function renderOverview() {
    const p = profile();
    const m = metrics(p.handovers);
    const dm = defectMetrics();
    const unacked = unackedUrgentCount();
    els.main.innerHTML = `
      <section class="station-hero" aria-labelledby="station-name">
        <h1 id="station-name">${p.station}</h1>
        <p>${p.role} · ${p.tagline}</p>
      </section>
      <h2 class="section-label">Lage auf einen Blick</h2>
      <div class="metrics metrics-4" aria-label="Kennzahlen">
        <div class="metric"><strong>${m.open}</strong><span>Übergaben offen</span></div>
        <div class="metric ${m.urgent ? "is-urgent" : ""}"><strong>${m.urgent}</strong><span>dringend</span></div>
        <div class="metric ${dm.open ? "is-urgent" : ""}"><strong>${dm.open}</strong><span>Mängel offen</span></div>
        <div class="metric"><strong>${unacked}</strong><span>unquittiert</span></div>
      </div>
      ${renderAssetBoard()}
      <h2 class="section-label">Schnellzugriff</h2>
      <div class="module-row module-row-4">
        <button type="button" class="module-tile" data-view="defects">
          ${icon("defect")}<strong>Mängel</strong><span>Owner, Frist, Status</span>
        </button>
        <button type="button" class="module-tile" data-view="assets">
          ${icon("asset")}<strong>Geräte</strong><span>Status & Pools</span>
        </button>
        <button type="button" class="module-tile" data-view="checklists">
          ${icon("check")}<strong>Checklisten</strong><span>Wiederkehrend</span>
        </button>
        <button type="button" class="module-tile" data-view="reports">
          ${icon("chart")}<strong>Auswertung</strong><span>Ampel & Owner</span>
        </button>
      </div>
      <h2 class="section-label">Aktuelle Hinweise</h2>
      <div class="list">
        ${p.handovers
          .filter((h) => h.status !== "done")
          .slice(0, 3)
          .map(
            (item, index) => `
          <button type="button" class="handover" data-detail="${item.id}" style="animation-delay:${index * 50}ms">
            <div class="meta">${chipsFor(item)}${
              acksFor(item.id).length
                ? '<span class="chip chip-ack">Quittiert</span>'
                : ""
            }</div>
            <h3>${item.title}</h3>
            <p class="sub">${item.category} · ${item.updated}</p>
          </button>`,
          )
          .join("")}
      </div>
    `;
  }

  function handoverListHtml(items) {
    if (!items.length) {
      return `<p class="empty">Keine Übergaben für diese Filter.</p>`;
    }
    return items
      .map(
        (item, index) => `
      <button type="button" class="handover" data-detail="${item.id}" style="animation-delay:${index * 40}ms">
        <div class="meta">${chipsFor(item)}${
          acksFor(item.id).length
            ? '<span class="chip chip-ack">Quittiert</span>'
            : ""
        }</div>
        <h3>${item.title}</h3>
        <p class="sub">${item.category} · ${item.author} · ${item.updated}</p>
      </button>`,
      )
      .join("");
  }

  function refreshHandoverResults() {
    const items = filteredHandovers();
    const count = document.getElementById("handover-count");
    const list = document.getElementById("handover-list");
    if (count) {
      count.textContent = `${items.length} von ${profile().handovers.length} Übergaben`;
    }
    if (list) list.innerHTML = handoverListHtml(items);
    document.querySelectorAll("[data-status]").forEach((btn) => {
      btn.setAttribute(
        "aria-pressed",
        String(state.statusFilter === btn.dataset.status),
      );
    });
    document.querySelectorAll("[data-priority]").forEach((btn) => {
      btn.setAttribute(
        "aria-pressed",
        String(state.priorityFilter === btn.dataset.priority),
      );
    });
  }

  function renderHandovers() {
    const items = filteredHandovers();
    els.main.innerHTML = `
      <h1 class="section-label">Übergaben</h1>
      <div class="toolbar">
        <label class="sr-only" for="search">Übergaben durchsuchen</label>
        <input id="search" class="search" type="search" placeholder="Übergaben durchsuchen" value="${state.query.replace(/"/g, "&quot;")}" />
      </div>
      <div class="filters" aria-label="Status filtern">
        ${["open", "in_progress", "done"]
          .map(
            (s) => `
          <button type="button" class="chip-btn" data-status="${s}" aria-pressed="${
            state.statusFilter === s
          }">${STATUS_LABEL[s]}</button>`,
          )
          .join("")}
      </div>
      <div class="filters" style="margin:0.55rem 0 1rem" aria-label="Priorität filtern">
        ${["urgent", "important", "normal"]
          .map(
            (p) => `
          <button type="button" class="chip-btn" data-priority="${p}" aria-pressed="${
            state.priorityFilter === p
          }">${PRIORITY_LABEL[p]}</button>`,
          )
          .join("")}
      </div>
      <p class="sub" id="handover-count" style="margin:0 0 0.85rem;color:var(--text-muted)">${items.length} von ${profile().handovers.length} Übergaben</p>
      <div class="list" id="handover-list">${handoverListHtml(items)}</div>
    `;
  }

  function renderDefects() {
    const items = filteredDefects();
    els.main.innerHTML = `
      <h1 class="section-label">Mängel</h1>
      <p class="hint-line">Owner, Frist und Status — schichtübergreifend, ohne Einsatzdaten.</p>
      <div class="filters" style="margin-bottom:1rem" aria-label="Mangel-Status">
        ${["open", "in_progress", "waiting", "done"]
          .map(
            (s) => `
          <button type="button" class="chip-btn" data-defect-status="${s}" aria-pressed="${
            state.defectStatusFilter === s
          }">${STATUS_LABEL[s]}</button>`,
          )
          .join("")}
      </div>
      <div class="list">
        ${
          items.length
            ? items
                .map(
                  (d, index) => `
          <button type="button" class="handover" data-defect="${d.id}" style="animation-delay:${index * 40}ms">
            <div class="meta">${chipsFor(d)}</div>
            <h3>${d.title}</h3>
            <p class="sub">${d.asset_ref} · ${d.owner} · fällig ${d.due}</p>
          </button>`,
                )
                .join("")
            : `<p class="empty">Keine Mängel für diesen Filter.</p>`
        }
      </div>
    `;
  }

  function renderAssets() {
    const p = profile();
    const assets = p.assets || [];
    const inventory = p.inventory || [];
    els.main.innerHTML = `
      <h1 class="section-label">Geräte & Status</h1>
      ${renderAssetBoard()}
      <h2 class="section-label">Schlüssel & Pools</h2>
      <p class="hint-line">Checkout / Checkin — Demo speichert nur lokal in dieser Sitzung.</p>
      <div class="list">
        ${inventory
          .map(
            (item) => `
          <article class="panel-block inventory-row">
            <div>
              <h3>${item.label}</h3>
              <p>${
                item.holder
                  ? `Bei <strong>${item.holder}</strong> seit ${item.since}${item.note ? ` · ${item.note}` : ""}`
                  : item.note
                    ? `<span class="warn-text">${item.note}</span> · verfügbar`
                    : "Verfügbar"
              }</p>
            </div>
            <button type="button" class="btn ${item.holder ? "btn-ghost" : "btn-cta"} btn-compact" data-inventory="${item.id}">
              ${item.holder ? "Zurückgeben" : "Ausgeben"}
            </button>
          </article>`,
          )
          .join("")}
      </div>
      <button type="button" class="btn btn-ghost" data-view="overview">← Zur Übersicht</button>
    `;
  }

  function renderCalendar() {
    const p = profile();
    els.main.innerHTML = `
      <h1 class="section-label">Kalender</h1>
      ${p.calendar
        .map(
          (entry) => `
        <article class="panel-block">
          <h3>${entry.title}</h3>
          <p>${entry.when}</p>
          <p>${entry.location}</p>
        </article>`,
        )
        .join("")}
      <button type="button" class="btn btn-ghost" data-view="overview">← Zur Übersicht</button>
    `;
  }

  function renderCoffee() {
    const coffee = profile().coffee;
    els.main.innerHTML = `
      <h1 class="section-label">Kaffeekasse</h1>
      <article class="panel-block">
        <p>Aktueller Kassenstand</p>
        <p class="balance">${coffee.balance}</p>
        <p>${coffee.hint}</p>
      </article>
      <h2 class="section-label">Letzte Buchungen</h2>
      ${coffee.ledger
        .map(
          (row) => `
        <article class="panel-block">
          <h3>${row.amount}</h3>
          <p>${row.note}</p>
          <p>${row.who}</p>
        </article>`,
        )
        .join("")}
      <button type="button" class="btn btn-ghost" data-view="overview">← Zur Übersicht</button>
    `;
  }

  function intervalLabel(interval) {
    if (interval === "weekly") return "Wöchentlich";
    if (interval === "monthly") return "Monatlich";
    if (interval === "daily") return "Täglich";
    return "";
  }

  function renderChecklistCard(list, listIndex) {
    const dueBadge = list.overdue
      ? '<span class="badge-overdue">Überfällig</span>'
      : list.due_next === "heute"
        ? '<span class="badge-due">Fällig heute</span>'
        : "";
    return `
      <article class="panel-block">
        <h3>${list.title}</h3>
        <p class="interval-tag">${intervalLabel(list.interval)} ${dueBadge}</p>
        ${list.items
          .map(
            (item, itemIndex) => `
          <label class="check-item">
            <input type="checkbox" data-list="${listIndex}" data-item="${itemIndex}" ${
              item.checked ? "checked" : ""
            } />
            <span>${item.text}</span>
          </label>`,
          )
          .join("")}
      </article>`;
  }

  function renderChecklists() {
    const lists = profile().checklists;
    const due = lists
      .map((list, index) => ({ list, index }))
      .filter(({ list }) => list.overdue || list.due_next === "heute");
    const rest = lists
      .map((list, index) => ({ list, index }))
      .filter(({ list }) => !list.overdue && list.due_next !== "heute");
    els.main.innerHTML = `
      <h1 class="section-label">Checklisten</h1>
      <p class="hint-line">Wiederkehrende Checks (Phase F): Intervalle mit Fälligkeit — Demo ohne Server-Scheduler.</p>
      ${
        due.length
          ? `<h2 class="section-label">Fällig heute / überfällig</h2>${due
              .map(({ list, index }) => renderChecklistCard(list, index))
              .join("")}`
          : ""
      }
      ${
        rest.length
          ? `<h2 class="section-label">Weitere</h2>${rest
              .map(({ list, index }) => renderChecklistCard(list, index))
              .join("")}`
          : ""
      }
      <button type="button" class="btn btn-ghost" data-view="overview">← Zur Übersicht</button>
    `;
  }

  function reportStats() {
    const p = profile();
    const defects = p.defects || [];
    const assets = p.assets || [];
    const lists = p.checklists || [];
    const openDefects = defects.filter((d) => d.status !== "done");
    const byOwner = {};
    openDefects.forEach((d) => {
      const key = d.owner || "ohne Owner";
      byOwner[key] = (byOwner[key] || 0) + 1;
    });
    const ready = assets.filter((a) => a.status === "ready").length;
    const ampQuote = assets.length
      ? Math.round((ready / assets.length) * 100)
      : 0;
    const overdueChecks = lists.filter((c) => c.overdue).length;
    return { openDefects, byOwner, ampQuote, overdueChecks, assets, ready };
  }

  function renderReports() {
    const stats = reportStats();
    const ownerRows = Object.entries(stats.byOwner)
      .map(
        ([owner, count]) =>
          `<li><strong>${count}</strong> · ${owner}</li>`,
      )
      .join("");
    els.main.innerHTML = `
      <h1 class="section-label">Auswertung</h1>
      <p class="hint-line">Leichte Client-Aggregation über Demo-Daten (Phase I) — kein Server-Report.</p>
      <div class="metrics metrics-3" aria-label="Auswertung">
        <div class="metric ${stats.openDefects.length ? "is-urgent" : ""}">
          <strong>${stats.openDefects.length}</strong><span>offene Mängel</span>
        </div>
        <div class="metric ${stats.overdueChecks ? "is-urgent" : ""}">
          <strong>${stats.overdueChecks}</strong><span>Checks überfällig</span>
        </div>
        <div class="metric">
          <strong>${stats.ampQuote}%</strong><span>Assets einsatzklar</span>
        </div>
      </div>
      <h2 class="section-label">Offene Mängel nach Owner</h2>
      <ul class="report-list">
        ${ownerRows || "<li>Keine offenen Mängel.</li>"}
      </ul>
      <h2 class="section-label">Asset-Ampel</h2>
      <p class="hint-line">${stats.ready} von ${stats.assets.length} Fahrzeugen/Geräten einsatzklar.</p>
      <button type="button" class="btn btn-ghost" data-view="overview">← Zur Übersicht</button>
    `;
  }

  function renderAccount() {
    const p = profile();
    const dm = defectMetrics();
    els.main.innerHTML = `
      <h1 class="section-label">Konto</h1>
      <dl class="panel-block">
        <div class="account-row"><dt>Angemeldet als</dt><dd>${p.username}</dd></div>
        <div class="account-row"><dt>Rolle</dt><dd>${p.role}</dd></div>
        <div class="account-row"><dt>Organisation</dt><dd>${p.label}</dd></div>
        <div class="account-row"><dt>Offene Mängel</dt><dd>${dm.open}</dd></div>
        <div class="account-row"><dt>Server</dt><dd>Demo (offline)</dd></div>
        <div class="account-row"><dt>Fahrplan</dt><dd>Phase A–D Prototyp</dd></div>
      </dl>
      <div class="toolbar">
        <button type="button" class="btn btn-cta" id="btn-exit-demo">Demo beenden</button>
        <a class="btn btn-ghost" href="../docs-hint.html" hidden></a>
        <button type="button" class="btn btn-ghost" data-view="overview">Zur Übersicht</button>
      </div>
      <p class="hint-line">Produktfahrplan: <code>docs/FAHRPLAN-BEHOERDEN.md</code> im Repo.</p>
    `;
    document.getElementById("btn-exit-demo")?.addEventListener("click", showSetup);
  }

  function renderDetail() {
    if (state.defectId != null) {
      renderDefectDetail();
      return;
    }
    const item = profile().handovers.find((h) => h.id === state.detailId);
    if (!item) {
      els.dialog.classList.add("app-hidden");
      els.dialog.innerHTML = "";
      return;
    }
    const acks = acksFor(item.id);
    els.dialog.classList.remove("app-hidden");
    els.dialog.innerHTML = `
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <div class="meta">${chipsFor(item)}</div>
        <h2 id="detail-title">${item.title}</h2>
        <p>${item.description}</p>
        <p><strong>Kategorie:</strong> ${item.category}</p>
        <p><strong>Autor:</strong> ${item.author}</p>
        <p><strong>Aktualisiert:</strong> ${item.updated}</p>
        <h3 class="section-label" style="margin-top:1rem">Quittierung</h3>
        ${
          acks.length
            ? `<ul class="ack-list">${acks
                .map((a) => `<li>${a.by} · ${a.at}</li>`)
                .join("")}</ul>`
            : `<p class="hint-line">Noch nicht quittiert.</p>`
        }
        <div class="dialog-actions dialog-actions-split">
          <button type="button" class="btn btn-ghost" id="btn-to-defect">Als Mangel</button>
          <button type="button" class="btn btn-cta" id="btn-ack">Übernommen</button>
          <button type="button" class="btn btn-ghost" id="close-detail">Schließen</button>
        </div>
      </div>
    `;
    document.getElementById("close-detail")?.addEventListener("click", closeDialogs);
    document.getElementById("btn-ack")?.addEventListener("click", () => {
      const key = ackKey(item.id);
      const list = state.acks[key] || [];
      const by = profile().username;
      if (!list.some((a) => a.by === by)) {
        list.push({
          by,
          at: new Date().toLocaleString("de-DE", {
            hour: "2-digit",
            minute: "2-digit",
            day: "2-digit",
            month: "2-digit",
          }),
        });
        state.acks[key] = list;
        saveAcks();
      }
      renderDetail();
      if (state.view === "overview" || state.view === "handovers") renderView();
    });
    document.getElementById("btn-to-defect")?.addEventListener("click", () => {
      const defects = profile().defects;
      const nextId = Math.max(0, ...defects.map((d) => d.id)) + 1;
      defects.unshift({
        id: nextId,
        title: item.title,
        description: item.description,
        asset_ref: item.category,
        priority: item.priority === "done" ? "normal" : item.priority,
        status: "open",
        owner: profile().username,
        due: "offen",
        category: "task",
      });
      state.detailId = null;
      state.defectId = nextId;
      state.view = "defects";
      renderView();
      renderDetail();
    });
    els.dialog.onclick = (event) => {
      if (event.target === els.dialog) closeDialogs();
    };
  }

  function renderDefectDetail() {
    const item = (profile().defects || []).find((d) => d.id === state.defectId);
    if (!item) {
      els.dialog.classList.add("app-hidden");
      els.dialog.innerHTML = "";
      return;
    }
    if (!Array.isArray(item.attachments)) item.attachments = [];
    const previews = item.attachments
      .map(
        (file) => `
        <figure class="attach-preview">
          <img src="${file.url}" alt="${file.name}" />
          <figcaption>${file.name}</figcaption>
        </figure>`,
      )
      .join("");
    els.dialog.classList.remove("app-hidden");
    els.dialog.innerHTML = `
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="defect-title">
        <div class="meta">${chipsFor(item)}</div>
        <h2 id="defect-title">${item.title}</h2>
        <p>${item.description}</p>
        <p><strong>Bezug:</strong> ${item.asset_ref}</p>
        <p><strong>Owner:</strong> ${item.owner}</p>
        <p><strong>Fällig:</strong> ${item.due}</p>
        <div class="filters" style="margin:1rem 0" aria-label="Status setzen">
          ${["open", "in_progress", "waiting", "done"]
            .map(
              (s) => `
            <button type="button" class="chip-btn" data-set-defect-status="${s}" aria-pressed="${
              item.status === s
            }">${STATUS_LABEL[s]}</button>`,
            )
            .join("")}
        </div>
        <h3 class="section-label">Anhänge (Demo)</h3>
        <p class="hint-line">Phase E: lokale Vorschau per objectURL — kein Server-Upload.</p>
        <div class="attach-grid">${previews || "<p class='empty'>Noch keine Fotos.</p>"}</div>
        <label class="btn btn-ghost attach-label">
          Foto / Datei wählen
          <input id="defect-attach" type="file" accept="image/*" hidden />
        </label>
        <div class="dialog-actions">
          <button type="button" class="btn btn-cta" id="close-detail">Schließen</button>
        </div>
      </div>
    `;
    document.getElementById("close-detail")?.addEventListener("click", closeDialogs);
    document.getElementById("defect-attach")?.addEventListener("change", (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      const url = URL.createObjectURL(file);
      item.attachments.push({ name: file.name, url });
      renderDefectDetail();
    });
    els.dialog.onclick = (event) => {
      if (event.target === els.dialog) closeDialogs();
    };
  }

  function closeDialogs() {
    state.detailId = null;
    state.defectId = null;
    els.dialog.classList.add("app-hidden");
    els.dialog.innerHTML = "";
  }

  function renderView() {
    document.documentElement.style.setProperty(
      "--service-accent",
      profile().accent,
    );
    els.topStation.textContent = profile().station;
    els.demoLabel.textContent = `Demo-Modus · ${profile().label}`;
    renderNav();
    switch (state.view) {
      case "handovers":
        renderHandovers();
        break;
      case "defects":
        renderDefects();
        break;
      case "assets":
        renderAssets();
        break;
      case "calendar":
        renderCalendar();
        break;
      case "coffee":
        renderCoffee();
        break;
      case "checklists":
        renderChecklists();
        break;
      case "reports":
        renderReports();
        break;
      case "account":
        renderAccount();
        break;
      default:
        renderOverview();
    }
    if (state.detailId != null || state.defectId != null) renderDetail();
    else {
      els.dialog.classList.add("app-hidden");
      els.dialog.innerHTML = "";
    }
  }

  function enterService(serviceId) {
    if (!PROFILES[serviceId]) return;
    state.service = serviceId;
    state.view = "overview";
    state.query = "";
    state.statusFilter = null;
    state.priorityFilter = null;
    state.defectStatusFilter = null;
    state.detailId = null;
    state.defectId = null;
    localStorage.setItem(STORAGE_KEY, serviceId);
    const url = new URL(window.location.href);
    url.searchParams.set("service", serviceId);
    history.replaceState({}, "", url);
    els.setup.classList.add("app-hidden");
    els.shell.classList.remove("app-hidden");
    renderView();
    els.main.focus({ preventScroll: true });
  }

  function showSetup() {
    state.service = null;
    localStorage.removeItem(STORAGE_KEY);
    const url = new URL(window.location.href);
    url.searchParams.delete("service");
    history.replaceState({}, "", url);
    els.shell.classList.add("app-hidden");
    els.setup.classList.remove("app-hidden");
    closeDialogs();
  }

  function renderSetup() {
    const order = ["rettungsdienst", "feuerwehr", "ffw", "polizei"];
    els.serviceList.innerHTML = order
      .map((id) => {
        const p = PROFILES[id];
        return `
        <button type="button" class="service-option" data-service="${id}" style="--opt-accent:${p.accent}">
          <span class="mark" aria-hidden="true"></span>
          <span>
            <h2>${p.label}</h2>
            <p>${p.tagline}</p>
          </span>
          <span aria-hidden="true">›</span>
        </button>`;
      })
      .join("");
  }

  function onClick(event) {
    const serviceBtn = event.target.closest("[data-service]");
    if (serviceBtn) {
      enterService(serviceBtn.dataset.service);
      return;
    }

    const setDefectStatus = event.target.closest("[data-set-defect-status]");
    if (setDefectStatus && state.defectId != null) {
      const defect = profile().defects.find((d) => d.id === state.defectId);
      if (defect) {
        defect.status = setDefectStatus.dataset.setDefectStatus;
        renderDefectDetail();
        if (state.view === "defects" || state.view === "overview") renderView();
      }
      return;
    }

    const inventoryBtn = event.target.closest("[data-inventory]");
    if (inventoryBtn && state.service) {
      const item = profile().inventory.find(
        (i) => i.id === inventoryBtn.dataset.inventory,
      );
      if (item) {
        if (item.holder) {
          item.holder = null;
          item.since = null;
          if (item.note === "vermisst") item.note = "";
        } else {
          item.holder = profile().username;
          item.since = new Date().toLocaleTimeString("de-DE", {
            hour: "2-digit",
            minute: "2-digit",
          });
        }
        renderAssets();
      }
      return;
    }

    const viewBtn = event.target.closest("[data-view]");
    if (viewBtn && state.service) {
      state.view = viewBtn.dataset.view;
      state.detailId = null;
      state.defectId = null;
      renderView();
      return;
    }

    const detailBtn = event.target.closest("[data-detail]");
    if (detailBtn) {
      state.defectId = null;
      state.detailId = Number(detailBtn.dataset.detail);
      renderDetail();
      return;
    }

    const defectBtn = event.target.closest("[data-defect]");
    if (defectBtn) {
      state.detailId = null;
      state.defectId = Number(defectBtn.dataset.defect);
      renderDetail();
      return;
    }

    const statusBtn = event.target.closest("[data-status]");
    if (statusBtn) {
      const value = statusBtn.dataset.status;
      state.statusFilter = state.statusFilter === value ? null : value;
      refreshHandoverResults();
      return;
    }

    const priorityBtn = event.target.closest("[data-priority]");
    if (priorityBtn) {
      const value = priorityBtn.dataset.priority;
      state.priorityFilter = state.priorityFilter === value ? null : value;
      refreshHandoverResults();
      return;
    }

    const defectStatusBtn = event.target.closest("[data-defect-status]");
    if (defectStatusBtn) {
      const value = defectStatusBtn.dataset.defectStatus;
      state.defectStatusFilter =
        state.defectStatusFilter === value ? null : value;
      renderDefects();
    }
  }

  function onInput(event) {
    if (event.target.id !== "search") return;
    state.query = event.target.value;
    refreshHandoverResults();
  }

  function onChange(event) {
    const box = event.target.closest('input[type="checkbox"][data-list]');
    if (!box || !state.service) return;
    const listIndex = Number(box.dataset.list);
    const itemIndex = Number(box.dataset.item);
    const item = profile().checklists[listIndex]?.items[itemIndex];
    if (item) item.checked = box.checked;
  }

  els.switchBtn.addEventListener("click", showSetup);
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("input", onInput);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeDialogs();
  });

  renderSetup();

  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("service") || params.get("demo");
  const fromStorage = localStorage.getItem(STORAGE_KEY);
  const initial = fromQuery || fromStorage;
  if (initial && PROFILES[initial]) {
    enterService(initial);
  }
})();
