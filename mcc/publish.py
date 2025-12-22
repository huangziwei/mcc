from __future__ import annotations

from pathlib import Path

from rich.console import Console

DEFAULT_CSV_URL = (
    "https://raw.githubusercontent.com/huangziwei/mcc/refs/heads/main/"
    "post/merged/modern-chinese-common-words.csv"
)
DEFAULT_TITLE = "Modern Chinese Common Words"

_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>__TITLE__</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=Noto+Serif+SC:wght@400;600&display=swap"
      rel="stylesheet"
    />
    <link rel="stylesheet" href="styles.css?v=6" />
  </head>
  <body>
    <header class="top">
      <div class="title">
        <div class="title-main">__TITLE__</div>
        <div class="title-sub">Proofread word list</div>
      </div>
      <div class="filters">
        <div class="filter-label">Length</div>
        <div class="filter-group" role="group" aria-label="Filter by word length">
          <button class="filter-btn is-active" type="button" data-length-filter="all">
            All
          </button>
          <button class="filter-btn" type="button" data-length-filter="1">1</button>
          <button class="filter-btn" type="button" data-length-filter="2">2</button>
          <button class="filter-btn" type="button" data-length-filter="3">3</button>
          <button class="filter-btn" type="button" data-length-filter="4+">4+</button>
        </div>
      </div>
      <div class="meta">
        <div id="status" class="status">Loading...</div>
        <div id="count" class="count"></div>
      </div>
    </header>
    <main id="word-view" class="word-view">
      <div id="word-grid" class="word-grid" aria-live="polite"></div>
    </main>
    <div class="scroll-hint" id="scroll-hint">Scroll horizontally &rarr;</div>
    <script src="app.js?v=6"></script>
  </body>
</html>
"""

_STYLES_TEMPLATE = """:root {
  color-scheme: light;
  --bg: #f6f1e7;
  --bg-soft: #fdfaf4;
  --ink: #2b2621;
  --muted: #6b6159;
  --accent: #c46b32;
  --shadow: rgba(41, 33, 25, 0.08);
  --word-size: clamp(18px, 1.6vw + 10px, 26px);
  --row-height: calc(var(--word-size) * 1.8);
  --column-gap: clamp(20px, 3vw, 40px);
  --pad-x: clamp(20px, 4vw, 56px);
  --pad-y: clamp(16px, 3vw, 40px);
  --app-height: 100vh;
  --header-height: 0px;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  color: var(--ink);
  background: radial-gradient(
      circle at top left,
      rgba(255, 255, 255, 0.85),
      rgba(255, 255, 255, 0) 55%
    ),
    linear-gradient(140deg, #f7efe3 0%, #f2e4d4 50%, #f9f2ea 100%);
  min-height: var(--app-height);
  height: var(--app-height);
  overflow: hidden;
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  background-image: radial-gradient(
      rgba(255, 255, 255, 0.5) 1px,
      transparent 1px
    ),
    radial-gradient(rgba(255, 255, 255, 0.35) 1px, transparent 1px);
  background-size: 28px 28px, 42px 42px;
  background-position: 0 0, 10px 8px;
  pointer-events: none;
  opacity: 0.6;
  z-index: -1;
}

.top {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
  justify-content: space-between;
  padding: var(--pad-y) var(--pad-x) 12px;
  border-bottom: 1px solid rgba(43, 38, 33, 0.12);
  background: rgba(253, 250, 244, 0.88);
  backdrop-filter: blur(6px);
}

.title {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.title-main {
  font-size: clamp(22px, 3vw, 36px);
  font-weight: 600;
  letter-spacing: 0.02em;
}

.title-sub {
  color: var(--muted);
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  text-align: right;
  font-size: 13px;
  color: var(--muted);
}

.filters {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--muted);
}

.filter-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.filter-btn {
  border: 1px solid rgba(43, 38, 33, 0.18);
  background: rgba(253, 250, 244, 0.9);
  color: var(--ink);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.filter-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 12px var(--shadow);
}

.filter-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.filter-btn.is-active {
  background: var(--ink);
  color: #fff;
  border-color: var(--ink);
  box-shadow: 0 6px 16px var(--shadow);
}

.status {
  font-weight: 600;
  color: var(--ink);
}

.status.error {
  color: #b42318;
}

.count {
  white-space: nowrap;
}

.word-view {
  height: calc(var(--app-height) - var(--header-height));
  overflow-x: auto;
  overflow-y: hidden;
  padding: 12px var(--pad-x) var(--pad-y);
  scroll-behavior: smooth;
  scrollbar-color: rgba(0, 0, 0, 0.3) transparent;
  touch-action: pan-x;
}

.word-grid {
  --rows: 1;
  display: grid;
  grid-auto-flow: column;
  grid-template-rows: repeat(var(--rows), var(--row-height));
  grid-auto-rows: var(--row-height);
  grid-auto-columns: max-content;
  column-gap: var(--column-gap);
  align-content: start;
  min-width: 100%;
  height: 100%;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 0.6s ease, transform 0.6s ease;
}

.word-grid.loaded {
  opacity: 1;
  transform: translateY(0);
}

.word {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  height: var(--row-height);
  padding-right: 4px;
  white-space: nowrap;
  color: var(--ink);
}

.word-index {
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  font-size: 0.6em;
  line-height: 1;
  color: var(--muted);
  min-width: 5ch;
  text-align: right;
  letter-spacing: 0.08em;
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
}

.word-text {
  font-family: "Noto Serif SC", serif;
  font-size: var(--word-size);
  line-height: 1;
  letter-spacing: 0.08em;
}

.scroll-hint {
  position: fixed;
  right: 18px;
  bottom: 14px;
  font-size: 12px;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.7);
  padding: 6px 10px;
  border-radius: 999px;
  box-shadow: 0 6px 18px var(--shadow);
  pointer-events: none;
}

