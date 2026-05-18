"use strict";

// ── Constants ──────────────────────────────────────────────────────────────

const REGIONS = ["USA", "Südamerika", "Russland", "China", "Indien"];
const REGION_META = {
  USA:           { flag: "🇺🇸", accent: "border-blue-600"   },
  "Südamerika":  { flag: "🌎",  accent: "border-green-600"  },
  Russland:      { flag: "🇷🇺", accent: "border-red-700"    },
  China:         { flag: "🇨🇳", accent: "border-yellow-600" },
  Indien:        { flag: "🇮🇳", accent: "border-orange-600" },
};

// ── State ──────────────────────────────────────────────────────────────────

let allArticles  = [];
let currentView  = "regions";   // regions | trending | breaking | mostread
let activeRegion = null;
let typeFilter   = "all";       // all | Mainstream | Alternative
let timeFilterH  = 48;
let searchQuery  = "";

// ── Click tracking (localStorage) ─────────────────────────────────────────

function getClicks() {
  try { return JSON.parse(localStorage.getItem("gnm_clicks") || "{}"); } catch { return {}; }
}
function recordClick(link) {
  const c = getClicks(); c[link] = (c[link] || 0) + 1;
  try { localStorage.setItem("gnm_clicks", JSON.stringify(c)); } catch {}
}
function clickCount(link) { return getClicks()[link] || 0; }

// ── Utilities ──────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
function show(id) { document.getElementById(id)?.classList.remove("hidden"); }
function hide(id) { document.getElementById(id)?.classList.add("hidden"); }

function chipCls(active) {
  return `px-2.5 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer ${
    active ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300 hover:bg-gray-600"
  }`;
}

function setRefreshBusy(busy) {
  const btn = document.getElementById("refresh-btn");
  const icon = document.getElementById("refresh-icon");
  if (!btn || !icon) return;
  btn.disabled = busy;
  icon.classList.toggle("spinner", busy);
  btn.classList.toggle("opacity-60", busy);
}

function formatAge(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso), diff = Date.now() - d.getTime();
    const m = Math.floor(diff / 60_000);
    if (m < 1)  return "gerade eben";
    if (m < 60) return `vor ${m} Min.`;
    const h = Math.floor(m / 60);
    if (h < 24) return `vor ${h} Std.`;
    return `vor ${Math.floor(h / 24)} Tag(en)`;
  } catch { return null; }
}

// ── Filtering ──────────────────────────────────────────────────────────────

function applyFilters(articles) {
  const cutoff = Date.now() - timeFilterH * 3_600_000;
  return articles.filter(a => {
    if (typeFilter !== "all" && a.type !== typeFilter) return false;
    if (a.published && new Date(a.published).getTime() < cutoff) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      if (!a.title.toLowerCase().includes(q) &&
          !(a.summary || "").toLowerCase().includes(q) &&
          !a.source.toLowerCase().includes(q)) return false;
    }
    return true;
  });
}

// ── Card builder ───────────────────────────────────────────────────────────

function buildCard(article, opts = {}) {
  const isMainstream = article.type === "Mainstream";
  const borderColor  = isMainstream ? "border-l-orange-500" : "border-l-emerald-500";
  const labelCls     = isMainstream
    ? "bg-orange-950/70 text-orange-300 border border-orange-700/50"
    : "bg-emerald-950/70 text-emerald-300 border border-emerald-700/50";

  const age    = formatAge(article.published);
  const clicks = clickCount(article.link);

  const card = document.createElement("a");
  card.href   = article.link;
  card.target = "_blank";
  card.rel    = "noopener noreferrer";
  card.className = [
    "news-card block bg-gray-800 hover:bg-gray-750",
    "border border-gray-700 hover:border-gray-600",
    "border-l-4", borderColor,
    "rounded-lg p-3 group",
    "hover:shadow-lg hover:shadow-black/40",
  ].join(" ");
  card.addEventListener("click", () => recordClick(article.link));

  const badges = [];
  if (article.urgent)   badges.push(`<span class="text-[10px] px-1.5 py-0.5 rounded bg-red-900/70 text-red-300 border border-red-700/50 font-bold urgent-pulse">⚡ Breaking</span>`);
  if (article.trending) badges.push(`<span class="text-[10px] px-1.5 py-0.5 rounded bg-yellow-900/70 text-yellow-300 border border-yellow-700/50 font-bold">🔥 ${article.coverage_count} Quellen</span>`);
  if (clicks > 0)       badges.push(`<span class="text-[10px] text-gray-500">👁 ${clicks}×</span>`);
  const regionTag = opts.showRegion
    ? `<span class="text-[10px] text-gray-500">${REGION_META[article.region]?.flag ?? ""} ${esc(article.region)}</span>`
    : "";

  card.innerHTML = `
    <div class="flex items-start justify-between gap-2 mb-1.5">
      <span class="text-xs font-semibold text-gray-300 leading-tight truncate">${esc(article.source)}</span>
      <span class="text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0 ${labelCls}">${isMainstream ? "Mainstream" : "Alternativ"}</span>
    </div>
    ${(badges.length || regionTag) ? `<div class="flex flex-wrap gap-1.5 mb-1.5">${badges.join("")}${regionTag}</div>` : ""}
    <h3 class="text-sm font-semibold text-gray-100 group-hover:text-white leading-snug mb-2 line-clamp-3">
      ${esc(article.title)}
    </h3>
    ${article.summary ? `<p class="text-xs text-gray-500 leading-relaxed line-clamp-2 mb-2">${esc(article.summary)}</p>` : ""}
    ${age ? `<time class="text-[10px] text-gray-600">${age}</time>` : ""}
  `;
  return card;
}

