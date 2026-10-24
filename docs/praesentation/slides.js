/* Folien „Wachwerk“: Blättern per Pfeiltasten, Leertaste oder Klick.
   URL-Parameter: ?autoplay=1 blättert automatisch, ?record=1 blendet die
   Leiste aus (Video), ?theme=dark|light erzwingt Nacht/Tag, #3 öffnet Folie 3. */
(() => {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  const root = document.documentElement;
  const theme = params.get("theme");
  if (theme === "dark" || theme === "light") {
    root.setAttribute("data-theme", theme);
  }
  if (params.get("record") === "1") {
    root.classList.add("is-record");
  }

  const slides = [...document.querySelectorAll(".slide")];
  const count = document.querySelector("[data-count]");
  const progress = document.querySelector("[data-progress]");
  const musicBtn = document.querySelector("[data-music]");
  const AUTO_MS = 6200;
  let index = 0;
  let timer = null;

  function show(n) {
    index = (n + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      const on = i === index;
      slide.classList.toggle("is-on", on);
      slide.setAttribute("aria-hidden", on ? "false" : "true");
    });
    count.textContent = `${index + 1} / ${slides.length}`;
    progress.style.width = `${((index + 1) / slides.length) * 100}%`;
    document.title = `Wachwerk – ${slides[index].dataset.title || "Vorführung"}`;
  }

  function armAuto() {
    window.clearInterval(timer);
    if (params.get("autoplay") === "1") {
      timer = window.setInterval(() => show(index + 1), AUTO_MS);
    }
  }

  document.querySelector("[data-next]").addEventListener("click", () => { show(index + 1); armAuto(); });
  document.querySelector("[data-prev]").addEventListener("click", () => { show(index - 1); armAuto(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight" || event.key === " " || event.key === "PageDown") {
      event.preventDefault();
      show(index + 1);
      armAuto();
    } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
      event.preventDefault();
      show(index - 1);
      armAuto();
    }
  });

  /* Eigene, kurze Ambient-Figur – keine fremden Aufnahmen. Startet nur nach Klick. */
  let audioCtx = null;
  let master = null;
  let pad = null;
  let phraseTimer = null;
  let playing = false;

  function tone(freq, start, peak, length) {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.value = 0;
    osc.connect(gain);
    gain.connect(master);
    const t0 = audioCtx.currentTime + start;
    gain.gain.setValueAtTime(0, t0);
    gain.gain.linearRampToValueAtTime(peak, t0 + 0.1);
    gain.gain.exponentialRampToValueAtTime(0.001, t0 + length);
    osc.start(t0);
    osc.stop(t0 + length + 0.1);
  }

  function startMusic() {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor || playing) {
      return;
    }
    audioCtx = new Ctor();
    master = audioCtx.createGain();
    master.gain.value = 0.07;
    master.connect(audioCtx.destination);
    [196, 246.94, 293.66, 329.63, 392, 329.63, 293.66, 246.94].forEach((f, i) => tone(f, i * 0.85, 0.22, 1.6));
    pad = audioCtx.createOscillator();
    const padGain = audioCtx.createGain();
    pad.type = "triangle";
    pad.frequency.value = 98;
    padGain.gain.value = 0.04;
    pad.connect(padGain);
    padGain.connect(master);
    pad.start();
    phraseTimer = window.setInterval(() => {
      [261.63, 329.63, 392, 440, 392, 329.63].forEach((f, i) => tone(f, i * 0.95, 0.18, 1.4));
    }, 6800);
    playing = true;
    musicBtn.setAttribute("aria-pressed", "true");
  }

  function stopMusic() {
    playing = false;
    window.clearInterval(phraseTimer);
    if (audioCtx) {
      audioCtx.close();
    }
    audioCtx = null;
    master = null;
    pad = null;
    musicBtn.setAttribute("aria-pressed", "false");
  }

  musicBtn.addEventListener("click", () => (playing ? stopMusic() : startMusic()));

  function fromHash() {
    const n = Number.parseInt(window.location.hash.slice(1), 10);
    return Number.isFinite(n) && n >= 1 ? n - 1 : 0;
  }
  window.addEventListener("hashchange", () => show(fromHash()));
  show(fromHash());
  armAuto();
})();