@media (max-width: 720px) {
  .top {
    flex-direction: column;
    align-items: flex-start;
  }

  .meta {
    text-align: left;
  }

  .filters {
    width: 100%;
  }

  .scroll-hint {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .word-grid {
    transition: none;
  }
}
"""

_APP_TEMPLATE = """const CONFIG = {
  csvUrl: "__CSV_URL__",
  title: "__TITLE__",
  proofreadOnly: true,
};

const elements = {
  grid: document.getElementById("word-grid"),
  status: document.getElementById("status"),
  count: document.getElementById("count"),
  view: document.getElementById("word-view"),
  header: document.querySelector(".top"),
  filterButtons: Array.from(document.querySelectorAll("[data-length-filter]")),
};

const STATS_PREFIX = "# mcc-stats:";
const dataState = {
  stats: null,
  totalRows: 0,
  allEntries: [],
  filteredEntries: [],
  lengthStats: null,
};
const filterState = { value: "all" };
const layoutState = { rows: 1 };
const renderState = { entries: [], rendered: 0, chunkSize: 400 };
let scrollTicking = false;

function setStatus(message, isError = false) {
  elements.status.textContent = message;
  elements.status.classList.toggle("error", isError);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-US");
}

function formatPercent(numerator, denominator) {
  if (!denominator) {
    return "0.0%";
  }
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function wordLength(word) {
  return Array.from(word).length;
}

function parseFilterValue(value) {
  if (!value || value === "all") {
    return { mode: "all" };
  }
  if (value.endsWith("+")) {
    const minValue = Number.parseInt(value, 10);
    if (Number.isFinite(minValue)) {
      return { mode: "min", value: minValue };
    }
  }
  const exactValue = Number.parseInt(value, 10);
  if (Number.isFinite(exactValue)) {
    return { mode: "exact", value: exactValue };
  }
  return { mode: "all" };
}

function formatFilterLabel(value) {
  if (!value || value === "all") {
    return "All lengths";
  }
  if (value.endsWith("+")) {
    return `${value} chars`;
  }
  return `${value} chars`;
}

function filterEntries(entries, value) {
  const parsed = parseFilterValue(value);
  if (parsed.mode === "all") {
    return entries;
  }
  return entries.filter((entry) => {
    const length = wordLength(entry.word);
    if (parsed.mode === "exact") {
      return length === parsed.value;
    }
    return length >= parsed.value;
  });
}

function sumCounts(byLength, minValue) {
  if (!byLength) {
    return 0;
  }
  let total = 0;
  Object.entries(byLength).forEach(([key, value]) => {
    const length = Number.parseInt(key, 10);
    if (!Number.isFinite(length)) {
      return;
    }
    if (minValue === null || length >= minValue) {
      total += Number(value) || 0;
    }
  });
  return total;
}

function getCountsForFilter() {
  const lengthStats = dataState.lengthStats;
  const parsed = parseFilterValue(filterState.value);
  if (!lengthStats) {
    const total = dataState.totalRows || dataState.filteredEntries.length;
    return { proofread: dataState.filteredEntries.length, total };
  }
  if (parsed.mode === "all") {
    return {
      proofread: lengthStats.proofreadWords,
      total: lengthStats.totalWords,
    };
  }
  if (parsed.mode === "exact") {
    return {
      proofread: lengthStats.proofreadByLength[parsed.value] || 0,
      total: lengthStats.totalByLength[parsed.value] || 0,
    };
  }
  if (parsed.mode === "min") {
    return {
      proofread: sumCounts(lengthStats.proofreadByLength, parsed.value),
      total: sumCounts(lengthStats.totalByLength, parsed.value),
    };
  }
  return {
    proofread: lengthStats.proofreadWords,
    total: lengthStats.totalWords,
  };
}

function updateStatusText() {
  const base = CONFIG.proofreadOnly ? "Proofread words" : "All words";
  const label = formatFilterLabel(filterState.value);
  setStatus(`${base} • ${label}`);
}

function updateFilterButtons() {
  elements.filterButtons.forEach((button) => {
    const isActive = button.dataset.lengthFilter === filterState.value;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function applyFilter(value) {
  filterState.value = value || "all";
  dataState.filteredEntries = filterEntries(
    dataState.allEntries,
    filterState.value
  );
  resetRender(dataState.filteredEntries);
  updateMeta();
  updateStatusText();
  updateFilterButtons();
}

function initFilters() {
  if (!elements.filterButtons.length) {
    return;
  }
  elements.filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      applyFilter(button.dataset.lengthFilter);
    });
  });
  const active = elements.filterButtons.find((button) =>
    button.classList.contains("is-active")
  );
  filterState.value = active ? active.dataset.lengthFilter : "all";
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        cell += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char === "\\r") {
      continue;
    } else {
      cell += char;
    }
  }
  row.push(cell);
  if (row.length > 1 || row[0] !== "") {
    rows.push(row);
  }
  return rows;
}

