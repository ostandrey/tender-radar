/* Tender Radar UI — vanilla JS, no build step.
   Data: data/tenders.json (list) + data/meta.json. Tender text is untrusted: everything is rendered with textContent.
   State lives in the URL (filters, sort, page, view, open tender) so refresh, back and shared links keep the place.
   The shortlist and the last-visit date live in this browser only (localStorage, guarded). */
(() => {
  "use strict";

  const DAY = 86400000;
  const BUDGETS = [
    { id: "lt100k", label: "Under ₴100 K", test: (v) => v != null && v < 1e5 },
    { id: "100k-1m", label: "₴100 K – 1 M", test: (v) => v != null && v >= 1e5 && v < 1e6 },
    { id: "1m-10m", label: "₴1 M – 10 M", test: (v) => v != null && v >= 1e6 && v < 1e7 },
    { id: "gt10m", label: "Over ₴10 M", test: (v) => v != null && v >= 1e7 },
    { id: "none", label: "Not stated", test: (v) => v == null },
  ];
  const DEADLINES = [
    { id: "", label: "Any time" }, { id: "3", label: "Within 3 days" }, { id: "7", label: "Within 7 days" },
    { id: "14", label: "Within 14 days" }, { id: "30", label: "Within 30 days" },
  ];
  const SORTS = { deadline: "Deadline, soonest", budget: "Budget, largest", newest: "Newest", relevance: "Relevance" };
  const REGIONS_SHOWN = 8;

  const $ = (id) => document.getElementById(id);
  const S = {
    tenders: [], meta: null, now: Date.now(), byId: new Map(),
    q: "", cat: new Set(), dl: "", budget: new Set(), method: new Set(), region: new Set(), fresh: false,
    sort: "deadline", per: 25, page: 1, view: "all", open: "",
    short: new Map(), lastVisit: "", newSince: "", regionsAll: false,
  };

  // ---------- small helpers ----------
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "text") n.textContent = v;
      else if (k === "on") for (const [ev, fn] of Object.entries(v)) n.addEventListener(ev, fn);
      else if (k === "class") n.className = v;
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return n;
  }
  const svg = (path) => {
    const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("aria-hidden", "true");
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path"); p.setAttribute("d", path); s.append(p); return s;
  };
  const STAR = "m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z";
  const X = "M6 6l12 12M18 6 6 18";
  const store = {
    get(key, fallback) { try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch (_) { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* storage blocked: shortlist lives for this page only */ } },
  };
  const ms = (iso) => { const t = Date.parse(iso || ""); return Number.isNaN(t) ? null : t; };
  const isOpen = (t) => { const d = ms(t.deadline); return d == null || d >= S.now; };
  const daysLeft = (t) => { const d = ms(t.deadline); return d == null ? null : (d - S.now) / DAY; };
  const urgency = (t) => { const d = daysLeft(t); return d == null ? "calm" : d <= 2 ? "hot" : d <= 7 ? "warm" : "calm"; };
  const fmtDate = (iso, withTime) => {
    const t = ms(iso); if (t == null) return "—";
    const o = { day: "numeric", month: "short", timeZone: "Europe/Kyiv" };
    if (withTime) Object.assign(o, { hour: "2-digit", minute: "2-digit", hour12: false });
    if (new Date(t).getFullYear() !== new Date(S.now).getFullYear()) o.year = "numeric";
    return new Intl.DateTimeFormat("en-GB", o).format(t);
  };
  const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });
  const full = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
  const money = (v) => (v == null ? "—" : "₴" + compact.format(v));
  const leftText = (t) => {
    const d = daysLeft(t); if (d == null) return "No deadline";
    if (d < 0) return "Closed";
    if (d < 1) { const h = Math.max(1, Math.round(d * 24)); return `${h} h left`; }
    const n = Math.floor(d); return `${n} day${n === 1 ? "" : "s"} left`;
  };
  const isNew = (t) => !!S.newSince && (t.first_seen || "") > S.newSince;

  // ---------- URL state ----------
  function readUrl() {
    const p = new URLSearchParams(location.search);
    const set = (k) => new Set((p.get(k) || "").split(",").filter(Boolean));
    S.q = p.get("q") || ""; S.cat = set("cat"); S.budget = set("budget"); S.method = set("proc"); S.region = set("region");
    S.dl = DEADLINES.some((d) => d.id === p.get("dl")) ? p.get("dl") : "";
    S.fresh = p.get("new") === "1";
    S.sort = SORTS[p.get("sort")] ? p.get("sort") : "deadline";
    S.per = [25, 50, 100].includes(Number(p.get("per"))) ? Number(p.get("per")) : 25;
    S.page = Math.max(1, Number(p.get("page")) || 1);
    S.view = p.get("view") === "shortlist" ? "short" : "all";
    S.open = p.get("id") || "";
  }
  function writeUrl(push) {
    const p = new URLSearchParams();
    const put = (k, v) => { if (v) p.set(k, v); };
    put("q", S.q.trim()); put("cat", [...S.cat].join(",")); put("dl", S.dl); put("budget", [...S.budget].join(","));
    put("proc", [...S.method].join(",")); put("region", [...S.region].join(",")); put("new", S.fresh ? "1" : "");
    put("sort", S.sort !== "deadline" ? S.sort : ""); put("per", S.per !== 25 ? String(S.per) : "");
    put("page", S.page > 1 ? String(S.page) : ""); put("view", S.view === "short" ? "shortlist" : ""); put("id", S.open);
    const url = location.pathname + (p.toString() ? "?" + p : "");
    if (url !== location.pathname + location.search) history[push ? "pushState" : "replaceState"](null, "", url);
  }

  // ---------- filtering (each facet counts against all the other filters) ----------
  function baseItems() {
    if (S.view === "short") return [...S.short.keys()].map((id) => S.byId.get(id) || { ...S.short.get(id), gone: true });
    return S.tenders.filter(isOpen);
  }
  function passes(t, skip) {
    if (skip !== "q" && S.q.trim()) {
      const q = S.q.trim().toLowerCase();
      if (!`${t.title} ${t.buyer} ${t.cpv_code} ${t.cpv_label}`.toLowerCase().includes(q)) return false;
    }
    if (skip !== "cat" && S.cat.size && !(t.categories || []).some((c) => S.cat.has(c))) return false;
    if (skip !== "dl" && S.dl) { const d = daysLeft(t); if (d == null || d > Number(S.dl)) return false; }
    if (skip !== "budget" && S.budget.size && !BUDGETS.some((b) => S.budget.has(b.id) && b.test(t.amount_uah))) return false;
    if (skip !== "method" && S.method.size && !S.method.has(t.method || "Not stated")) return false;
    if (skip !== "region" && S.region.size && !S.region.has(t.region || "Not stated")) return false;
    if (skip !== "fresh" && S.fresh && !isNew(t)) return false;
    return true;
  }
  function sorted(items) {
    const by = {
      deadline: (a, b) => (ms(a.deadline) ?? Infinity) - (ms(b.deadline) ?? Infinity),
      budget: (a, b) => (b.amount_uah ?? -1) - (a.amount_uah ?? -1),
      newest: (a, b) => (ms(b.published) ?? 0) - (ms(a.published) ?? 0) || (b.first_seen || "").localeCompare(a.first_seen || ""),
      relevance: (a, b) => (b.score || 0) - (a.score || 0),
    }[S.sort];
    return items.slice().sort((a, b) => by(a, b) || String(a.id).localeCompare(String(b.id)));
  }
  const activeCount = () => S.cat.size + (S.dl ? 1 : 0) + S.budget.size + S.method.size + S.region.size + (S.fresh ? 1 : 0) + (S.q.trim() ? 1 : 0);

  // ---------- render ----------
  function render(opts = {}) {
    const base = baseItems();
    const items = sorted(base.filter((t) => passes(t)));
    const pages = Math.max(1, Math.ceil(items.length / S.per));
    if (S.page > pages) S.page = pages;
    const start = (S.page - 1) * S.per;
    const pageItems = items.slice(start, start + S.per);

    renderStats(); renderViews(); renderFacets(base); renderTags(); renderShortbar(base);
    $("range").textContent = "";
    if (items.length) $("range").append("Showing ", el("strong", { text: `${start + 1}–${start + pageItems.length}` }), ` of ${items.length}`,
      S.view === "short" ? " shortlisted" : " open tenders");
    $("filters-btn-label").textContent = activeCount() ? `Filters · ${activeCount()}` : "Filters";
    $("sort").value = S.sort; $("per").value = String(S.per);
    if ($("q") !== document.activeElement) $("q").value = S.q;

    $("list").replaceChildren(...pageItems.map(row));
    renderEmpty(base, items);
    renderPager(pages);
    $("export-csv").classList.toggle("hidden", !items.length || S.view === "short");
    if (opts.scroll) $("results").scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    writeUrl(opts.push);
  }

  function renderStats() {
    const open = S.tenders.filter(isOpen);
    const total = open.reduce((s, t) => s + (t.amount_uah || 0), 0);
    const soon = open.filter((t) => { const d = daysLeft(t); return d != null && d <= 7; }).length;
    const fresh = open.filter(isNew).length;
    const stat = (k, v, s, cls, pressed, onClick) => el("button", { type: "button", class: "stat " + (cls || ""), "aria-pressed": String(!!pressed), on: { click: onClick } },
      el("span", { class: "k", text: k }), el("span", { class: "v", text: v }), el("span", { class: "s", text: s }));
    $("stats").replaceChildren(
      stat("Open tenders", full.format(open.length), "IT services, software, systems", "", S.view === "all" && !activeCount(), () => { clearAll(); setView("all"); }),
      stat("Total expected value", money(total), "in UAH at the NBU rate", "", S.sort === "budget", () => { S.sort = "budget"; S.page = 1; setView("all"); }),
      stat("Closing within 7 days", full.format(soon), "bids still open", "hot", S.dl === "7", () => { S.dl = S.dl === "7" ? "" : "7"; S.page = 1; setView("all"); }),
      S.firstDay
        ? stat("Tracking since", fmtDate(S.tenders.reduce((m, t) => (t.first_seen && (!m || t.first_seen < m) ? t.first_seen : m), "")),
          "new tenders get a badge from the next update", "", false, () => {})
        : stat(S.lastVisit ? "New since your last visit" : "New in the latest update", full.format(fresh),
          S.lastVisit ? `since ${fmtDate(S.lastVisit)}` : "first seen in the last run", "new", S.fresh, () => { S.fresh = !S.fresh; S.page = 1; setView("all"); }),
    );
  }

  function renderViews() {
    $("n-all").textContent = full.format(S.tenders.filter(isOpen).length);
    $("n-short").textContent = String(S.short.size);
    $("tab-all").setAttribute("aria-selected", String(S.view === "all"));
    $("tab-short").setAttribute("aria-selected", String(S.view === "short"));
  }

  function facetOptions(box, options, selected, onToggle, type) {
    const isOn = (id) => (type === "radio" ? selected === id : selected.has(id));
    box.replaceChildren(...options.map((o) => {
      const id = `${box.id}-${o.id || "any"}`.replace(/[^\w-]/g, "_");
      const input = el("input", { type: type || "checkbox", id, name: box.id, checked: isOn(o.id), on: { change: () => onToggle(o.id) } });
      return el("label", { class: "opt" + (o.count === 0 && !isOn(o.id) ? " zero" : ""), for: id },
        input, el("span", { class: "t", text: o.label }), o.count != null ? el("span", { class: "c", text: String(o.count) }) : null);
    }));
  }
  const toggleIn = (set) => (id) => { set.has(id) ? set.delete(id) : set.add(id); S.page = 1; render(); };

  function renderFacets(base) {
    const count = (skip, test) => base.filter((t) => passes(t, skip) && test(t)).length;
    const cats = [...new Set(base.flatMap((t) => t.categories || []))];
    const catOpts = cats.map((c) => ({ id: c, label: c, count: count("cat", (t) => (t.categories || []).includes(c)) })).sort((a, b) => b.count - a.count);
    facetOptions($("f-cat"), catOpts, S.cat, toggleIn(S.cat));

    const dlOpts = DEADLINES.map((d) => ({ id: d.id, label: d.label,
      count: d.id ? count("dl", (t) => { const x = daysLeft(t); return x != null && x <= Number(d.id); }) : null }));
    facetOptions($("f-dl"), dlOpts, S.dl, (id) => { S.dl = id; S.page = 1; render(); }, "radio");

    const bOpts = BUDGETS.map((b) => ({ id: b.id, label: b.label, count: count("budget", (t) => b.test(t.amount_uah)) }));
    facetOptions($("f-budget"), bOpts, S.budget, toggleIn(S.budget));

    const methods = [...new Set(base.map((t) => t.method || "Not stated"))];
    $("facet-method").classList.toggle("hidden", methods.length < 2);
    const mOpts = methods.map((m) => ({ id: m, label: m, count: count("method", (t) => (t.method || "Not stated") === m) })).sort((a, b) => b.count - a.count);
    facetOptions($("f-method"), mOpts, S.method, toggleIn(S.method));

    const regions = [...new Set(base.map((t) => t.region || "Not stated"))];
    let rOpts = regions.map((r) => ({ id: r, label: r, count: count("region", (t) => (t.region || "Not stated") === r) }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "uk"));
    const hidden = rOpts.length - REGIONS_SHOWN;
    if (!S.regionsAll && hidden > 0) rOpts = rOpts.filter((o, i) => i < REGIONS_SHOWN || S.region.has(o.id));
    facetOptions($("f-region"), rOpts, S.region, toggleIn(S.region));
    if (hidden > 0) $("f-region").append(el("button", { type: "button", class: "more-link", text: S.regionsAll ? "Show fewer" : `Show all ${regions.length} regions`,
      on: { click: () => { S.regionsAll = !S.regionsAll; render(); } } }));
  }

  function renderTags() {
    const tags = [];
    const tag = (label, onRemove) => tags.push(el("button", { type: "button", class: "tag", "aria-label": `Remove filter: ${label}`, on: { click: onRemove } }, label, svg(X)));
    const go = () => { S.page = 1; render(); };
    if (S.q.trim()) tag(`“${S.q.trim()}”`, () => { S.q = ""; go(); });
    S.cat.forEach((c) => tag(c, () => { S.cat.delete(c); go(); }));
    if (S.dl) tag(DEADLINES.find((d) => d.id === S.dl).label, () => { S.dl = ""; go(); });
    S.budget.forEach((b) => tag((BUDGETS.find((x) => x.id === b) || {}).label || b, () => { S.budget.delete(b); go(); }));
    S.method.forEach((m) => tag(m, () => { S.method.delete(m); go(); }));
    S.region.forEach((r) => tag(r, () => { S.region.delete(r); go(); }));
    if (S.fresh) tag("New", () => { S.fresh = false; go(); });
    if (tags.length > 1) tags.push(el("button", { type: "button", class: "tag clear", text: "Clear all", on: { click: () => { clearAll(); render(); } } }));
    $("tags").replaceChildren(...tags);
  }

  function renderShortbar(base) {
    const on = S.view === "short" && S.short.size > 0;
    $("shortbar").classList.toggle("hidden", !on);
    if (!on) return;
    const open = base.filter((t) => !t.gone && isOpen(t));
    const total = base.reduce((s, t) => s + (t.amount_uah || 0), 0);
    const next = open.map((t) => ms(t.deadline)).filter((x) => x != null).sort((a, b) => a - b)[0];
    const closed = base.length - open.length;
    $("short-summary").replaceChildren(el("strong", { text: `${S.short.size} tender${S.short.size === 1 ? "" : "s"}` }),
      ` · total ${money(total)}`, next ? ` · next deadline ${fmtDate(new Date(next).toISOString(), true)}` : "", closed ? ` · ${closed} closed` : "");
  }

  function row(t) {
    const starred = S.short.has(t.id);
    const open = !t.gone && isOpen(t);
    const u = open ? urgency(t) : "calm";
    const meta = [t.buyer, t.region, t.method].filter(Boolean);
    const pub = ms(t.published), dl = ms(t.deadline);
    const elapsed = open && pub != null && dl != null && dl > pub ? Math.min(1, Math.max(0, (S.now - pub) / (dl - pub))) : null;
    return el("li", { class: "row" + (t.gone ? " gone" : "") },
      el("button", { type: "button", class: "star", "aria-pressed": String(starred), "aria-label": starred ? "Remove from shortlist" : "Add to shortlist",
        title: starred ? "Remove from shortlist" : "Add to shortlist", on: { click: () => toggleStar(t) } }, svg(STAR)),
      el("div", { class: "main" },
        el("button", { type: "button", class: "title", text: t.title, title: t.title, on: { click: () => openTender(t.id) } }),
        el("p", { class: "meta" }, ...meta.flatMap((m, i) => (i === 0 ? [el("b", { text: m })] : [" · ", m]))),
        el("div", { class: "chips" },
          t.gone ? el("span", { class: "chip closed", text: "No longer listed" }) : !open ? el("span", { class: "chip closed", text: "Closed" }) : null,
          open && isNew(t) ? el("span", { class: "chip new", text: "New" }) : null,
          ...(t.categories || []).map((c) => el("span", { class: "chip", text: c })),
          t.cpv_code ? el("span", { class: "chip code", text: t.cpv_code, title: t.cpv_label || "" }) : null)),
      el("div", { class: "money" },
        el("div", { class: "v", text: money(t.amount_uah), title: t.amount_uah != null ? `₴${full.format(t.amount_uah)}` : "" }),
        t.currency && t.currency !== "UAH" && t.amount != null ? el("div", { class: "o", text: `${full.format(t.amount)} ${t.currency}` })
          : el("div", { class: "o", text: "expected value" })),
      el("div", { class: "due " + u },
        el("div", { class: "left", text: t.gone ? "—" : leftText(t) }),
        el("div", { class: "when", text: dl ? `until ${fmtDate(t.deadline, true)}` : "" }),
        elapsed != null ? el("div", { class: "ruler", role: "img", "aria-label": `${Math.round(elapsed * 100)}% of the bidding period has passed` },
          el("i", { style: `width:${(elapsed * 100).toFixed(1)}%` })) : null,
        elapsed != null ? el("div", { class: "ruler-labels" }, el("span", { text: fmtDate(t.published) }), el("span", { text: fmtDate(t.deadline) })) : null));
  }

  function renderEmpty(base, items) {
    const box = $("empty");
    let content = null;
    if (!S.tenders.length) content = [el("h2", { text: "No tenders yet" }), el("p", { text: "The daily update has not produced data yet. Check back after the next run." })];
    else if (S.view === "short" && !S.short.size) content = [el("h2", { text: "Your shortlist is empty" }),
      el("p", { text: "Star a tender to keep it here — you’ll see the total value, the next deadline and can export the list." }),
      el("button", { type: "button", class: "btn primary", text: "Browse tenders", on: { click: () => setView("all") } })];
    else if (!items.length) content = [el("h2", { text: "Nothing matches these filters" }),
      el("p", { text: `${base.length} tenders in this view — try removing a filter.` }),
      el("button", { type: "button", class: "btn", text: "Clear all filters", on: { click: () => { clearAll(); render(); } } })];
    box.classList.toggle("hidden", !content);
    if (content) box.replaceChildren(...content);
  }

  function renderPager(pages) {
    const nav = $("pager");
    if (pages <= 1) { nav.replaceChildren(); return; }
    const go = (p) => { S.page = p; render({ push: true, scroll: true }); };
    const btn = (label, p, extra) => el("button", { type: "button", ...extra, on: { click: () => go(p) } }, label);
    const nums = [];
    let last = 0;
    [...new Set([1, pages, S.page - 1, S.page, S.page + 1])].filter((p) => p >= 1 && p <= pages).sort((a, b) => a - b).forEach((p) => {
      if (p - last > 1) nums.push(el("span", { class: "full", text: "…" }));
      nums.push(btn(String(p), p, { class: "full", "aria-current": p === S.page ? "page" : null, "aria-label": `Page ${p}` }));
      last = p;
    });
    nav.replaceChildren(
      btn("‹ Prev", S.page - 1, { disabled: S.page === 1, "aria-label": "Previous page" }),
      ...nums,
      el("span", { class: "compact", text: `Page ${S.page} of ${pages}` }),
      btn("Next ›", S.page + 1, { disabled: S.page === pages, "aria-label": "Next page" }));
  }

  // ---------- details drawer ----------
  /** Description parts that add something beyond the title (buyers often repeat the title as the only lot/item). */
  function describes(t) {
    const norm = (x) => (x || "").toLowerCase().replace(/\s+/g, " ").trim();
    const title = norm(t.title);
    return (t.description || "").split(" | ").filter((p) => p && !title.includes(norm(p)) && !norm(p).includes(title)).join("\n");
  }
  let lastFocus = null;
  function openTender(id, push = true) {
    const t = S.byId.get(id) || (S.short.has(id) ? { ...S.short.get(id), gone: true } : null);
    if (!t) { S.open = ""; writeUrl(false); return; }
    if ($("drawer").hidden) lastFocus = document.activeElement;
    S.open = id;
    const starred = S.short.has(t.id);
    const dt = (k, v) => el("div", {}, el("dt", { text: k }), el("dd", { text: v || "—" }));
    const step = (k, iso, cls) => el("li", { class: cls || null }, el("span", { class: "k", text: k }), fmtDate(iso, true));
    const e = ms(t.enquiry_end), d = ms(t.deadline);
    $("drawer-body").replaceChildren(
      el("div", { class: "chips" }, ...(t.categories || []).map((c) => el("span", { class: "chip", text: c })), isNew(t) ? el("span", { class: "chip new", text: "New" }) : null),
      el("h2", { class: "d-title", id: "d-title", text: t.title }),
      el("p", { class: "d-buyer", text: [t.buyer, t.region].filter(Boolean).join(" · ") }),
      el("div", { class: "d-actions" },
        el("a", { class: "btn primary", href: t.url, target: "_blank", rel: "noopener" }, "Open on Prozorro ↗"),
        el("button", { type: "button", class: "btn", "aria-pressed": String(starred), on: { click: () => { toggleStar(t); openTender(t.id, false); } } },
          svg(STAR), starred ? "In shortlist" : "Add to shortlist"),
        el("button", { type: "button", class: "btn ghost", on: { click: () => copy(location.href, "Link copied") } }, "Copy link")),
      el("dl", { class: "d-grid" },
        dt("Expected value", t.amount_uah != null ? `₴${full.format(t.amount_uah)}` + (t.currency !== "UAH" && t.amount != null ? ` (${full.format(t.amount)} ${t.currency})` : "") : "Not stated"),
        dt("Time left", t.gone ? "No longer listed" : leftText(t)),
        dt("Procedure", t.method), dt("Bid security", t.guarantee ? `₴${full.format(t.guarantee)}` : "Not required"),
        dt("CPV", t.cpv_code ? `${t.cpv_code} ${t.cpv_label || ""}` : ""), dt("Prozorro ID", t.id)),
      el("section", { class: "d-sec" }, el("h3", { text: "Timeline" }),
        el("ol", { class: "timeline" },
          t.published ? step("Bids open", t.published, "done") : null,
          t.enquiry_end ? step("Questions to the buyer until", t.enquiry_end, e != null && e < S.now ? "done" : "next") : null,
          step("Bid deadline", t.deadline, d != null && d < S.now ? "done" : (e == null || e < S.now) ? "next" : ""))),
      describes(t) ? el("section", { class: "d-sec" }, el("h3", { text: "What the buyer needs" }), el("p", { text: describes(t) })) : null,
      (t.documents || []).length ? el("section", { class: "d-sec" }, el("h3", { text: "Tender documents" }),
        el("ul", { class: "docs" }, ...t.documents.map((doc) => el("li", {}, el("a", { href: doc.url, target: "_blank", rel: "noopener", text: doc.title }))))) : null,
    );
    $("drawer").hidden = false; $("scrim").classList.remove("hidden"); document.body.style.overflow = "hidden";
    $("drawer-close").focus();
    writeUrl(push);
  }
  function closeTender() {
    if ($("drawer").hidden) return;
    $("drawer").hidden = true; $("scrim").classList.add("hidden"); document.body.style.overflow = "";
    S.open = ""; writeUrl(false); if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
  }

  // ---------- shortlist ----------
  function snapshot(t) {
    const keys = ["id", "title", "buyer", "region", "categories", "amount", "currency", "amount_uah", "deadline", "published", "url", "cpv_code", "method"];
    return Object.fromEntries(keys.map((k) => [k, t[k]]));
  }
  const saveShort = () => store.set("tr.shortlist", Object.fromEntries(S.short));
  function toggleStar(t) {
    if (S.short.has(t.id)) { S.short.delete(t.id); toast("Removed from shortlist"); }
    else { S.short.set(t.id, { ...snapshot(t), added: new Date(S.now).toISOString() }); toast("Added to shortlist"); }
    saveShort(); render();
  }
  function clearShortlist() {
    const before = new Map(S.short);
    S.short.clear(); saveShort(); render();
    toast(`Shortlist cleared (${before.size})`, "Undo", () => { S.short = before; saveShort(); render(); });
  }

  // ---------- export ----------
  function csv(items) {
    const cell = (v) => {
      let s = v == null ? "" : String(v);
      if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; // keep spreadsheet formulas from running
      return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const head = ["Prozorro ID", "Title", "Buyer", "Region", "Categories", "Expected value, UAH", "Original amount", "Currency", "Deadline", "Procedure", "Link"];
    const rows = items.map((t) => [t.id, t.title, t.buyer, t.region, (t.categories || []).join("; "), t.amount_uah != null ? Math.round(t.amount_uah) : "",
      t.amount ?? "", t.currency, t.deadline, t.method, t.url]);
    const text = "﻿" + [head, ...rows].map((r) => r.map(cell).join(",")).join("\r\n");
    const a = el("a", { href: URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" })),
      download: `tender-radar-${S.view === "short" ? "shortlist" : "results"}-${new Date(S.now).toISOString().slice(0, 10)}.csv` });
    document.body.append(a); a.click(); a.remove();
  }
  function copy(text, done) {
    (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject(new Error("no clipboard")))
      .then(() => toast(done), () => toast("Couldn’t copy — select and copy manually"));
  }
  const shortlistText = () => sorted(baseItems())
    .map((t) => `${t.title}\n${money(t.amount_uah)} · ${leftText(t)} (${fmtDate(t.deadline, true)}) · ${t.buyer}\n${t.url}`).join("\n\n");

  // ---------- toast ----------
  let toastTimer;
  function toast(message, action, onAction) {
    const box = $("toast");
    const kids = [el("span", { text: message })];
    if (action) kids.push(el("button", { type: "button", text: action, on: { click: () => { onAction(); box.classList.add("hidden"); } } }));
    box.replaceChildren(...kids);
    box.classList.remove("hidden"); clearTimeout(toastTimer);
    toastTimer = setTimeout(() => box.classList.add("hidden"), action ? 8000 : 2600);
  }

  // ---------- views, filters sheet ----------
  function setView(v) { S.view = v; S.page = 1; render({ push: true }); }
  function clearAll() { S.q = ""; S.cat.clear(); S.dl = ""; S.budget.clear(); S.method.clear(); S.region.clear(); S.fresh = false; S.page = 1; }
  function sheet(open) {
    $("filters").classList.toggle("open", open); $("scrim").classList.toggle("hidden", !open);
    document.body.style.overflow = open ? "hidden" : "";
    (open ? $("sheet-close") : $("open-filters")).focus();
  }

  // ---------- data ----------
  async function getJson(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
    return res.json();
  }
  const prevDay = (iso) => new Date(Date.parse(iso) - DAY).toISOString().slice(0, 10);
  async function load() {
    $("loading").classList.remove("hidden"); $("empty").classList.add("hidden");
    try {
      const [tenders, meta] = await Promise.all([getJson("data/tenders.json"), getJson("data/meta.json").catch(() => null)]);
      S.tenders = Array.isArray(tenders) ? tenders : []; S.meta = meta; S.now = Date.now();
      S.byId = new Map(S.tenders.map((t) => [t.id, t]));
      const latest = S.tenders.reduce((m, t) => ((t.first_seen || "") > m ? t.first_seen : m), "");
      S.newSince = S.lastVisit && S.lastVisit < latest ? S.lastVisit : (latest ? prevDay(latest) : "");
      const openNow = S.tenders.filter(isOpen);
      S.firstDay = openNow.length > 0 && openNow.filter(isNew).length >= 0.9 * openNow.length; // everything is new: badges would be noise
      if (S.firstDay) S.newSince = "";
      if (latest) store.set("tr.lastVisit", latest);
      renderUpdated();
      $("loading").classList.add("hidden");
      render();
      if (S.open) openTender(S.open, false);
    } catch (err) {
      $("loading").classList.add("hidden");
      const box = $("empty"); box.classList.remove("hidden");
      box.replaceChildren(el("h2", { text: "Couldn’t load tenders" }), el("p", { text: "The data file did not load. Your filters are kept." }),
        el("button", { type: "button", class: "btn primary", text: "Try again", on: { click: load } }));
      $("updated").textContent = "Data not available";
    }
  }
  function renderUpdated() {
    const gen = S.meta && ms(S.meta.generated_at);
    $("updated").textContent = gen ? `Updated ${fmtDate(S.meta.generated_at, true)} · source: Prozorro` : "";
    const stale = gen && S.now - gen > 36 * 3600 * 1000;
    $("stale").classList.toggle("hidden", !stale);
    if (stale) $("stale").textContent = `Data is from ${fmtDate(S.meta.generated_at, true)} — the daily update hasn’t run since. Deadlines may have changed.`;
  }

  // ---------- wiring ----------
  function bind() {
    let timer;
    $("q").addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { S.q = e.target.value; S.page = 1; render(); }, 150); });
    $("sort").addEventListener("change", (e) => { S.sort = e.target.value; S.page = 1; render(); });
    $("per").addEventListener("change", (e) => { S.per = Number(e.target.value); S.page = 1; render(); });
    $("tab-all").addEventListener("click", () => setView("all"));
    $("tab-short").addEventListener("click", () => setView("short"));
    $("short-csv").addEventListener("click", () => csv(sorted(baseItems())));
    $("short-copy").addEventListener("click", () => copy(shortlistText(), "Shortlist copied"));
    $("short-clear").addEventListener("click", clearShortlist);
    $("export-csv").addEventListener("click", () => csv(sorted(baseItems().filter((t) => passes(t)))));
    $("open-filters").addEventListener("click", () => sheet(true));
    $("sheet-close").addEventListener("click", () => sheet(false));
    $("sheet-done").addEventListener("click", () => sheet(false));
    $("clear-all-2").addEventListener("click", () => { clearAll(); render(); });
    $("drawer-close").addEventListener("click", closeTender);
    $("scrim").addEventListener("click", () => { if (!$("drawer").hidden) closeTender(); else sheet(false); });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (!$("drawer").hidden) closeTender(); else if ($("filters").classList.contains("open")) sheet(false);
    });
    window.addEventListener("popstate", () => { readUrl(); render(); if (S.open) openTender(S.open, false); else closeTender(); });
    const m = location.hostname.match(/^([^.]+)\.github\.io$/);
    const repo = location.pathname.split("/").filter(Boolean)[0];
    if (m && repo) $("source-link").href = `https://github.com/${m[1]}/${repo}`;
  }

  // ---------- start ----------
  S.short = new Map(Object.entries(store.get("tr.shortlist", {}) || {}));
  S.lastVisit = store.get("tr.lastVisit", "") || "";
  readUrl(); bind(); load();
})();