// ── Region filter bar ──────────────────────────────────────────────────────

function buildRegionBar(byRegion) {
  const bar = document.getElementById("region-filter");
  if (!bar) return;
  bar.innerHTML = "";
  bar.style.display = "";

  const mkBtn = (label, region) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.className = chipCls(region === null ? activeRegion === null : activeRegion === region);
    // All filter changes go through render() so the grid is always cleanly rebuilt
    b.onclick = () => {
      activeRegion = (activeRegion === region) ? null : region;
      render();
    };
    bar.appendChild(b);
  };

  mkBtn("Alle", null);
  REGIONS.forEach(r => mkBtn(`${REGION_META[r]?.flag ?? ""} ${r} (${(byRegion[r] || []).length})`, r));
}

// ── Shared region-column layout ────────────────────────────────────────────

/**
 * Renders articles in regional columns (same layout for all views).
 * @param {object[]} articles  - pre-filtered/sorted articles for this view
 * @param {string}   emptyMsg  - shown per column when no articles match
 */
function renderByRegion(articles, emptyMsg = "Keine Artikel") {
  const grid = document.getElementById("news-grid");

  // Group by region (preserving order within each group)
  const byRegion = Object.fromEntries(REGIONS.map(r => [r, []]));
  articles.forEach(a => { if (byRegion[a.region]) byRegion[a.region].push(a); });

  buildRegionBar(byRegion);

  const cols = document.createElement("div");
  cols.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-5";

  REGIONS.forEach(region => {
    const meta       = REGION_META[region] ?? { flag: "🌍", accent: "border-gray-600" };
    const regionArts = byRegion[region] ?? [];
    const visible    = !activeRegion || activeRegion === region;

    const col = document.createElement("div");
    col.className      = "flex flex-col gap-2.5";
    col.dataset.region = region;
    col.style.display  = visible ? "" : "none";

    const hdr = document.createElement("div");
    hdr.className = `flex items-center gap-2 pb-2 border-b-2 ${meta.accent} sticky top-[136px] bg-gray-900 pt-1 z-10`;
    hdr.innerHTML = `
      <span class="text-xl leading-none">${meta.flag}</span>
      <h2 class="text-sm font-bold text-white uppercase tracking-wider">${esc(region)}</h2>
      <span class="ml-auto text-[10px] text-gray-500 font-mono">${regionArts.length}</span>`;
    col.appendChild(hdr);

    if (regionArts.length === 0) {
      const p = document.createElement("p");
      p.className   = "text-gray-600 text-xs italic text-center mt-6";
      p.textContent = emptyMsg;
      col.appendChild(p);
    } else {
      regionArts.forEach(a => col.appendChild(buildCard(a)));
    }
    cols.appendChild(col);
  });

  grid.appendChild(cols);
}

// ── View renderers ─────────────────────────────────────────────────────────

function renderRegions(articles) {
  renderByRegion(articles, "Keine Artikel");
}

function renderTrending(articles) {
  const filtered = articles
    .filter(a => (a.coverage_count ?? 1) >= 2)
    .sort((a, b) => (b.coverage_count ?? 1) - (a.coverage_count ?? 1));

  const grid = document.getElementById("news-grid");
  const total = filtered.length;
  const hdr   = document.createElement("p");
  hdr.className   = "text-gray-500 text-sm mb-4";
  hdr.textContent = total
    ? `${total} Artikel von mehreren Quellen gleichzeitig abgedeckt`
    : "Keine Trending-Artikel für die gewählten Filter.";
  grid.appendChild(hdr);

  renderByRegion(filtered, "Kein Trending in dieser Region");
}

