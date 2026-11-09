#!/usr/bin/env node
// Wachwerk accessibility gate (ROADMAP 0.28): axe-core on the main pages of each
// role, light and dark, plus the wall display screenshot/grid test at
// 1920x1080 and 1280x720 (kiosk via the display link), a session view of the
// display in a low window (1366x600: nothing cut off silently) and a
// no-horizontal-scroll check for every page run at phone width (390x844).
//
// Environment:
//   BASE_URL          default http://127.0.0.1:8765
//   DEMO_PASSWORD     default Demo-Passwort-12345 (load_demo_data)
//   DISPLAY_TOKEN     raw display link token (create in CI with a shell step)
//   TERMINAL_TOKEN    raw terminal start token
//   TERMINAL_CODE     station code for the terminal, default 1234
//   IDS_JSON          JSON with {handover, defect, checklist, vehicle, device, sop}
//   OUT_DIR           output dir for report.json, screenshots (default ./a11y-out)
//   A11Y_THEMES       comma list of theme variants (default all four)
//   FAIL_ON           comma list of impacts that fail the run (default critical,serious)
//   SEED_JSON         file written by tests/a11y/seed.py (tokens and ids)
//   A11Y_ROLES        comma list of roles (default all)
//
// Exit code 1 when a violation with an impact in FAIL_ON is found, the
// display grid assertion fails (kiosk or session view), a phone-width page
// scrolls sideways or a page cannot be tested.
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

let AxeBuilder = null;
try {
  AxeBuilder = require('@axe-core/playwright').default || require('@axe-core/playwright').AxeBuilder;
} catch (err) {
  AxeBuilder = null;
}
const AXE_SOURCE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');

const BASE = (process.env.BASE_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');
const PASSWORD = process.env.DEMO_PASSWORD || 'Demo-Passwort-12345';
const OUT = path.resolve(process.env.OUT_DIR || 'a11y-out');
// SEED_JSON: file written by tests/a11y/seed.py ({terminal, display, ids}).
const SEED = process.env.SEED_JSON ? JSON.parse(fs.readFileSync(process.env.SEED_JSON, 'utf8')) : {};
if (SEED.terminal && !process.env.TERMINAL_TOKEN) process.env.TERMINAL_TOKEN = SEED.terminal;
if (SEED.display && !process.env.DISPLAY_TOKEN) process.env.DISPLAY_TOKEN = SEED.display;
const IDS = SEED.ids || JSON.parse(process.env.IDS_JSON || '{}');
const FAIL_ON = (process.env.FAIL_ON || 'critical,serious').split(',').map((s) => s.trim()).filter(Boolean);
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

// colorScheme = prefers-color-scheme; cookie = app toggle (wb_theme -> <html data-theme>).
const ALL_THEMES = {
  light: { colorScheme: 'light', cookie: null },
  dark: { colorScheme: 'dark', cookie: null },
  'toggle-dark': { colorScheme: 'light', cookie: 'dark' },
  'toggle-light': { colorScheme: 'dark', cookie: 'light' },
};
const THEMES = (process.env.A11Y_THEMES || Object.keys(ALL_THEMES).join(','))
  .split(',').map((s) => s.trim()).filter((s) => ALL_THEMES[s]);

const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 844 };

const id = (key, fallback) => (IDS[key] !== undefined && IDS[key] !== null ? IDS[key] : fallback);