function stripStatsHeader(text) {
  let stats = null;
  const lines = text.split(/\\r?\\n/);
  const filtered = [];
  for (const line of lines) {
    if (!stats && line.startsWith(STATS_PREFIX)) {
      const payload = line.slice(STATS_PREFIX.length).trim();
      try {
        stats = JSON.parse(payload);
      } catch (error) {
        stats = null;
      }
      continue;
    }
    if (line.startsWith("#")) {
      continue;
    }
    filtered.push(line);
  }
  return { stats, csvText: filtered.join("\\n") };
}

function normalizeRanges(values) {
  const ranges = [];
  if (!Array.isArray(values)) {
    return ranges;
  }
  values.forEach((entry) => {
    if (Array.isArray(entry) && entry.length >= 2) {
      ranges.push([Number(entry[0]), Number(entry[1])]);
    } else if (Number.isFinite(entry)) {
      ranges.push([Number(entry), Number(entry)]);
    }
  });
  return ranges;
}

function collectProofreadRanges(stats) {
  const rangesByPass = stats && stats.rows ? stats.rows.ranges_by_pass : null;
  if (!rangesByPass || typeof rangesByPass !== "object") {
    return null;
  }
  let ranges = [];
  Object.keys(rangesByPass).forEach((passKey) => {
    ranges = ranges.concat(normalizeRanges(rangesByPass[passKey]));
  });
  if (!ranges.length) {
    return null;
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged = [ranges[0]];
  for (let i = 1; i < ranges.length; i += 1) {
    const prev = merged[merged.length - 1];
    const current = ranges[i];
    if (current[0] <= prev[1] + 1) {
      prev[1] = Math.max(prev[1], current[1]);
    } else {
      merged.push(current);
    }
  }
  return merged;
}

function createRangeChecker(ranges) {
  if (!ranges || ranges.length === 0) {
    return null;
  }
  let rangeIndex = 0;
  let current = ranges[0];
  return (rowIndex) => {
    while (current && rowIndex > current[1]) {
      rangeIndex += 1;
      current = ranges[rangeIndex];
    }
    return !!current && rowIndex >= current[0] && rowIndex <= current[1];
  };
}

function updateMeta() {
  const { proofread, total } = getCountsForFilter();
  elements.count.textContent = `Proofread: ${formatPercent(
    proofread,
    total
  )} (${formatNumber(proofread)} / ${formatNumber(total)})`;
}

function setChunkSize() {
  const rows = layoutState.rows || 1;
  const target = rows * 20;
  renderState.chunkSize = Math.max(200, Math.min(target, 1200));
}

function renderNextChunk() {
  if (renderState.rendered >= renderState.entries.length) {
    return;
  }
  const start = renderState.rendered;
  const end = Math.min(
    start + renderState.chunkSize,
    renderState.entries.length
  );
  const fragment = document.createDocumentFragment();
  for (let i = start; i < end; i += 1) {
    const entry = renderState.entries[i];
    const div = document.createElement("div");
    div.className = "word";
    const indexSpan = document.createElement("span");
    indexSpan.className = "word-index";
    indexSpan.textContent = entry.rank;
    const textSpan = document.createElement("span");
    textSpan.className = "word-text";
    textSpan.textContent = entry.word;
    div.appendChild(indexSpan);
    div.appendChild(textSpan);
    fragment.appendChild(div);
  }
  elements.grid.appendChild(fragment);
  renderState.rendered = end;
  if (start === 0) {
    elements.grid.classList.add("loaded");
  }
}

function fillViewport() {
  if (!elements.view) {
    return;
  }
  let safety = 0;
  let lastWidth = -1;
  while (
    renderState.rendered < renderState.entries.length &&
    elements.view.scrollWidth <= elements.view.clientWidth + 40 &&
    safety < 6
  ) {
    renderNextChunk();
    if (elements.view.scrollWidth === lastWidth) {
      break;
    }
    lastWidth = elements.view.scrollWidth;
    safety += 1;
  }
}

function shouldLoadMore() {
  if (!elements.view) {
    return false;
  }
  const threshold = Math.max(elements.view.clientWidth * 0.6, 320);
  return (
    elements.view.scrollLeft + elements.view.clientWidth >=
    elements.view.scrollWidth - threshold
  );
}

function maybeRenderMore() {
  let safety = 0;
  while (
    shouldLoadMore() &&
    renderState.rendered < renderState.entries.length &&
    safety < 6
  ) {
    renderNextChunk();
    safety += 1;
  }
}

function resetRender(entries) {
  renderState.entries = entries;
  renderState.rendered = 0;
  elements.grid.textContent = "";
  elements.grid.classList.remove("loaded");
  if (elements.view) {
    elements.view.scrollLeft = 0;
  }
  setChunkSize();
  renderNextChunk();
  fillViewport();
}

function onScroll() {
  if (scrollTicking) {
    return;
  }
  scrollTicking = true;
  requestAnimationFrame(() => {
    scrollTicking = false;
    maybeRenderMore();
  });
}

function updateLayout() {
  const appHeight = window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${appHeight}px`);
  const headerHeight = elements.header
    ? elements.header.getBoundingClientRect().height
    : 0;
  document.documentElement.style.setProperty(
    "--header-height",
    `${headerHeight}px`
  );
  const rowHeightValue = getComputedStyle(document.documentElement)
    .getPropertyValue("--row-height")
    .trim();
  const rowHeight = Number.parseFloat(rowHeightValue) || 32;
  const viewStyles = elements.view ? getComputedStyle(elements.view) : null;
  const paddingY = viewStyles
    ? Number.parseFloat(viewStyles.paddingTop) +
      Number.parseFloat(viewStyles.paddingBottom)
    : 0;
  const available = Math.max(1, appHeight - headerHeight - paddingY);
  const rows = Math.max(1, Math.floor(available / rowHeight));
  layoutState.rows = rows;
  elements.grid.style.setProperty("--rows", rows);
  if (elements.view) {
    elements.view.style.height = `${rows * rowHeight + paddingY}px`;
  }
  setChunkSize();
  fillViewport();
}

function applyTitle() {
  if (!CONFIG.title) {
    return;
  }
  document.title = CONFIG.title;
  const titleEl = document.querySelector(".title-main");
  if (titleEl) {
    titleEl.textContent = CONFIG.title;
  }
}

async function loadWords() {
  setStatus("Loading merged CSV...");
  const response = await fetch(CONFIG.csvUrl, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Fetch failed: ${response.status}`);
  }
  const text = await response.text();
  const { stats, csvText } = stripStatsHeader(text);
  const rows = parseCsv(csvText);
  if (!rows.length) {
    throw new Error("CSV has no rows.");
  }
  const header = rows[0].map((value) => value.trim().toLowerCase());
  let indexIndex = header.indexOf("index");
  if (indexIndex === -1) {
    indexIndex = 0;
  }
  let wordIndex = header.indexOf("word");
  if (wordIndex === -1) {
    wordIndex = 1;
  }

  const proofreadRanges = collectProofreadRanges(stats);
  const isProofreadRow = createRangeChecker(proofreadRanges);
  const lengthStats = {
    totalByLength: {},
    proofreadByLength: {},
    totalWords: 0,
    proofreadWords: 0,
  };
  const entries = [];
  for (let i = 1; i < rows.length; i += 1) {
    const rowIndex = i;
    const word = (rows[i][wordIndex] || "").trim();
    if (word) {
      const length = wordLength(word);
      lengthStats.totalByLength[length] =
        (lengthStats.totalByLength[length] || 0) + 1;
      lengthStats.totalWords += 1;
      const proofread = isProofreadRow ? isProofreadRow(rowIndex) : true;
      if (proofread) {
        lengthStats.proofreadByLength[length] =
          (lengthStats.proofreadByLength[length] || 0) + 1;
        lengthStats.proofreadWords += 1;
      }
      if (CONFIG.proofreadOnly && !proofread) {
        continue;
      }
      const rankRaw = rows[i][indexIndex];
      const rank = rankRaw && String(rankRaw).trim() ? String(rankRaw).trim() : String(i);
      entries.push({ rank, word });
    }
  }
  return { stats, entries, totalRows: lengthStats.totalWords, lengthStats };
}

