const PROFILES = {
  rettungsdienst: {
    banner: "Demo-Modus · Rettungsdienst",
    station: "Rettungswache Musterstadt",
    role: "Schichtleitung",
    handovers: [
      {
        title: "RTW 1 – Defibrillator-Akku tauschen",
        priority: "urgent",
        status: "open",
      },
      {
        title: "Funkgerät Wachzimmer knackt",
        priority: "important",
        status: "progress",
      },
      {
        title: "Kühlschrank Medikamente – Log fehlt",
        priority: "normal",
        status: "open",
      },
    ],
  },
  feuerwehr: {
    banner: "Demo-Modus · Feuerwehr",
    station: "Feuerwehrwache Nord",
    role: "Wachabteilungsführer",
    handovers: [
      {
        title: "HLF 20 – Atemschutzgerät 3 außer Betrieb",
        priority: "urgent",
        status: "open",
      },
      {
        title: "Hydrantentest Straße 12 verschoben",
        priority: "important",
        status: "progress",
      },
      {
        title: "Schlauchturm – Beleuchtung defekt",
        priority: "normal",
        status: "open",
      },
    ],
  },
  polizei: {
    banner: "Demo-Modus · Polizei",
    station: "Polizeiwache Innenstadt",
    role: "Dienstgruppenleitung",
    handovers: [
      {
        title: "Streifenwagen 3 – Reifenprofil vorne links",
        priority: "urgent",
        status: "open",
      },
      {
        title: "Bodycam-Akkus nachladen",
        priority: "important",
        status: "progress",
      },
      {
        title: "Schlüsselbrett Zellentür – Ersatz fehlt",
        priority: "normal",
        status: "open",
      },
    ],
  },
  ffw: {
    banner: "Demo-Modus · Freiwillige Feuerwehr",
    station: "FFW Musterdorf",
    role: "Wehrführung",
    handovers: [
      {
        title: "Gerätehaus – Heizung macht Geräusche",
        priority: "important",
        status: "open",
      },
      {
        title: "Übung Verkehrsabsicherung – Material fehlt",
        priority: "normal",
        status: "open",
      },
      {
        title: "TS-Batterie prüfen",
        priority: "important",
        status: "progress",
      },
    ],
  },
};

const PRIORITY_LABEL = {
  urgent: "Dringend",
  important: "Wichtig",
  normal: "Normal",
};

const STATUS_LABEL = {
  open: "Offen",
  progress: "In Bearbeitung",
};

function countMetrics(handovers) {
  return {
    open: handovers.filter((h) => h.status === "open").length,
    progress: handovers.filter((h) => h.status === "progress").length,
    urgent: handovers.filter((h) => h.priority === "urgent").length,
  };
}

function renderProfile(service) {
  const profile = PROFILES[service];
  if (!profile) return;

  const banner = document.getElementById("demo-banner");
  const station = document.getElementById("demo-station");
  const role = document.getElementById("demo-role");
  const list = document.getElementById("demo-list");
  const panel = document.getElementById("demo-panel");
  const metrics = countMetrics(profile.handovers);

  banner.textContent = profile.banner;
  station.textContent = profile.station;
  role.textContent = profile.role;
  document.getElementById("m-open").textContent = String(metrics.open);
  document.getElementById("m-progress").textContent = String(metrics.progress);
  document.getElementById("m-urgent").textContent = String(metrics.urgent);

  list.replaceChildren(
    ...profile.handovers.map((item) => {
      const li = document.createElement("li");
      const title = document.createElement("p");
      title.className = "handover-title";
      title.textContent = item.title;

      const meta = document.createElement("div");
      meta.className = "handover-meta";

      const pChip = document.createElement("span");
      pChip.className = `chip chip-${item.priority}`;
      pChip.textContent = PRIORITY_LABEL[item.priority];

      const sChip = document.createElement("span");
      sChip.className = `chip chip-${item.status === "progress" ? "progress" : "open"}`;
      sChip.textContent = STATUS_LABEL[item.status];

      meta.append(pChip, sChip);
      li.append(title, meta);
      return li;
    }),
  );

  const tabId =
    service === "feuerwehr"
      ? "tab-fw"
      : service === "polizei"
        ? "tab-pol"
        : service === "ffw"
          ? "tab-ffw"
          : "tab-rd";
  panel.setAttribute("aria-labelledby", tabId);
}

function setActiveTab(service) {
  document.querySelectorAll(".demo-tab").forEach((tab) => {
    const active = tab.dataset.service === service;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  renderProfile(service);
  const openApp = document.getElementById("demo-open-app");
  if (openApp) openApp.href = `app/?service=${service}`;
}

document.querySelectorAll(".demo-tab").forEach((tab) => {
  tab.addEventListener("click", () => setActiveTab(tab.dataset.service));
});

document.querySelectorAll("[data-demo]").forEach((link) => {
  link.addEventListener("click", () => {
    const service = link.getAttribute("data-demo");
    if (service && PROFILES[service]) setActiveTab(service);
  });
});

const params = new URLSearchParams(window.location.search);
const initial = params.get("demo");
setActiveTab(
  initial && PROFILES[initial] ? initial : "rettungsdienst",
);

if (initial && PROFILES[initial]) {
  document.getElementById("demo")?.scrollIntoView({ behavior: "smooth" });
}