// ---------------------------------------------------------------- page list
function pagesFor(role) {
  const h = id('handover', 1);
  const d = id('defect', 1);
  const v = id('vehicle', 'demo-rtw-831');
  const m = id('device', 'demo-defi-rtw1');
  const s = id('sop', 'demo-sop-fahrzeugdesinfektion');
  const c = id('checklist', 1);
  const r = id('run', 1);
  if (role === 'anon') {
    return [
      ['landing', '/'],
      ['login', '/anmelden/'],
      ['vorfuehrung', '/vorfuehrung/'],
      ['install-guide', '/selbst-betreiben/'],
      ['it-privacy', '/it-und-datenschutz/'],
      ['privacy', '/datenschutz/'],
      ['legal-notice', '/impressum/'],
      ['help', '/hilfe/'],
      ['offline', '/offline/'],
    ];
  }
  if (role === 'admin') {
    return [
      ['dashboard', '/uebersicht/'],
      ['handover-list', '/uebergaben/'],
      ['handover-detail', `/uebergaben/${h}/`],
      ['handover-form', '/uebergaben/neu/'],
      ['handover-edit', `/uebergaben/${h}/bearbeiten/`],
      ['defect-list', '/maengel/'],
      ['defect-form', '/maengel/neu/'],
      ['defect-form-phone', '/maengel/neu/', PHONE],
      ['defect-detail', `/maengel/${d}/`],
      ['checklists-run', '/checklisten/'],
      ['checklist-schedules', '/checklisten/intervalle/'],
      ['checklist-history', `/checklisten/verlauf/${c}/`],
      ['checklist-run-detail', `/checklisten/verlauf/lauf/${r}/`],
      ['tasks', '/aufgaben/'],
      ['fleet', '/fuhrpark/'],
      ['vehicle-detail', `/fuhrpark/v/${v}/`],
      ['mpg-list', '/mpg/'],
      ['mpg-detail', `/mpg/d/${m}/`],
      ['warehouse', '/lager/'],
      ['orga-sop-list', '/orga/'],
      ['sop-detail', `/orga/sop/${s}/`],
      ['sop-form', '/orga/sop/neu/'],
      ['team', '/team/'],
      ['terminal-admin', '/team/terminal/'],
      ['calendar', '/kalender/'],
      ['calendar-form', '/kalender/neu/'],
      ['coffee', '/kaffeekasse/'],
      ['settings', '/einstellungen/'],
      ['presentation-settings', '/einstellungen/darstellung/'],
      ['display-links', '/einstellungen/display/'],
      ['pinboard', '/pinnwand/'],
      ['news', '/neuigkeiten/'],
      ['more', '/mehr/'],
      ['account', '/konto/'],
      ['reminder-settings', '/konto/erinnerungen/'],
      ['paper', '/papier/'],
      ['audit-log', '/audit/'],
    ];
  }
  if (role === 'member') {
    return [
      ['dashboard', '/uebersicht/'],
      ['handover-list', '/uebergaben/'],
      ['defect-form', '/maengel/neu/'],
      ['defect-form-phone', '/maengel/neu/', PHONE],
      ['checklists-run', '/checklisten/'],
      ['checklist-history', `/checklisten/verlauf/${c}/`],
      ['sop-detail', `/orga/sop/${s}/`],
      ['reminder-settings', '/konto/erinnerungen/'],
      ['coffee', '/kaffeekasse/'],
      ['calendar', '/kalender/'],
    ];
  }
  if (role === 'cashier') {
    return [
      ['coffee', '/kaffeekasse/'],
      ['coffee-book', '/kaffeekasse/mappe/'],
      ['coffee-cash', '/kaffeekasse/kasse/'],
      ['coffee-ledger', '/kaffeekasse/buchungen/'],
    ];
  }
  if (role === 'auditor') {
    return [
      ['audit-log', '/audit/'],
    ];
  }
  if (role === 'terminal') {
    // Reached after the lock screen; see loginTerminal().
    return [
      ['terminal-menu', '/terminal/alltag/'],
      ['terminal-defect-form', '/maengel/neu/'],
      ['terminal-checklists', '/checklisten/'],
      ['terminal-handovers', '/uebergaben/'],
    ];
  }
  return [];
}

// ---------------------------------------------------------------- helpers
async function settle(page) {
  try {
    await page.waitForLoadState('load', { timeout: 15000 });
  } catch (err) { /* ignore */ }
  await page.waitForTimeout(400);
}

async function runAxe(page) {
  if (AxeBuilder) {
    try {
      return await new AxeBuilder({ page }).withTags(TAGS).analyze();
    } catch (err) {
      console.warn(`AxeBuilder failed (${err.message.split('\n')[0]}), falling back to evaluate`);
    }
  }
  // Fallback: evaluate the axe source (not subject to the page CSP, unlike addScriptTag).
  await page.evaluate(AXE_SOURCE);
  return page.evaluate((tags) => window.axe.run(document, { runOnly: { type: 'tag', values: tags } }), TAGS);
}