async function init() {
  applyTitle();
  initFilters();
  updateLayout();
  if (elements.view) {
    elements.view.addEventListener("scroll", onScroll, { passive: true });
  }
  window.addEventListener("resize", () => {
    window.clearTimeout(window.__mccResizeTimer);
    window.__mccResizeTimer = window.setTimeout(updateLayout, 150);
  });
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(updateLayout).catch(() => null);
  }
  try {
    const { stats, entries, totalRows, lengthStats } = await loadWords();
    dataState.stats = stats;
    dataState.totalRows = totalRows;
    dataState.allEntries = entries;
    dataState.lengthStats = lengthStats;
    applyFilter(filterState.value);
    updateLayout();
  } catch (error) {
    setStatus("Failed to load word list.", true);
    elements.count.textContent = "";
  }
}

init();
"""


def publish_site(
    site_dir: Path,
    csv_url: str = DEFAULT_CSV_URL,
    title: str = DEFAULT_TITLE,
) -> None:
    console = Console(stderr=True)
    site_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "index.html": _INDEX_TEMPLATE,
        "styles.css": _STYLES_TEMPLATE,
        "app.js": _APP_TEMPLATE,
    }
    for name, template in files.items():
        content = template.replace("__CSV_URL__", csv_url).replace("__TITLE__", title)
        (site_dir / name).write_text(content, encoding="utf-8")
    console.log(f"Wrote site files to {site_dir}")
