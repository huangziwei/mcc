const CONFIG = {
    csvUrl: "https://raw.githubusercontent.com/huangziwei/mcc/refs/heads/main/post/merged/modern-chinese-common-words.csv",
    title: "Modern Chinese Common Words",
    proofreadOnly: true,
};

const elements = {
    grid: document.getElementById("word-grid"),
    status: document.getElementById("status"),
    count: document.getElementById("count"),
    searchInput: document.getElementById("search-input"),
    pinyinToggle: document.getElementById("pinyin-toggle"),
    view: document.getElementById("word-view"),
    header: document.querySelector(".top"),
    footer: document.querySelector(".footer"),
    filterSelect: document.getElementById("length-filter"),
};

const STATS_PREFIX = "# mcc-stats:";
const ERHUA_EXCEPTIONS = new Set([
    "儿",
    "女儿",
    "男儿",
    "新生儿",
    "婴儿",
    "少儿",
    "孤儿",
    "幼儿",
    "小儿",
    "健儿",
    "胎儿",
]);
const dataState = {
    stats: null,
    allEntries: [],
    filteredEntries: [],
    matchCounts: { proofread: 0, total: 0 },
};
const filterState = { value: "all" };
const searchState = { query: "", timer: null, matcher: null };
const pinyinState = { visible: false };
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