async function newContext(browser, theme, viewport, storageState) {
  const context = await browser.newContext({
    viewport: viewport || DESKTOP,
    colorScheme: theme.colorScheme,
    reducedMotion: 'reduce',
    locale: 'de-DE',
    timezoneId: 'Europe/Berlin',
    storageState: storageState || undefined,
  });
  if (theme.cookie) {
    await context.addCookies([{ name: 'wb_theme', value: theme.cookie, url: BASE }]);
  }
  return context;
}

async function login(browser, username) {
  const context = await browser.newContext({ viewport: DESKTOP });
  const page = await context.newPage();
  await page.goto(`${BASE}/anmelden/`);
  await page.fill('#id_username', username);
  await page.fill('#id_password', PASSWORD);
  await Promise.all([page.waitForLoadState('load'), page.click('form.form-card button[type=submit]')]);
  await page.waitForTimeout(300);
  if (page.url().includes('/anmelden/')) {
    throw new Error(`login failed for ${username}: still on ${page.url()}`);
  }
  const state = await context.storageState();
  await context.close();
  return state;
}

async function unlockTerminal(page) {
  const token = process.env.TERMINAL_TOKEN;
  await page.goto(`${BASE}/terminal/start/${token}/`);
  await settle(page);
  return page;
}

async function submitTerminalCode(page) {
  const code = process.env.TERMINAL_CODE || '1234';
  await Promise.all([
    page.waitForLoadState('load'),
    page.evaluate((value) => {
      const input = document.getElementById('terminal-code');
      input.value = value;
      input.form.submit();
    }, code),
  ]);
  await page.waitForURL(/\/terminal\/alltag\//, { timeout: 10000 });
}

function summarise(result) {
  return result.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    helpUrl: v.helpUrl,
    nodes: v.nodes.length,
    examples: v.nodes.slice(0, 3).map((n) => ({
      target: n.target.join(' '),
      html: n.html.slice(0, 300),
      summary: (n.failureSummary || '').slice(0, 400),
    })),
  }));
}

