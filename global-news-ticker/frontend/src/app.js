// Global News Monitor — Frontend App
// Vanilla JS + Tailwind CSS, no build step required.

"use strict";

// ── Configuration ──────────────────────────────────────────────────────────

const REGIONS = ["USA", "Südamerika", "Russland", "China", "Indien"];

const REGION_META = {
  USA:          { flag: "🇺🇸", accent: "border-blue-700" },
  "Südamerika": { flag: "🌎", accent: "border-green-700" },
  Russland:     { flag: "🇷🇺", accent: "border-red-800" },
  China:        { flag: "🇨🇳", accent: "border-yellow-700" },
  Indien:       { flag: "🇮🇳", accent: "border-orange-700" },
};

// Active region filter (null = show all)
let activeRegion = null;

// ── State helpers ──────────────────────────────────────────────────────────

function show(id) { document.getElementById(id)?.classList.remove("hidden"); }
function hide(id) { document.getElementById(id)?.classList.add("hidden"); }

function setRefreshBusy(busy) {
  const btn = document.getElementById("refresh-btn");
  const icon = document.getElementById("refresh-icon");
  if (!btn || !icon) return;
  btn.disabled = busy;
  icon.classList.toggle("spinner", busy);
  btn.classList.toggle("opacity-60", busy);
  btn.classList.toggle("cursor-not-allowed", busy);
}

// ── Date formatting ────────────────────────────────────────────────────────

function formatAge(isoString) {
  if (!isoString) return null;
  try {
    const d = new Date(isoString);
    const diffMs = Date.now() - d.getTime();
    const mins = Math.floor(diffMs / 60_000);
    if (mins < 1)   return "gerade eben";
    if (mins < 60)  return `vor ${mins} Min.`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `vor ${hours} Std.`;
    const days = Math.floor(hours / 24);
    return `vor ${days} Tag${days > 1 ? "en" : ""}`;
  } catch {
    return null;
  }
}

// ── HTML escaping ──────────────────────────────────────────────────────────

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Card builder ───────────────────────────────────────────────────────────

function buildCard(article) {
  const isMainstream = article.type === "Mainstream";

  // Left border + label colour distinguishes Mainstream vs. Alternative
  const borderAccent = isMainstream ? "border-l-orange-500"  : "border-l-emerald-500";
  const labelCls     = isMainstream
    ? "bg-orange-950/70 text-orange-300 border border-orange-700/50"
    : "bg-emerald-950/70 text-emerald-300 border border-emerald-700/50";
  const labelText    = isMainstream ? "Mainstream" : "Alternativ";

  const age = formatAge(article.published);

  const card = document.createElement("a");
  card.href = article.link;
  card.target = "_blank";
  card.rel = "noopener noreferrer";
  card.className = [
    "news-card block bg-gray-800 hover:bg-gray-750",
    "border border-gray-700 hover:border-gray-600",
    "border-l-4", borderAccent,
    "rounded-lg p-3 group",
    "hover:shadow-lg hover:shadow-black/40",
  ].join(" ");

  card.innerHTML = `
    <div class="flex items-start justify-between gap-2 mb-2">
      <span class="text-xs font-semibold text-gray-300 leading-tight truncate">${esc(article.source)}</span>
      <span class="text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0 ${labelCls}">${labelText}</span>
    </div>
    <h3 class="text-sm font-semibold text-gray-100 group-hover:text-white
               leading-snug mb-2 line-clamp-3">
      ${esc(article.title)}
    </h3>
    ${article.summary
      ? `<p class="text-xs text-gray-500 leading-relaxed line-clamp-2 mb-2">${esc(article.summary)}</p>`
      : ""}
    ${age ? `<time class="text-[10px] text-gray-600">${age}</time>` : ""}
  `;

  return card;
}

// ── Region column builder ──────────────────────────────────────────────────