const TONE_MARKS = {
    ā: { base: "a", tone: 1 },
    á: { base: "a", tone: 2 },
    ǎ: { base: "a", tone: 3 },
    à: { base: "a", tone: 4 },
    ē: { base: "e", tone: 1 },
    é: { base: "e", tone: 2 },
    ě: { base: "e", tone: 3 },
    è: { base: "e", tone: 4 },
    ī: { base: "i", tone: 1 },
    í: { base: "i", tone: 2 },
    ǐ: { base: "i", tone: 3 },
    ì: { base: "i", tone: 4 },
    ō: { base: "o", tone: 1 },
    ó: { base: "o", tone: 2 },
    ǒ: { base: "o", tone: 3 },
    ò: { base: "o", tone: 4 },
    ū: { base: "u", tone: 1 },
    ú: { base: "u", tone: 2 },
    ǔ: { base: "u", tone: 3 },
    ù: { base: "u", tone: 4 },
    ǖ: { base: "ü", tone: 1 },
    ǘ: { base: "ü", tone: 2 },
    ǚ: { base: "ü", tone: 3 },
    ǜ: { base: "ü", tone: 4 },
};
const TONE_MARK_RE = /[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]/;
const TONE_DIGIT_RE = /[1-5]/;
const CJK_RE = /[\u3400-\u9fff]/;
const PINYIN_ALLOWED_RE =
    /^[a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüv\s*?'\d]+$/i;
const PINYIN_VOWEL_RE = /[aeiouüvāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]/i;

function normalizePattern(value) {
    return String(value || "").replace(/？/g, "?").replace(/＊/g, "*");
}

function isLikelyPinyin(value) {
    const trimmed = normalizePattern(value).trim();
    if (!trimmed) {
        return false;
    }
    if (CJK_RE.test(trimmed)) {
        return false;
    }
    if (!PINYIN_ALLOWED_RE.test(trimmed)) {
        return false;
    }
    if (TONE_DIGIT_RE.test(trimmed)) {
        return true;
    }
    return PINYIN_VOWEL_RE.test(trimmed);
}

function detectPinyinMode(value) {
    if (TONE_DIGIT_RE.test(value)) {
        return "digits";
    }
    if (TONE_MARK_RE.test(value)) {
        return "marks";
    }
    return "plain";
}

function normalizePinyinMarks(value) {
    return normalizePattern(value)
        .toLowerCase()
        .replace(/v/g, "ü")
        .replace(/\s+/g, " ")
        .trim();
}

function normalizePinyinPlain(value) {
    const marked = normalizePinyinMarks(value);
    if (!marked) {
        return "";
    }
    let result = "";
    for (const char of marked) {
        if (char === "*" || char === "?" || char === " ") {
            result += char;
            continue;
        }
        if (char >= "1" && char <= "5") {
            continue;
        }
        const mapped = TONE_MARKS[char];
        if (mapped) {
            result += mapped.base;
            continue;
        }
        result += char;
    }
    return result.trim().replace(/\s+/g, " ");
}

function pinyinTokenToDigits(token) {
    if (!token) {
        return "";
    }
    const suffixMatch = token.match(/[*?]+$/);
    const suffix = suffixMatch ? suffixMatch[0] : "";
    const core = suffix ? token.slice(0, -suffix.length) : token;
    let tone = 0;
    let output = "";
    for (const char of core) {
        if (char === "*" || char === "?") {
            output += char;
            continue;
        }
        if (char >= "1" && char <= "5") {
            tone = Number(char);
            continue;
        }
        const mapped = TONE_MARKS[char];
        if (mapped) {
            output += mapped.base;
            tone = mapped.tone;
            continue;
        }
        output += char;
    }
    if (!output && !suffix) {
        return "";
    }
    if (tone > 0) {
        output += String(tone);
    }
    return output + suffix;
}

function normalizePinyinDigits(value) {
    const marked = normalizePinyinMarks(value);
    if (!marked) {
        return "";
    }
    const tokens = marked.split(/\s+/).filter(Boolean);
    return tokens.map((token) => pinyinTokenToDigits(token)).join(" ");
}

function scheduleFilterUpdate() {
    if (searchState.timer) {
        window.clearTimeout(searchState.timer);
    }
    searchState.timer = window.setTimeout(() => {
        searchState.timer = null;
        searchState.matcher = buildSearchMatcher(searchState.query);
        applyFilters();
    }, 120);
}

function parsePinyinTokens(value) {
    const raw = String(value || "").trim();
    if (!raw) {
        return [];
    }
    return raw.split(/\s+/);
}

function normalizeErhuaToken(token) {
    const raw = normalizePattern(token).trim().toLowerCase().replace(/v/g, "ü");
    if (!raw) {
        return "";
    }
    const trimmed = raw.replace(/[*?]+$/g, "");
    let result = "";
    for (const char of trimmed) {
        if (char >= "1" && char <= "5") {
            continue;
        }
        const mapped = TONE_MARKS[char];
        result += mapped ? mapped.base : char;
    }
    return result;
}

function isErhuaToken(token) {
    const normalized = normalizeErhuaToken(token);
    if (!normalized) {
        return null;
    }
    if (normalized === "er") {
        return false;
    }
    return normalized.endsWith("r");
}

function shouldUseErhua(word, tokens) {
    if (!word.endsWith("儿")) {
        return false;
    }
    if (tokens && tokens.length) {
        const lastToken = tokens[tokens.length - 1];
        if (lastToken) {
            const erhua = isErhuaToken(lastToken);
            if (erhua !== null) {
                return erhua;
            }
        }
    }
    return !ERHUA_EXCEPTIONS.has(word);
}

function appendWordRuby(target, entry) {
    target.textContent = "";
    const ruby = document.createElement("ruby");
    ruby.className = "word-ruby";
    const chars = Array.from(entry.word);
    const tokens = entry.pinyinTokens || [];
    const useErhua = shouldUseErhua(entry.word, tokens);
    const lastIndex = chars.length - 1;
    chars.forEach((char, index) => {
        if (useErhua && index === lastIndex) {
            const span = document.createElement("span");
            span.className = "erhua";
            span.textContent = char;
            ruby.appendChild(span);
        } else {
            ruby.appendChild(document.createTextNode(char));
        }
        const rt = document.createElement("rt");
        const token = tokens[index];
        rt.textContent = token ? token : "\u00a0";
        ruby.appendChild(rt);
    });
    target.appendChild(ruby);
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

function matchesSearch(entry) {
    if (!searchState.matcher) {
        return true;
    }
    return searchState.matcher(entry);
}

function matchGlob(text, pattern) {
    const textChars = Array.from(text);
    const patternChars = Array.from(pattern);
    let tIndex = 0;
    let pIndex = 0;
    let starIndex = -1;
    let matchIndex = 0;
    while (tIndex < textChars.length) {
        if (
            pIndex < patternChars.length &&
            (patternChars[pIndex] === "?" ||
                patternChars[pIndex] === textChars[tIndex])
        ) {
            tIndex += 1;
            pIndex += 1;
            continue;
        }
        if (pIndex < patternChars.length && patternChars[pIndex] === "*") {
            starIndex = pIndex;
            matchIndex = tIndex;
            pIndex += 1;
            continue;
        }
        if (starIndex !== -1) {
            pIndex = starIndex + 1;
            matchIndex += 1;
            tIndex = matchIndex;
            continue;
        }
        return false;
    }
    while (pIndex < patternChars.length && patternChars[pIndex] === "*") {
        pIndex += 1;
    }
    return pIndex === patternChars.length;
}

function buildSearchMatcher(query) {
    const normalized = normalizePattern(query);
    const trimmed = normalized.trim();
    if (!trimmed) {
        return null;
    }
    let mode = "auto";
    let term = trimmed;
    const lowered = trimmed.toLowerCase();
    if (lowered.startsWith("py:")) {
        mode = "pinyin";
        term = trimmed.slice(3).trim();
    } else if (lowered.startsWith("word:")) {
        mode = "word";
        term = trimmed.slice(5).trim();
    } else if (isLikelyPinyin(trimmed)) {
        mode = "pinyin";
    } else {
        mode = "word";
    }
    if (!term) {
        return null;
    }
    const hasWildcard = /[*?]/.test(term);
    if (mode === "word") {
        if (!hasWildcard) {
            const termLower = term.toLowerCase();
            return (entry) => entry.word.toLowerCase().includes(termLower);
        }
        const termLower = term.toLowerCase();
        return (entry) => matchGlob(entry.word.toLowerCase(), termLower);
    }
    const pinyinMode = detectPinyinMode(term);
    const normalizer =
        pinyinMode === "digits"
            ? normalizePinyinDigits
            : pinyinMode === "marks"
              ? normalizePinyinMarks
              : normalizePinyinPlain;
    const normalizedQuery = normalizer(term);
    if (!normalizedQuery) {
        return null;
    }
    if (!hasWildcard) {
        return (entry) => normalizer(entry.pinyin).includes(normalizedQuery);
    }
    return (entry) => matchGlob(normalizer(entry.pinyin), normalizedQuery);
}

function updateStatusText() {
    const base = CONFIG.proofreadOnly ? "Proofread words" : "All words";
    const label = formatFilterLabel(filterState.value);
    const queryLabel = searchState.query ? ` • "${searchState.query}"` : "";
    setStatus(`${base} • ${label}${queryLabel}`);
}

function updateFilterControl() {
    if (!elements.filterSelect) {
        return;
    }
    if (elements.filterSelect.value !== filterState.value) {
        elements.filterSelect.value = filterState.value;
    }
}

function applyFilters() {
    const parsed = parseFilterValue(filterState.value);
    const displayEntries = [];
    const counts = { proofread: 0, total: 0 };
    for (const entry of dataState.allEntries) {
        if (!matchesLength(entry, parsed)) {
            continue;
        }
        if (!matchesSearch(entry)) {
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
    updateFilterControl();
    updateLayout();
}

function applyFilter(value) {
    filterState.value = value || "all";
    applyFilters();
}

function initFilters() {
    if (!elements.filterSelect) {
        return;
    }
    elements.filterSelect.addEventListener("change", () => {
        applyFilter(elements.filterSelect.value);
    });
    filterState.value = elements.filterSelect.value || "all";
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

function updatePinyinToggle() {
    if (!elements.pinyinToggle || !elements.grid) {
        return;
    }
    const isActive = pinyinState.visible;
    elements.pinyinToggle.classList.toggle("is-active", isActive);
    elements.pinyinToggle.setAttribute(
        "aria-pressed",
        isActive ? "true" : "false"
    );
    elements.grid.classList.toggle("show-pinyin", isActive);
}

function initPinyinToggle() {
    if (!elements.pinyinToggle) {
        return;
    }
    elements.pinyinToggle.addEventListener("click", () => {
        pinyinState.visible = !pinyinState.visible;
        updatePinyinToggle();
    });
    updatePinyinToggle();
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
        appendWordRuby(textSpan, entry);
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

function getRowHeight() {
    if (elements.grid) {
        const gridStyles = getComputedStyle(elements.grid);
        const autoRows = gridStyles.gridAutoRows;
        const parsed = Number.parseFloat(autoRows);
        if (Number.isFinite(parsed) && parsed > 0) {
            return parsed;
        }
    }
    if (!document.body) {
        return 32;
    }
    const probe = document.createElement("div");
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    probe.style.height = "var(--row-height)";
    probe.style.width = "1px";
    probe.style.pointerEvents = "none";
    document.body.appendChild(probe);
    const height =
        probe.getBoundingClientRect().height || probe.offsetHeight || 0;
    probe.remove();
    return height || 32;
}

function updateLayout() {
    const viewportHeight =
        document.documentElement.clientHeight || window.innerHeight;
    const visualHeight = window.visualViewport
        ? window.visualViewport.height
        : viewportHeight;
    const appHeight = Math.min(visualHeight, viewportHeight);
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
    const rowHeight = getRowHeight();
    const viewStyles = elements.view ? getComputedStyle(elements.view) : null;
    const paddingTop = viewStyles
        ? Number.parseFloat(viewStyles.paddingTop) || 0
        : 0;
    const viewHeight = elements.view
        ? elements.view.getBoundingClientRect().height
        : Math.max(1, appHeight - headerHeight - footerHeight);
    const available = Math.max(1, viewHeight - paddingTop);
    const rows = Math.max(1, Math.floor(available / rowHeight));
    const nextPaddingBottom = Math.max(
        0,
        viewHeight - paddingTop - rows * rowHeight
    );
    if (elements.view) {
        elements.view.style.paddingBottom = `${Math.max(
            0,
            nextPaddingBottom
        )}px`;
    }
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
    let pinyinIndex = header.indexOf("pinyin");
    if (pinyinIndex === -1) {
        pinyinIndex = null;
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
        const pinyinRaw =
            pinyinIndex !== null && pinyinIndex < rows[i].length
                ? rows[i][pinyinIndex]
                : "";
        const pinyinTokens = parsePinyinTokens(pinyinRaw);
        entries.push({
            rank,
            word,
            proofread,
            length,
            pinyin: pinyinRaw,
            pinyinTokens,
            search: word.toLowerCase(),
        });
    }
    return { stats, entries };
}

async function init() {
    applyTitle();
    initFilters();
    initPinyinToggle();
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
