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
    <link rel="stylesheet" href="styles.css?v=11" />
  </head>
  <body>
    <header class="top">
      <div class="title">
        <div class="title-main">__TITLE__</div>
        <div class="search">
          <label class="sr-only" for="search-input">Search words</label>
          <input
            id="search-input"
            class="search-input"
            type="search"
            placeholder="Search words"
            autocomplete="off"
            spellcheck="false"
          />
        </div>
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
    <footer class="footer">
      <div class="footer-inner">
        Source: 李行健、苏新春（主编）. 《现代汉语常用词表（第2版）》. 北京：商务印书馆, 2021.
        ISBN 978-7-100-20011-0.
      </div>
    </footer>
    <div class="scroll-hint" id="scroll-hint">Scroll horizontally &rarr;</div>
    <script src="app.js?v=11"></script>
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
  --footer-height: 0px;
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

.search {
  margin-top: 6px;
}

.search-input {
  width: clamp(180px, 30vw, 320px);
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(43, 38, 33, 0.18);
  background: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--ink);
}

.search-input::placeholder {
  color: rgba(43, 38, 33, 0.5);
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(196, 107, 50, 0.18);
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

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
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
  height: calc(var(--app-height) - var(--header-height) - var(--footer-height));
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

.word-text .erhua {
  font-size: 0.72em;
  letter-spacing: 0;
  margin-left: 0.06em;
  opacity: 0.75;
}

.footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 6px var(--pad-x) 8px;
  border-top: 1px solid rgba(43, 38, 33, 0.12);
  background: rgba(253, 250, 244, 0.92);
  font-size: 11px;
  color: var(--muted);
  backdrop-filter: blur(6px);
}

.footer-inner {
  white-space: nowrap;
  overflow-x: auto;
  overflow-y: hidden;
  -webkit-overflow-scrolling: touch;
}

.footer-inner::-webkit-scrollbar {
  height: 4px;
}

.footer-inner::-webkit-scrollbar-thumb {
  background: rgba(43, 38, 33, 0.25);
  border-radius: 999px;
}

.scroll-hint {
  position: fixed;
  right: 18px;
  bottom: calc(var(--footer-height) + 14px);
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

  .search-input {
    width: min(100%, 320px);
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
  searchInput: document.getElementById("search-input"),
  view: document.getElementById("word-view"),
  header: document.querySelector(".top"),
  footer: document.querySelector(".footer"),
  filterButtons: Array.from(document.querySelectorAll("[data-length-filter]")),
};

const STATS_PREFIX = "# mcc-stats:";
const ERHUA_EXCEPTIONS = new Set(["儿", "女儿", "男儿", "新生儿", "婴儿", "少儿", "孤儿", "幼儿", "小儿", "健儿", "胎儿"]);
const dataState = {
  stats: null,
  allEntries: [],
  filteredEntries: [],
  matchCounts: { proofread: 0, total: 0 },
};
const filterState = { value: "all" };
const searchState = { query: "", timer: null };
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

function normalizeQuery(value) {
  return String(value || "").trim().toLowerCase();
}

function scheduleFilterUpdate() {
  if (searchState.timer) {
    window.clearTimeout(searchState.timer);
  }
  searchState.timer = window.setTimeout(() => {
    searchState.timer = null;
    applyFilters();
  }, 120);
}

function appendWordText(target, word) {
  if (word.endsWith("儿") && !ERHUA_EXCEPTIONS.has(word)) {
    const prefix = word.slice(0, -1);
    target.textContent = "";
    target.appendChild(document.createTextNode(prefix));
    const small = document.createElement("small");
    small.className = "erhua";
    small.textContent = "儿";
    target.appendChild(small);
    return;
  }
  target.textContent = word;
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

function matchesLength(entry, parsed) {
  if (parsed.mode === "all") {
    return true;
  }
  if (parsed.mode === "exact") {
    return entry.length === parsed.value;
  }
  return entry.length >= parsed.value;
}

function matchesSearch(entry, query) {
  if (!query) {
    return true;
  }
  return entry.search.includes(query);
}

function updateStatusText() {
  const base = CONFIG.proofreadOnly ? "Proofread words" : "All words";
  const label = formatFilterLabel(filterState.value);
  const queryLabel = searchState.query ? ` • "${searchState.query}"` : "";
  setStatus(`${base} • ${label}${queryLabel}`);
}

function updateFilterButtons() {
  elements.filterButtons.forEach((button) => {
    const isActive = button.dataset.lengthFilter === filterState.value;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function applyFilters() {
  const parsed = parseFilterValue(filterState.value);
  const query = searchState.query;
  const displayEntries = [];
  const counts = { proofread: 0, total: 0 };
  for (const entry of dataState.allEntries) {
    if (!matchesLength(entry, parsed)) {
      continue;
    }
    if (!matchesSearch(entry, query)) {
      continue;
    }
    counts.total += 1;
    if (entry.proofread) {
      counts.proofread += 1;
    }
    if (CONFIG.proofreadOnly && !entry.proofread) {
      continue;
    }
    displayEntries.push(entry);
  }
  dataState.filteredEntries = displayEntries;
  dataState.matchCounts = counts;
  resetRender(displayEntries);
  updateMeta();
  updateStatusText();
  updateFilterButtons();
  updateLayout();
}

function applyFilter(value) {
  filterState.value = value || "all";
  applyFilters();
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

function initSearch() {
  if (!elements.searchInput) {
    return;
  }
  elements.searchInput.addEventListener("input", () => {
    const next = normalizeQuery(elements.searchInput.value);
    if (next === searchState.query) {
      return;
    }
    searchState.query = next;
    scheduleFilterUpdate();
  });
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
  const { proofread, total } = dataState.matchCounts;
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
    appendWordText(textSpan, entry.word);
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
  const appHeight = window.visualViewport
    ? window.visualViewport.height
    : document.documentElement.clientHeight || window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${appHeight}px`);
  const headerHeight = elements.header
    ? elements.header.getBoundingClientRect().height
    : 0;
  const footerHeight = elements.footer
    ? elements.footer.getBoundingClientRect().height
    : 0;
  document.documentElement.style.setProperty(
    "--header-height",
    `${headerHeight}px`
  );
  document.documentElement.style.setProperty(
    "--footer-height",
    `${footerHeight}px`
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
  const viewHeight = elements.view
    ? elements.view.clientHeight
    : Math.max(1, appHeight - headerHeight - footerHeight);
  const available = Math.max(1, viewHeight - paddingY);
  const rows = Math.max(1, Math.floor(available / rowHeight));
  layoutState.rows = rows;
  elements.grid.style.setProperty("--rows", rows);
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
  const entries = [];
  for (let i = 1; i < rows.length; i += 1) {
    const rowIndex = i;
    const word = (rows[i][wordIndex] || "").trim();
    if (!word) {
      continue;
    }
    const length = wordLength(word);
    const proofread = isProofreadRow ? isProofreadRow(rowIndex) : true;
    const rankRaw = rows[i][indexIndex];
    const rank =
      rankRaw && String(rankRaw).trim() ? String(rankRaw).trim() : String(i);
    entries.push({
      rank,
      word,
      proofread,
      length,
      search: word.toLowerCase(),
    });
  }
  return { stats, entries };
}

async function init() {
  applyTitle();
  initFilters();
  initSearch();
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
    const { stats, entries } = await loadWords();
    dataState.stats = stats;
    dataState.allEntries = entries;
    applyFilters();
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