// ---------------------------------------------------------------- display grid
// Measures the wall display in the page. Nothing may be cut off silently:
// - no visible element outside the viewport or the grid,
// - no module, column or region whose content is taller than its box while
//   overflow hides it (kiosk) or that needs scrolling (kiosk),
// - no visible element that hides content sideways (overflow not visible and
//   scrollWidth > clientWidth) unless it ends with a visible ellipsis
//   (text-overflow: ellipsis on a block box, e.g. a single long ticker title),
// - no emoji in the visible text.
function measureDisplay() {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const root = document.documentElement;
  const grid = document.querySelector('[data-display-grid]');
  const g = grid ? grid.getBoundingClientRect() : null;
  const describe = (el) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : ''}`;
  const overflowing = [];
  const clipped = [];
  const sideways = [];
  if (grid) {
    for (const el of [grid, ...grid.querySelectorAll('*')]) {
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || el.closest('[hidden]')) continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      const rect = [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)];
      if (r.right > vw + 1 || r.bottom > vh + 1 || r.left < -1 || r.top < -1) {
        overflowing.push({ el: describe(el), rect });
      } else if (r.right > g.right + 1 || r.bottom > g.bottom + 1) {
        clipped.push({ el: describe(el), rect });
      }
      if (style.overflowX !== 'visible' && el.scrollWidth > el.clientWidth + 1) {
        const ellipsis = style.textOverflow === 'ellipsis' && !/flex|grid/.test(style.display);
        if (!ellipsis) {
          sideways.push({ el: describe(el), scroll: el.scrollWidth, client: el.clientWidth, text: (el.innerText || '').slice(0, 80) });
        }
      }
    }
  }
  // Content taller than its module, column or region.
  const truncated = [];
  const scrollable = [];
  for (const el of document.querySelectorAll('[data-module-container], .display-column, .display-region')) {
    if (el.closest('[hidden]')) continue;
    if (el.scrollHeight > el.clientHeight + 2) {
      const overflowY = getComputedStyle(el).overflowY;
      const entry = { el: el.getAttribute('data-module-container') || el.className, scroll: el.scrollHeight, client: el.clientHeight };
      if (overflowY === 'hidden' || overflowY === 'clip') truncated.push(entry);
      else if (overflowY !== 'visible') scrollable.push(entry);
    }
  }
  const emoji = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B50}\u{2B55}\u{FE0F}]/u;
  return {
    viewport: [vw, vh],
    scroll: [root.scrollWidth, root.scrollHeight],
    bodyScroll: [document.body.scrollWidth, document.body.scrollHeight],
    grid: g ? [Math.round(g.left), Math.round(g.top), Math.round(g.width), Math.round(g.height)] : null,
    ratio: g ? +(g.width / g.height).toFixed(3) : null,
    overflowing: overflowing.slice(0, 20),
    overflowingCount: overflowing.length,
    clipped: clipped.slice(0, 20),
    clippedCount: clipped.length,
    sideways: sideways.slice(0, 20),
    sidewaysCount: sideways.length,
    truncated,
    scrollable,
    ticker: (() => {
      const text = document.querySelector('[data-display-ticker-text]');
      const more = document.querySelector('[data-display-ticker-more]');
      if (!text || text.closest('[hidden]')) return null;
      return { text: text.textContent, more: more && !more.hidden ? more.textContent : '', scroll: text.scrollWidth, client: text.clientWidth };
    })(),
    emoji: emoji.test(document.body.innerText),
  };
}

async function waitForDisplay(page) {
  // display.js fills the modules from /display/data/; wait for the clock.
  await page.waitForFunction(() => {
    const clock = document.querySelector('[data-display-clock], .display-clock');
    return clock && /\d/.test(clock.textContent);
  }, null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(1500);
}

async function checkDisplay(browser, report, screenshotsDir, states) {
  const token = process.env.DISPLAY_TOKEN;
  if (!token) {
    report.display.push({ error: 'DISPLAY_TOKEN not set' });
    return false;
  }
  let ok = true;
  // Kiosk (display link): fixed 16:9 frame, nothing scrolls, nothing is cut off.
  for (const size of [{ width: 1920, height: 1080 }, { width: 1280, height: 720 }]) {
    for (const themeName of ['light', 'dark']) {
      const context = await newContext(browser, ALL_THEMES[themeName], size);
      const page = await context.newPage();
      await page.goto(`${BASE}/display/start/${token}/`, { waitUntil: 'load' });
      await waitForDisplay(page);
      const geometry = await page.evaluate(measureDisplay);
      const failures = [];
      if (geometry.scroll[0] > geometry.viewport[0] || geometry.scroll[1] > geometry.viewport[1]) failures.push('document scrolls');
      if (!geometry.grid) failures.push('no [data-display-grid]');
      else {
        if (Math.abs(geometry.ratio - 16 / 9) > 0.02) failures.push(`grid ratio ${geometry.ratio}`);
        if (geometry.grid[2] > geometry.viewport[0] + 1 || geometry.grid[3] > geometry.viewport[1] + 1) failures.push('grid larger than viewport');
      }
      if (geometry.overflowingCount) failures.push(`${geometry.overflowingCount} elements outside the viewport`);
      if (geometry.clippedCount) failures.push(`${geometry.clippedCount} elements clipped by the grid`);
      if (geometry.sidewaysCount) failures.push(`${geometry.sidewaysCount} element(s) cut off sideways without ellipsis`);
      if (geometry.truncated.length) failures.push(`${geometry.truncated.length} region(s) cut off inside the grid`);
      if (geometry.scrollable.length) failures.push(`${geometry.scrollable.length} region(s) need scrolling`);
      if (geometry.emoji) failures.push('emoji in display text');
      const shot = path.join(screenshotsDir, `display-${size.width}x${size.height}-${themeName}.png`);
      await page.screenshot({ path: shot, fullPage: false });
      const axe = await runAxe(page);
      report.axeVersion = report.axeVersion || axe.testEngine.version;
      const violations = summarise(axe);
      report.display.push({ size: `${size.width}x${size.height}`, theme: themeName, geometry, failures, screenshot: shot });
      report.pages.push({ role: 'display', name: `display-${size.width}x${size.height}`, url: page.url(), theme: themeName, status: 200, violations, incomplete: axe.incomplete.length });
      if (failures.length) ok = false;
      await context.close();
    }
  }
  // Session view from a PC (fluid, no 16:9 frame) in a low window: lists are
  // shortened to "+N weitere"; if even that does not fit, the column scrolls.
  // Nothing may be cut off silently and the page itself must not scroll sideways.
  const sessionState = states.member || states.admin;
  if (sessionState) {
    const size = { width: 1366, height: 600 };
    const context = await newContext(browser, ALL_THEMES.light, size, sessionState);
    const page = await context.newPage();
    const response = await page.goto(`${BASE}/display/`, { waitUntil: 'load' });
    await waitForDisplay(page);
    const geometry = await page.evaluate(measureDisplay);
    const failures = [];
    if (!response || response.status() >= 400) failures.push(`HTTP ${response ? response.status() : 0}`);
    if (geometry.scroll[0] > geometry.viewport[0] + 1) failures.push('document scrolls sideways');
    if (geometry.sidewaysCount) failures.push(`${geometry.sidewaysCount} element(s) cut off sideways without ellipsis`);
    if (geometry.truncated.length) failures.push(`${geometry.truncated.length} region(s) cut off silently`);
    if (geometry.emoji) failures.push('emoji in display text');
    const shot = path.join(screenshotsDir, `display-session-${size.width}x${size.height}.png`);
    await page.screenshot({ path: shot, fullPage: false });
    const axe = await runAxe(page);
    report.display.push({ size: `session ${size.width}x${size.height}`, theme: 'light', geometry, failures, screenshot: shot });
    report.pages.push({ role: 'display', name: `display-session-${size.width}x${size.height}`, url: page.url(), theme: 'light', status: response ? response.status() : 0, violations: summarise(axe), incomplete: axe.incomplete.length });
    if (failures.length) ok = false;
    await context.close();
  } else {
    report.errors.push('display session view: no logged-in member');
  }
  return ok;
}

// ---------------------------------------------------------------- main
async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const shots = path.join(OUT, 'screenshots');
  fs.mkdirSync(shots, { recursive: true });
  const browser = await chromium.launch();
  const report = { base: BASE, tags: TAGS, themes: THEMES, axeVersion: null, pages: [], display: [], layout: [], errors: [] };
  const states = {};
  for (const [role, user] of [['admin', 'demo-admin'], ['member', 'demo-mitglied'], ['cashier', 'demo-kasse'], ['auditor', 'demo-audit']]) {
    try {
      states[role] = await login(browser, user);
    } catch (err) {
      report.errors.push(`${role}: ${err.message}`);
    }
  }

  const roles = (process.env.A11Y_ROLES || 'anon,admin,member,cashier,auditor,terminal').split(',');
  for (const role of roles) {
    if (role !== 'anon' && role !== 'terminal' && !states[role]) continue;
    for (const themeName of THEMES) {
      const theme = ALL_THEMES[themeName];
      let terminalContext = null;
      let terminalPage = null;
      if (role === 'terminal') {
        if (!process.env.TERMINAL_TOKEN) { report.errors.push('TERMINAL_TOKEN not set'); break; }
        terminalContext = await newContext(browser, theme, DESKTOP);
        terminalPage = await terminalContext.newPage();
        await unlockTerminal(terminalPage);
        const lock = await runAxe(terminalPage);
        report.axeVersion = report.axeVersion || lock.testEngine.version;
        report.pages.push({ role, name: 'terminal-lock-screen', url: terminalPage.url(), theme: themeName, status: 200, violations: summarise(lock), incomplete: lock.incomplete.length });
        await submitTerminalCode(terminalPage);
      }
      for (const [name, url, viewport] of pagesFor(role)) {
        let context = terminalContext;
        let page = terminalPage;
        if (!page) {
          context = await newContext(browser, theme, viewport || DESKTOP, states[role]);
          page = await context.newPage();
        } else if (viewport) {
          await page.setViewportSize(viewport);
        }
        let status = 0;
        try {
          const response = await page.goto(BASE + url, { waitUntil: 'load', timeout: 20000 });
          status = response ? response.status() : 0;
          // An error page would pass axe without testing the real page.
          if (status >= 400) throw new Error(`HTTP ${status}`);
          await settle(page);
          const result = await runAxe(page);
          report.axeVersion = report.axeVersion || result.testEngine.version;
          report.pages.push({ role, name, url: page.url().replace(BASE, ''), requested: url, theme: themeName, status, violations: summarise(result), incomplete: result.incomplete.length });
          // Phone width: the page must not scroll sideways (e.g. visually
          // hidden file inputs that keep their form width).
          if (viewport && viewport.width === PHONE.width) {
            const wide = await page.evaluate(() => {
              const root = document.documentElement;
              const culprits = [];
              for (const el of document.body.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                if (r.right > root.clientWidth + 1 && getComputedStyle(el).position !== 'fixed') {
                  culprits.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}`);
                }
              }
              return { scrollWidth: root.scrollWidth, clientWidth: root.clientWidth, culprits: culprits.slice(0, 10) };
            });
            report.layout.push({ role, name, theme: themeName, ...wide });
            if (wide.scrollWidth > wide.clientWidth + 1) {
              report.errors.push(`${role} ${name} ${themeName}: scrolls sideways at ${PHONE.width}px (${wide.scrollWidth} > ${wide.clientWidth}: ${wide.culprits.join(', ')})`);
            }
          }
          if (themeName === THEMES[0]) {
            await page.screenshot({ path: path.join(shots, `${role}-${name}-${themeName}.png`), fullPage: false });
          }
        } catch (err) {
          report.errors.push(`${role} ${name} ${themeName}: ${err.message.split('\n')[0]}`);
        }
        if (!terminalPage) await context.close();
        else if (viewport) await page.setViewportSize(DESKTOP);
      }
      if (terminalContext) await terminalContext.close();
    }
  }

  const displayOk = await checkDisplay(browser, report, shots, states);
  await browser.close();

  // ------------------------------------------------------------ summary
  const byRule = {};
  let failing = 0;
  for (const entry of report.pages) {
    for (const v of entry.violations) {
      const key = `${v.impact}|${v.id}`;
      byRule[key] = byRule[key] || { impact: v.impact, id: v.id, pages: 0, nodes: 0 };
      byRule[key].pages += 1;
      byRule[key].nodes += v.nodes;
      if (FAIL_ON.includes(v.impact)) failing += 1;
    }
  }
  report.summary = Object.values(byRule).sort((a, b) => a.impact.localeCompare(b.impact) || b.nodes - a.nodes);
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2));

  console.log(`axe ${report.axeVersion}; ${report.pages.length} page runs; themes ${THEMES.join(', ')}`);
  for (const row of report.summary) {
    console.log(`${row.impact.padEnd(9)} ${row.id.padEnd(32)} page-runs=${row.pages} nodes=${row.nodes}`);
  }
  for (const d of report.display) {
    console.log(`display ${d.size} ${d.theme}: ${d.failures && d.failures.length ? 'FAIL ' + d.failures.join('; ') : 'ok'}`);
  }
  for (const l of report.layout) {
    console.log(`phone ${l.role} ${l.name} ${l.theme}: scrollWidth ${l.scrollWidth} / clientWidth ${l.clientWidth}`);
  }
  for (const e of report.errors) console.log(`error: ${e}`);
  if (failing || !displayOk || report.errors.length) {
    console.log(`::error::${failing} violation(s) with impact ${FAIL_ON.join('/')}, display ok=${displayOk}, errors=${report.errors.length}`);
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
