const CONFIG = {
  csvUrl: "https://raw.githubusercontent.com/huangziwei/mcc/refs/heads/main/post/merged/modern-chinese-common-words.csv",
  title: "Modern Chinese Common Words",
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
const ERHUA_EXCEPTIONS = new Set(["儿", "女儿"]);
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
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char === "\r") {
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
  const lines = text.split(/\r?\n/);
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
  return { stats, csvText: filtered.join("\n") };
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