function buildRegionColumn(region, articles) {
  const meta = REGION_META[region] ?? { flag: "🌍", accent: "border-gray-600" };

  const col = document.createElement("div");
  col.className = "flex flex-col gap-2.5";
  col.dataset.region = region;

  // Sticky region header
  const header = document.createElement("div");
  header.className = [
    "flex items-center gap-2 pb-2",
    "border-b-2", meta.accent,
    "sticky top-[88px] bg-gray-900 pt-1 z-10",
  ].join(" ");
  header.innerHTML = `
    <span class="text-xl leading-none">${meta.flag}</span>
    <h2 class="text-sm font-bold text-white uppercase tracking-wider">${esc(region)}</h2>
    <span class="ml-auto text-[10px] text-gray-500 font-mono tabular-nums">${articles.length}</span>
  `;
  col.appendChild(header);

  if (articles.length === 0) {
    const empty = document.createElement("p");
    empty.className = "text-gray-600 text-xs italic text-center mt-6";
    empty.textContent = "Keine Artikel verfügbar";
    col.appendChild(empty);
    return col;
  }

  articles.forEach((art) => col.appendChild(buildCard(art)));
  return col;
}

// ── Filter bar ─────────────────────────────────────────────────────────────

function buildFilterBar(byRegion) {
  const bar = document.getElementById("filter-bar");
  if (!bar) return;
  bar.innerHTML = "";

  const allBtn = document.createElement("button");
  allBtn.textContent = "Alle";
  allBtn.dataset.region = "";
  allBtn.className = chipClass(activeRegion === null);
  allBtn.onclick = () => { activeRegion = null; applyFilter(); };
  bar.appendChild(allBtn);

  REGIONS.forEach((r) => {
    const count = (byRegion[r] ?? []).length;
    const btn = document.createElement("button");
    btn.textContent = `${REGION_META[r]?.flag ?? ""} ${r} (${count})`;
    btn.dataset.region = r;
    btn.className = chipClass(activeRegion === r);
    btn.onclick = () => { activeRegion = activeRegion === r ? null : r; applyFilter(); };
    bar.appendChild(btn);
  });
}

function chipClass(active) {
  return [
    "px-2.5 py-1 rounded-full text-xs font-medium transition-colors",
    active
      ? "bg-blue-600 text-white"
      : "bg-gray-700 text-gray-300 hover:bg-gray-600",
  ].join(" ");
}

function applyFilter() {
  // Re-render filter chips with updated active state
  const bar = document.getElementById("filter-bar");
  if (bar) {
    bar.querySelectorAll("button").forEach((btn) => {
      const region = btn.dataset.region;
      const isActive = activeRegion === null ? region === "" : region === activeRegion;
      btn.className = chipClass(isActive);
    });
  }

  // Show / hide columns
  const grid = document.getElementById("news-grid");
  if (!grid) return;
  grid.querySelectorAll("[data-region]").forEach((col) => {
    const show = activeRegion === null || col.dataset.region === activeRegion;
    col.style.display = show ? "" : "none";
  });
}

// ── Grid renderer ──────────────────────────────────────────────────────────

function renderGrid(articles) {
  const grid = document.getElementById("news-grid");
  if (!grid) return;
  grid.innerHTML = "";

  // Group by region
  const byRegion = Object.fromEntries(REGIONS.map((r) => [r, []]));
  articles.forEach((a) => {
    if (byRegion[a.region]) byRegion[a.region].push(a);
  });

  // Article count
  const countEl = document.getElementById("article-count");
  if (countEl) countEl.textContent = `${articles.length} Artikel`;

  buildFilterBar(byRegion);

  const columns = document.createElement("div");
  columns.className =
    "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-5";
  grid.appendChild(columns);

  REGIONS.forEach((region) => {
    columns.appendChild(buildRegionColumn(region, byRegion[region] ?? []));
  });

  applyFilter();
}

// ── Main fetch ─────────────────────────────────────────────────────────────

async function loadNews() {
  hide("error-box");
  hide("empty-box");
  hide("news-grid");
  show("loading");
  setRefreshBusy(true);

  try {
    // Cache-bust so the browser always fetches fresh JSON
    const res = await fetch(`/data/news.json?_=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);

    const articles = await res.json();
    hide("loading");

    if (!Array.isArray(articles) || articles.length === 0) {
      show("empty-box");
    } else {
      show("news-grid");
      renderGrid(articles);
    }

    const ts = document.getElementById("last-updated");
    if (ts) {
      ts.textContent = `Stand: ${new Date().toLocaleTimeString("de-DE")}`;
    }
  } catch (err) {
    hide("loading");
    const box = document.getElementById("error-box");
    if (box) {
      box.textContent = `Fehler beim Laden der Nachrichten: ${err.message}`;
      show("error-box");
    }
  } finally {
    setRefreshBusy(false);
  }
}

// ── Boot ───────────────────────────────────────────────────────────────────
loadNews();
