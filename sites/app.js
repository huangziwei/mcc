const CONFIG = {
    csvUrl: "https://raw.githubusercontent.com/huangziwei/mcc/refs/heads/main/post/merged/modern-chinese-common-words.csv",
    title: "Modern Chinese Common Words",
    proofreadOnly: true,
};

const elements = {
  grid: document.getElementById("word-grid"),
  status: document.getElementById("status"),
  count: document.getElementById("count"),
  passes: document.getElementById("passes"),
  view: document.getElementById("word-view"),
  header: document.querySelector(".top"),
};

const STATS_PREFIX = "# mcc-stats:";
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

function updateMeta(stats, shownCount, totalRows) {
    if (!stats || !stats.rows) {
        elements.count.textContent = `Rows: ${formatNumber(totalRows)}`;
        elements.passes.textContent = "";
        return;
    }
    const proofread = stats.rows.proofread || shownCount;
    const total = stats.rows.total || totalRows;
    elements.count.textContent = `Proofread rows: ${formatNumber(proofread)} / ${formatNumber(total)}`;
    const passes = stats.rows.passes || {};
    const passEntries = Object.entries(passes).sort((a, b) => Number(a[0]) - Number(b[0]));
    elements.passes.textContent = passEntries.length
        ? `Passes: ${passEntries.map(([pass, count]) => `pass ${pass}: ${formatNumber(count)}`).join(", ")}`
        : "";
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
    const headerHeight = elements.header ? elements.header.getBoundingClientRect().height : 0;
    document.documentElement.style.setProperty("--header-height", `${headerHeight}px`);
    const rowHeightValue = getComputedStyle(document.documentElement).getPropertyValue("--row-height").trim();
    const rowHeight = Number.parseFloat(rowHeightValue) || 32;
    const viewStyles = elements.view ? getComputedStyle(elements.view) : null;
    const paddingY = viewStyles
        ? Number.parseFloat(viewStyles.paddingTop) + Number.parseFloat(viewStyles.paddingBottom)
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
    const isProofreadRow = CONFIG.proofreadOnly ? createRangeChecker(proofreadRanges) : null;
  const entries = [];
  for (let i = 1; i < rows.length; i += 1) {
    const rowIndex = i;
    if (isProofreadRow && !isProofreadRow(rowIndex)) {
      continue;
    }
    const word = (rows[i][wordIndex] || "").trim();
    if (word) {
      const rankRaw = rows[i][indexIndex];
      const rank = rankRaw && String(rankRaw).trim() ? String(rankRaw).trim() : String(i);
      entries.push({ rank, word });
    }
  }
  return { stats, entries, totalRows: rows.length - 1 };
}

async function init() {
    applyTitle();
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
    const { stats, entries, totalRows } = await loadWords();
    resetRender(entries);
    updateLayout();
    updateMeta(stats, entries.length, totalRows);
    setStatus(CONFIG.proofreadOnly ? "Showing proofread words" : "Showing all words");
    } catch (error) {
        setStatus("Failed to load word list.", true);
        elements.count.textContent = "";
        elements.passes.textContent = "";
    }
}

init();