function renderBreaking(articles) {
  const filtered = articles.filter(a => a.urgent);

  const grid = document.getElementById("news-grid");
  const hdr  = document.createElement("p");
  hdr.className = "text-gray-500 text-sm mb-4";
  hdr.innerHTML = filtered.length
    ? `<span class="text-red-400 urgent-pulse">⚡</span> ${filtered.length} Breaking-Artikel`
    : "Aktuell keine Breaking-News in den gefilterten Artikeln.";
  grid.appendChild(hdr);

  renderByRegion(filtered, "Kein Breaking in dieser Region");
}

function renderMostRead(articles) {
  const clicks     = getClicks();
  const filtered   = articles
    .map(a => ({ ...a, _clicks: clicks[a.link] || 0 }))
    .filter(a => a._clicks > 0)
    .sort((a, b) => b._clicks - a._clicks);

  const grid = document.getElementById("news-grid");

  if (filtered.length === 0) {
    const info = document.createElement("div");
    info.className = "flex flex-col items-center py-20 text-gray-500 gap-3";
    info.innerHTML = `
      <svg class="w-12 h-12 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7
                 -1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
      </svg>
      <p class="text-sm text-center">Du hast noch keine Artikel angeklickt.<br>
         Klicke Artikel an — sie erscheinen hier sortiert nach Klickzahl.</p>`;
    grid.appendChild(info);
    return;
  }

  const hdr = document.createElement("p");
  hdr.className   = "text-gray-500 text-sm mb-4";
  hdr.textContent = `${filtered.length} gelesene Artikel (auf diesem Gerät gespeichert)`;
  grid.appendChild(hdr);

  renderByRegion(filtered, "Noch nichts gelesen in dieser Region");
}

// ── Central render ─────────────────────────────────────────────────────────

function render() {
  const grid = document.getElementById("news-grid");
  grid.innerHTML = "";   // always start clean
  hide("empty-box");

  const filtered = applyFilters(allArticles);

  const countEl = document.getElementById("article-count");
  if (countEl) countEl.textContent = `${filtered.length} Artikel`;

  // Hide region bar for non-region views; renderRegions will show it
  const rf = document.getElementById("region-filter");
  if (rf && currentView !== "regions") {
    rf.innerHTML = "";
    rf.style.display = "none";
  }

  switch (currentView) {
    case "regions":  renderRegions(filtered);  break;
    case "trending": renderTrending(filtered); break;
    case "breaking": renderBreaking(filtered); break;
    case "mostread": renderMostRead(filtered); break;
  }
}

// ── Filter / view setters ──────────────────────────────────────────────────

function setView(v) {
  currentView  = v;
  activeRegion = null;
  document.querySelectorAll(".view-tab").forEach(b => {
    b.className = `view-tab px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
      b.dataset.view === v
        ? "bg-blue-600 text-white"
        : "bg-gray-700 text-gray-300 hover:bg-gray-600"
    }`;
  });
  render();
}

function setTypeFilter(t) {
  typeFilter = t;
  document.querySelectorAll(".type-tab").forEach(b => {
    b.className = `type-tab px-2.5 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer ${
      b.dataset.type === t
        ? "bg-blue-600 text-white"
        : "bg-gray-700 text-gray-300 hover:bg-gray-600"
    }`;
  });
  render();
}

function setTimeFilter(h) {
  timeFilterH = parseInt(h, 10);
  render();
}

function setSearch(q) {
  searchQuery = q.trim();
  render();
}

// ── Data loading ───────────────────────────────────────────────────────────

async function loadNews() {
  hide("error-box");
  hide("empty-box");
  show("loading");
  hide("news-grid");
  setRefreshBusy(true);

  try {
    const res = await fetch(`/data/news.json?_=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
    allArticles = await res.json();

    hide("loading");
    show("news-grid");

    const ts = document.getElementById("last-updated");
    if (ts) ts.textContent = `Stand: ${new Date().toLocaleTimeString("de-DE")}`;

    render();
  } catch (err) {
    hide("loading");
    const box = document.getElementById("error-box");
    if (box) { box.textContent = `Fehler: ${err.message}`; show("error-box"); }
  } finally {
    setRefreshBusy(false);
  }
}

// ── Boot ───────────────────────────────────────────────────────────────────
setView("regions");
loadNews();
