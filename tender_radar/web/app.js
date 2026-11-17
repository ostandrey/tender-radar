/* Tender Radar front end. Vanilla JS, no build step.
 * Tender text is untrusted: everything is written with textContent, never innerHTML.
 */
(() => {
  "use strict";

  const PAGE = 40; // cards rendered per "Show more"
  const DAY = 86400000;
  const $ = (id) => document.getElementById(id);

  const state = {
    tenders: [], meta: null, now: Date.now(),
    filters: { search: "", categories: new Set(), deadline: "", budget: "", region: "", sort: "deadline" },
    shown: PAGE,
  };

  // ---------- formatting ----------
  const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
  const full = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });

  const uah = (n) => (n == null ? "n/a" : "₴" + compact.format(n));
  const deadlineMs = (t) => (t.deadline ? Date.parse(t.deadline) : NaN);

  function countdown(t) {
    const ms = deadlineMs(t) - state.now;
    if (Number.isNaN(ms)) return { main: "n/a", sub: "no deadline", urgent: false };
    const d = Math.floor(ms / DAY);
    const h = Math.floor((ms % DAY) / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    const date = new Date(deadlineMs(t)).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    const main = d > 0 ? `${d}d ${h}h` : `${h}h ${m}m`;
    return { main, sub: `closes ${date}`, urgent: ms < 3 * DAY };
  }

  function isOpen(t) {
    const ms = deadlineMs(t);
    return Number.isNaN(ms) || ms > state.now;
  }

  // ---------- filtering ----------
  function parseBudget(value) {
    if (!value) return null;
    const [lo, hi] = value.split("-");
    return { lo: lo ? Number(lo) : 0, hi: hi ? Number(hi) : Infinity };
  }

  function applyFilters() {
    const f = state.filters;
    const q = f.search.trim().toLowerCase();
    const budget = parseBudget(f.budget);
    const limit = f.deadline ? state.now + Number(f.deadline) * DAY : Infinity;
    const out = state.tenders.filter((t) => {
      if (!isOpen(t)) return false;
      if (q && !(t.title + " " + t.buyer).toLowerCase().includes(q)) return false;
      if (f.categories.size && !t.categories.some((c) => f.categories.has(c))) return false;
      if (f.region && t.region !== f.region) return false;
      if (limit !== Infinity && !(deadlineMs(t) <= limit)) return false;
      if (budget && !(t.amount_uah != null && t.amount_uah >= budget.lo && t.amount_uah < budget.hi)) return false;
      return true;
    });
    const by = {
      deadline: (a, b) => (deadlineMs(a) || Infinity) - (deadlineMs(b) || Infinity),
      budget: (a, b) => (b.amount_uah || 0) - (a.amount_uah || 0),
      newest: (a, b) => (b.first_seen || "").localeCompare(a.first_seen || "") || (b.score - a.score),
    };
    return out.sort(by[f.sort]);
  }

  // ---------- rendering ----------
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function safeUrl(url) {
    try {
      const u = new URL(url);
      return u.protocol === "https:" && u.hostname.endsWith("prozorro.gov.ua") ? u.href : null;
    } catch { return null; }
  }

  function renderCard(t, index) {
    const li = el("li", "card");
    li.style.setProperty("--i", Math.min(index, 12));

    const cd = countdown(t);
    const when = el("div", "when" + (cd.urgent ? " urgent" : ""));
    when.append(el("strong", null, cd.main), el("span", null, cd.sub));

    const body = el("div", "body");
    const title = el("h2", "title");
    const href = safeUrl(t.url);
    if (href) {
      const a = el("a", null, t.title);
      a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      title.append(a);
    } else {
      title.textContent = t.title;
    }
    const meta = el("p", "meta", [t.buyer, t.region].filter(Boolean).join(" · "));
    const tags = el("div", "tags");
    if (t.first_seen && state.meta && t.first_seen === state.meta.generated_at.slice(0, 10)) tags.append(el("span", "new", "NEW"));
    t.categories.forEach((c) => tags.append(el("span", "tag", c)));
    if (t.cpv_code) tags.append(el("span", "cpv", t.cpv_code));
    body.append(title, meta, tags);

    const money = el("div", "money");
    const strong = el("strong", null, uah(t.amount_uah));
    if (t.amount_uah != null) strong.title = "₴" + full.format(t.amount_uah);
    money.append(strong);
    if (t.amount != null && t.currency !== "UAH") money.append(el("span", null, `${full.format(t.amount)} ${t.currency}`));
    if (href) {
      const open = el("a", "open", "Open on Prozorro ↗");
      open.href = href; open.target = "_blank"; open.rel = "noopener noreferrer";
      money.append(open);
    }

    li.append(when, body, money);
    return li;
  }

  function updateToggleLabel() {
    const f = state.filters;
    const n = [f.deadline, f.budget, f.region].filter(Boolean).length + f.categories.size;
    const btn = $("f-toggle");
    if (btn) btn.textContent = n ? `Filters · ${n}` : "Filters";
  }

  function render() {
    updateToggleLabel();
    const list = $("list");
    const rows = applyFilters();
    const open = state.tenders.filter(isOpen).length;
    list.replaceChildren(...rows.slice(0, state.shown).map(renderCard));
    $("empty").hidden = rows.length > 0;
    $("more-wrap").hidden = rows.length <= state.shown;
    $("count").textContent = rows.length
      ? `Showing ${Math.min(state.shown, rows.length)} of ${rows.length} matching (${open} open in total)`
      : "";
    state.filtered = rows;
  }

  function renderKpis() {
    const open = state.tenders.filter(isOpen);
    const soon = open.filter((t) => deadlineMs(t) <= state.now + 7 * DAY).length;
    const today = state.meta.generated_at.slice(0, 10);
    $("kpi-open").textContent = String(open.length);
    $("kpi-value").textContent = compact.format(open.reduce((s, t) => s + (t.amount_uah || 0), 0));
    $("kpi-soon").textContent = String(soon);
    $("kpi-new").textContent = String(open.filter((t) => t.first_seen === today).length);
    const when = new Date(state.meta.generated_at);
    $("updated").textContent = `Updated ${when.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}`
      + ` · ${state.tenders.length} tenders tracked`;
  }

  function renderChips() {
    const counts = new Map();
    state.tenders.filter(isOpen).forEach((t) => t.categories.forEach((c) => counts.set(c, (counts.get(c) || 0) + 1)));
    const chips = $("chips");
    chips.replaceChildren();
    [...counts.entries()].sort((a, b) => b[1] - a[1]).forEach(([name, n]) => {
      const b = el("button", "chip", name);
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      b.append(el("small", null, String(n)));
      b.addEventListener("click", () => {
        const on = state.filters.categories.has(name);
        on ? state.filters.categories.delete(name) : state.filters.categories.add(name);
        b.setAttribute("aria-pressed", String(!on));
        state.shown = PAGE;
        render();
      });
      chips.append(b);
    });
  }

  function renderRegions() {
    const select = $("f-region");
    const regions = [...new Set(state.tenders.filter(isOpen).map((t) => t.region).filter(Boolean))].sort((a, b) => a.localeCompare(b, "uk"));
    regions.forEach((r) => { const o = el("option", null, r); o.value = r; select.append(o); });
  }

  // ---------- CSV export ----------
  function csvCell(value) {
    let s = value == null ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; // neutralise spreadsheet formulas in untrusted text
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function exportCsv() {
    const head = ["id", "title", "buyer", "region", "cpv", "categories", "amount", "currency", "amount_uah", "deadline", "status", "first_seen", "url"];
    const lines = [head.join(",")].concat((state.filtered || []).map((t) => [
      t.id, t.title, t.buyer, t.region, t.cpv_code, t.categories.join("; "), t.amount, t.currency,
      t.amount_uah, t.deadline, t.status, t.first_seen, t.url,
    ].map(csvCell).join(",")));
    const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `tender-radar-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // ---------- wiring ----------
  function bind() {
    const on = (id, ev, fn) => $(id).addEventListener(ev, fn);
    const apply = (key) => (e) => { state.filters[key] = e.target.value; state.shown = PAGE; render(); };
    let timer;
    on("f-search", "input", (e) => {
      clearTimeout(timer);
      timer = setTimeout(() => { state.filters.search = e.target.value; state.shown = PAGE; render(); }, 120);
    });
    on("f-sort", "change", apply("sort"));
    on("f-deadline", "change", apply("deadline"));
    on("f-budget", "change", apply("budget"));
    on("f-region", "change", apply("region"));
    on("btn-more", "click", () => { state.shown += PAGE; render(); });
    on("btn-csv", "click", exportCsv);
    const reset = () => {
      state.filters = { search: "", categories: new Set(), deadline: "", budget: "", region: "", sort: "deadline" };
      ["f-search", "f-deadline", "f-budget", "f-region"].forEach((id) => { $(id).value = ""; });
      $("f-sort").value = "deadline";
      document.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
      state.shown = PAGE;
      render();
    };
    on("btn-reset", "click", reset);
    on("f-toggle", "click", () => {
      const box = document.querySelector(".filters");
      const open = box.classList.toggle("is-open");
      $("f-toggle").setAttribute("aria-expanded", String(open));
    });
    on("btn-empty-reset", "click", reset);
    on("btn-retry", "click", load);
  }

  function setSourceLink() {
    // https://<owner>.github.io/<repo>/ -> https://github.com/<owner>/<repo>
    const m = location.hostname.match(/^([^.]+)\.github\.io$/);
    const repo = location.pathname.split("/").filter(Boolean)[0];
    if (m && repo) $("source-link").href = `https://github.com/${m[1]}/${repo}`;
  }

  async function getJson(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return res.json();
  }

  async function load() {
    $("loading").hidden = false;
    $("error").hidden = true;
    try {
      const [tenders, meta] = await Promise.all([getJson("data/tenders.json"), getJson("data/meta.json")]);
      state.tenders = tenders;
      state.meta = meta;
      state.now = Date.now();
      $("loading").hidden = true;
      renderKpis();
      renderChips();
      renderRegions();
      render();
    } catch (err) {
      $("loading").hidden = true;
      $("error-text").textContent = "The dataset could not be loaded (" + err.message + "). If you opened this file directly, serve the folder over HTTP.";
      $("error").hidden = false;
      $("updated").textContent = "Data unavailable";
    }
  }

  bind();
  setSourceLink();
  load();
})();
