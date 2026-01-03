const CONFIG = {
    csvUrl: "https://raw.githubusercontent.com/huangziwei/mcc/refs/heads/main/post/merged/modern-chinese-common-words.csv",
    dictionaryManifestUrl: "dictionaries/manifest.json",
    title: "Modern Chinese Common Words",
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
    footerInner: document.querySelector(".footer-inner"),
    lengthSelect: document.getElementById("length-filter"),
    rankSelect: document.getElementById("rank-filter"),
    originSelect: document.getElementById("origin-filter"),
};

const RANK_OPTIONS = [500, 1000, 3000, 5000, 10000, 20000, 30000, 40000, 50000];
const STATS_PREFIX = "# mcc-stats:";
const FOOTER_SOURCES = new Map([
    ["佛源", "Source: 孙维张（主编）. 《佛源语词词典》. 北京：语文出版社, 2007. ISBN 978-7-80184-151-3."],
]);
const dataState = {
    stats: null,
    allEntries: [],
    filteredEntries: [],
    wordLookup: new Map(),
    matchCounts: { proofread: 0, total: 0 },
};
const filterState = { value: "all" };
const rankState = { value: "1" };
const originState = { value: "all" };
const searchState = { query: "", timer: null, matcher: null };
const layoutState = { rows: 1 };
const renderState = { entries: [], rendered: 0, chunkSize: 400 };
const footerState = { defaultText: "" };
const selectionMenuState = {
    menu: null,
    copyWordButton: null,
    copyPinyinButton: null,
    searchButton: null,
    dictionaryPanel: null,
    dictionaryStatus: null,
    dictionaryResults: null,
    selectionMeta: null,
    selectionMetaWord: null,
    selectionMetaDetails: null,
    word: "",
    pinyin: "",
    timer: null,
    lookupId: 0,
    anchorRect: null,
};
const dictionaryState = {
    manifest: null,
    manifestPromise: null,
    dictionaries: new Map(),
    loading: new Map(),
};
let scrollTicking = false;
let filterMeasureSpan = null;

function setStatus(message, isError = false) {
    elements.status.textContent = message;
    elements.status.classList.toggle("error", isError);
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString("en-US");
}

function normalizeQuery(value) {
    return String(value || "")
        .trim()
        .toLowerCase();
}

function normalizeOrigin(value) {
    return String(value || "")
        .trim()
        .toLowerCase();
}

function normalizeFooterText(value) {
    return String(value || "")
        .replace(/\s+/g, " ")
        .trim();
}

function updateFooterSource() {
    if (!elements.footerInner) {
        return;
    }
    if (!footerState.defaultText) {
        footerState.defaultText = normalizeFooterText(elements.footerInner.textContent);
    }
    const normalizedOrigin = normalizeOrigin(originState.value);
    const mappedSource = FOOTER_SOURCES.get(normalizedOrigin);
    const nextText = normalizeFooterText(mappedSource || footerState.defaultText);
    if (!nextText) {
        return;
    }
    if (normalizeFooterText(elements.footerInner.textContent) === nextText) {
        return;
    }
    elements.footerInner.textContent = nextText;
}

function ensureFilterMeasureSpan() {
    if (filterMeasureSpan) {
        return filterMeasureSpan;
    }
    const span = document.createElement("span");
    span.style.position = "absolute";
    span.style.visibility = "hidden";
    span.style.whiteSpace = "pre";
    span.style.pointerEvents = "none";
    span.style.top = "-9999px";
    span.style.left = "-9999px";
    document.body.appendChild(span);
    filterMeasureSpan = span;
    return span;
}

function getSelectedLabel(select) {
    if (!select) {
        return "";
    }
    const option = select.selectedOptions && select.selectedOptions[0];
    if (option && option.textContent) {
        return option.textContent.trim();
    }
    return select.value || "";
}

function measureSelectWidth(select) {
    if (!select) {
        return 0;
    }
    const label = getSelectedLabel(select);
    if (!label) {
        return 0;
    }
    const span = ensureFilterMeasureSpan();
    const style = window.getComputedStyle(select);
    span.style.font = style.font;
    span.style.letterSpacing = style.letterSpacing;
    span.style.textTransform = style.textTransform;
    span.textContent = label;
    const textWidth = span.getBoundingClientRect().width;
    const paddingLeft = Number.parseFloat(style.paddingLeft) || 0;
    const paddingRight = Number.parseFloat(style.paddingRight) || 0;
    const borderLeft = Number.parseFloat(style.borderLeftWidth) || 0;
    const borderRight = Number.parseFloat(style.borderRightWidth) || 0;
    return Math.ceil(textWidth + paddingLeft + paddingRight + borderLeft + borderRight);
}

function syncFilterWidths() {
    const selects = [elements.lengthSelect, elements.rankSelect, elements.originSelect].filter(Boolean);
    if (!selects.length) {
        return;
    }
    selects.forEach((select) => {
        const width = measureSelectWidth(select);
        if (!Number.isFinite(width) || width <= 0) {
            select.style.removeProperty("--filter-width");
            return;
        }
        select.style.setProperty("--filter-width", `${Math.ceil(width)}px`);
    });
}

function createSelectionMenuButton(label) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "selection-menu-btn";
    button.textContent = label;
    return button;
}

async function copyToClipboard(text) {
    const value = String(text || "");
    if (!value) {
        return false;
    }
    if (navigator.clipboard && window.isSecureContext) {
        try {
            await navigator.clipboard.writeText(value);
            return true;
        } catch (error) {
            return false;
        }
    }
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "true");
    textarea.style.position = "fixed";
    textarea.style.top = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    let success = false;
    try {
        success = document.execCommand("copy");
    } catch (error) {
        success = false;
    }
    document.body.removeChild(textarea);
    return success;
}

function getDictionaryManifestUrl() {
    if (!CONFIG.dictionaryManifestUrl) {
        return "";
    }
    try {
        return new URL(CONFIG.dictionaryManifestUrl, window.location.href).toString();
    } catch (error) {
        return CONFIG.dictionaryManifestUrl;
    }
}

function resolveDictionaryUrl(path) {
    if (!path) {
        return "";
    }
    const manifestUrl = getDictionaryManifestUrl();
    if (!manifestUrl) {
        return path;
    }
    try {
        return new URL(path, manifestUrl).toString();
    } catch (error) {
        return path;
    }
}

async function loadDictionaryManifest() {
    if (!CONFIG.dictionaryManifestUrl) {
        return [];
    }
    if (dictionaryState.manifest) {
        return dictionaryState.manifest;
    }
    if (dictionaryState.manifestPromise) {
        return dictionaryState.manifestPromise;
    }
    dictionaryState.manifestPromise = (async () => {
        try {
            const url = getDictionaryManifestUrl();
            const response = await fetch(url, { cache: "no-store" });
            if (!response.ok) {
                throw new Error(`Manifest fetch failed: ${response.status}`);
            }
            const data = await response.json();
            const manifest = Array.isArray(data) ? data : [];
            dictionaryState.manifest = manifest;
            return manifest;
        } catch (error) {
            console.warn("Dictionary manifest failed to load.", error);
            dictionaryState.manifest = [];
            return [];
        } finally {
            dictionaryState.manifestPromise = null;
        }
    })();
    return dictionaryState.manifestPromise;
}

async function loadDictionary(definition) {
    if (!definition || !definition.id) {
        return null;
    }
    if (dictionaryState.dictionaries.has(definition.id)) {
        return dictionaryState.dictionaries.get(definition.id);
    }
    if (dictionaryState.loading.has(definition.id)) {
        return dictionaryState.loading.get(definition.id);
    }
    const url = resolveDictionaryUrl(definition.path || "");
    if (!url) {
        dictionaryState.dictionaries.set(definition.id, null);
        return null;
    }
    const promise = (async () => {
        try {
            const response = await fetch(url, { cache: "no-store" });
            if (!response.ok) {
                throw new Error(`Dictionary fetch failed: ${response.status}`);
            }
            const data = await response.json();
            const format = data && data.meta ? data.meta.format : null;
            if (format && format !== "mcc-dict-v1") {
                throw new Error(`Unsupported dictionary format: ${format}`);
            }
            dictionaryState.dictionaries.set(definition.id, data);
            return data;
        } catch (error) {
            console.warn(`Dictionary ${definition.id} failed to load.`, error);
            dictionaryState.dictionaries.set(definition.id, null);
            return null;
        } finally {
            dictionaryState.loading.delete(definition.id);
        }
    })();
    dictionaryState.loading.set(definition.id, promise);
    return promise;
}

function normalizeDictionaryEntries(rawEntries) {
    if (!rawEntries) {
        return [];
    }
    return Array.isArray(rawEntries) ? rawEntries : [rawEntries];
}

function formatDictionaryMeta(entry) {
    if (!entry || !entry.meta) {
        return "";
    }
    if (Array.isArray(entry.meta)) {
        return entry.meta.map((value) => String(value).trim()).filter(Boolean).join(" · ");
    }
    return String(entry.meta).trim();
}

function getClosestWordElement(node) {
    if (!node) {
        return null;
    }
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    if (!element) {
        return null;
    }
    return element.closest(".word");
}

function getSelectionContext() {
    if (!elements.view) {
        return null;
    }
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
        return null;
    }
    const range = selection.getRangeAt(0);
    if (!elements.view.contains(range.commonAncestorContainer)) {
        return null;
    }
    const text = selection.toString().trim();
    if (!text) {
        return null;
    }
    const rect = range.getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) {
        return null;
    }
    const anchorWord = getClosestWordElement(selection.anchorNode);
    const focusWord = getClosestWordElement(selection.focusNode);
    const wordElement = anchorWord && anchorWord === focusWord ? anchorWord : null;
    let word = text;
    let pinyin = "";
    if (wordElement) {
        const dataWord = wordElement.dataset.word || "";
        const dataPinyin = wordElement.dataset.pinyin || "";
        if (dataWord) {
            word = dataWord;
        }
        pinyin = dataPinyin.trim();
    } else if (dataState.wordLookup && dataState.wordLookup.has(text)) {
        const entry = dataState.wordLookup.get(text);
        pinyin = entry && entry.pinyin ? entry.pinyin.trim() : "";
    }
    return { word, pinyin, rect };
}

function positionSelectionMenu(rect) {
    const menu = selectionMenuState.menu;
    if (!menu || !rect) {
        return;
    }
    const menuRect = menu.getBoundingClientRect();
    const padding = 12;
    let x = rect.left + rect.width / 2 - menuRect.width / 2;
    let y = rect.top - menuRect.height - 10;
    if (y < padding) {
        y = rect.bottom + 10;
    }
    x = Math.min(Math.max(x, padding), window.innerWidth - menuRect.width - padding);
    y = Math.min(Math.max(y, padding), window.innerHeight - menuRect.height - padding);
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
}

function resetDictionaryPanel() {
    if (!selectionMenuState.dictionaryPanel || !selectionMenuState.dictionaryResults) {
        return;
    }
    selectionMenuState.dictionaryPanel.hidden = true;
    if (selectionMenuState.dictionaryStatus) {
        selectionMenuState.dictionaryStatus.textContent = "";
        selectionMenuState.dictionaryStatus.hidden = true;
    }
    selectionMenuState.dictionaryResults.textContent = "";
    selectionMenuState.dictionaryResults.hidden = true;
}

function renderDictionaryResults(results) {
    if (!selectionMenuState.dictionaryPanel || !selectionMenuState.dictionaryResults) {
        return;
    }
    selectionMenuState.dictionaryResults.textContent = "";
    results.forEach((result) => {
        const section = document.createElement("div");
        section.className = "selection-menu-dictionary-section";

        const title = document.createElement("div");
        title.className = "selection-menu-dictionary-title";
        title.textContent = result.label || result.id || "Dictionary";
        section.appendChild(title);

        result.entries.forEach((entry) => {
            const entryWrap = document.createElement("div");
            entryWrap.className = "selection-menu-dictionary-entry";

            const metaText = formatDictionaryMeta(entry);
            if (metaText) {
                const meta = document.createElement("div");
                meta.className = "selection-menu-dictionary-meta";
                meta.textContent = metaText;
                entryWrap.appendChild(meta);
            }

            const body = document.createElement("div");
            body.className = "selection-menu-dictionary-text";
            body.textContent = entry.text;
            entryWrap.appendChild(body);
            section.appendChild(entryWrap);
        });

        selectionMenuState.dictionaryResults.appendChild(section);
    });
    if (selectionMenuState.dictionaryStatus) {
        selectionMenuState.dictionaryStatus.textContent = "";
        selectionMenuState.dictionaryStatus.hidden = true;
    }
    selectionMenuState.dictionaryPanel.hidden = results.length === 0;
    selectionMenuState.dictionaryResults.hidden = results.length === 0;
    positionSelectionMenu(selectionMenuState.anchorRect);
}

async function updateDictionaryPanel(word) {
    if (!selectionMenuState.dictionaryPanel || !selectionMenuState.dictionaryResults) {
        return;
    }
    const lookupWord = String(word || "").trim();
    if (!lookupWord) {
        resetDictionaryPanel();
        return;
    }
    const lookupId = selectionMenuState.lookupId + 1;
    selectionMenuState.lookupId = lookupId;
    resetDictionaryPanel();

    const manifest = await loadDictionaryManifest();
    if (selectionMenuState.lookupId !== lookupId || selectionMenuState.word !== lookupWord) {
        return;
    }
    if (!manifest.length) {
        resetDictionaryPanel();
        return;
    }

    const dictionaries = await Promise.all(manifest.map((def) => loadDictionary(def)));
    if (selectionMenuState.lookupId !== lookupId || selectionMenuState.word !== lookupWord) {
        return;
    }

    const results = [];
    manifest.forEach((def, index) => {
        const data = dictionaries[index];
        if (!data || !data.entries) {
            return;
        }
        const rawEntries = data.entries[lookupWord];
        const entries = normalizeDictionaryEntries(rawEntries)
            .map((entry) => {
                if (typeof entry === "string") {
                    return { text: entry.trim() };
                }
                if (entry && typeof entry.text === "string") {
                    return {
                        text: entry.text.trim(),
                        meta: entry.meta,
                    };
                }
                return null;
            })
            .filter((entry) => entry && entry.text);
        if (!entries.length) {
            return;
        }
        results.push({
            id: def.id,
            label: def.label || (data.meta && data.meta.label) || def.id,
            entries,
        });
    });

    if (!results.length) {
        resetDictionaryPanel();
        return;
    }
    renderDictionaryResults(results);
}

function showSelectionMenu() {
    if (!selectionMenuState.menu) {
        return;
    }
    selectionMenuState.menu.classList.add("is-visible");
}

function hideSelectionMenu() {
    if (!selectionMenuState.menu) {
        return;
    }
    selectionMenuState.menu.classList.remove("is-visible");
    selectionMenuState.word = "";
    selectionMenuState.pinyin = "";
    selectionMenuState.anchorRect = null;
    if (selectionMenuState.selectionMeta) {
        selectionMenuState.selectionMeta.hidden = true;
    }
    resetDictionaryPanel();
}

function updateSelectionMenu() {
    const context = getSelectionContext();
    if (!context || !selectionMenuState.menu) {
        hideSelectionMenu();
        return;
    }
    const previousWord = selectionMenuState.word;
    selectionMenuState.word = context.word;
    selectionMenuState.pinyin = context.pinyin;
    selectionMenuState.anchorRect = context.rect;
    if (selectionMenuState.selectionMeta) {
        const entry = dataState.wordLookup ? dataState.wordLookup.get(context.word) : null;
        const rankText = entry && entry.rank ? `#${entry.rank}` : "";
        const details = [];
        if (context.pinyin) {
            details.push(context.pinyin);
        }
        if (rankText) {
            details.push(rankText);
        }
        if (selectionMenuState.selectionMetaWord) {
            selectionMenuState.selectionMetaWord.textContent = context.word;
        }
        if (selectionMenuState.selectionMetaDetails) {
            selectionMenuState.selectionMetaDetails.textContent = details.join(" · ");
            selectionMenuState.selectionMetaDetails.hidden = details.length === 0;
        }
        selectionMenuState.selectionMeta.hidden = false;
    }
    if (context.word !== previousWord) {
        resetDictionaryPanel();
    }
    if (selectionMenuState.copyPinyinButton) {
        selectionMenuState.copyPinyinButton.hidden = !context.pinyin;
    }
    positionSelectionMenu(context.rect);
    showSelectionMenu();
    if (context.word !== previousWord) {
        updateDictionaryPanel(context.word);
    }
}

function scheduleSelectionMenuUpdate() {
    if (selectionMenuState.timer) {
        window.clearTimeout(selectionMenuState.timer);
    }
    selectionMenuState.timer = window.setTimeout(() => {
        selectionMenuState.timer = null;
        updateSelectionMenu();
    }, 30);
}

function initSelectionMenu() {
    if (!document.body) {
        return;
    }
    const menu = document.createElement("div");
    menu.className = "selection-menu";
    const actions = document.createElement("div");
    actions.className = "selection-menu-actions";
    const copyWordButton = createSelectionMenuButton("Copy word");
    const copyPinyinButton = createSelectionMenuButton("Copy pinyin");
    const searchButton = createSelectionMenuButton("Search zdic.net");
    actions.appendChild(copyWordButton);
    actions.appendChild(copyPinyinButton);
    actions.appendChild(searchButton);
    const selectionMeta = document.createElement("div");
    selectionMeta.className = "selection-menu-meta";
    selectionMeta.hidden = true;
    const selectionMetaWord = document.createElement("div");
    selectionMetaWord.className = "selection-menu-meta-word";
    const selectionMetaDetails = document.createElement("div");
    selectionMetaDetails.className = "selection-menu-meta-details";
    selectionMeta.appendChild(selectionMetaWord);
    selectionMeta.appendChild(selectionMetaDetails);
    const dictionaryPanel = document.createElement("div");
    dictionaryPanel.className = "selection-menu-dictionary";
    dictionaryPanel.hidden = true;
    const dictionaryStatus = document.createElement("div");
    dictionaryStatus.className = "selection-menu-dictionary-status";
    dictionaryStatus.hidden = true;
    const dictionaryResults = document.createElement("div");
    dictionaryResults.className = "selection-menu-dictionary-results";
    dictionaryResults.hidden = true;
    dictionaryPanel.appendChild(dictionaryStatus);
    dictionaryPanel.appendChild(dictionaryResults);
    menu.appendChild(actions);
    menu.appendChild(selectionMeta);
    menu.appendChild(dictionaryPanel);
    document.body.appendChild(menu);
    selectionMenuState.menu = menu;
    selectionMenuState.copyWordButton = copyWordButton;
    selectionMenuState.copyPinyinButton = copyPinyinButton;
    selectionMenuState.searchButton = searchButton;
    selectionMenuState.dictionaryPanel = dictionaryPanel;
    selectionMenuState.dictionaryStatus = dictionaryStatus;
    selectionMenuState.dictionaryResults = dictionaryResults;
    selectionMenuState.selectionMeta = selectionMeta;
    selectionMenuState.selectionMetaWord = selectionMetaWord;
    selectionMenuState.selectionMetaDetails = selectionMetaDetails;

    copyWordButton.addEventListener("click", async () => {
        await copyToClipboard(selectionMenuState.word);
        hideSelectionMenu();
    });
    copyPinyinButton.addEventListener("click", async () => {
        if (!selectionMenuState.pinyin) {
            return;
        }
        await copyToClipboard(selectionMenuState.pinyin);
        hideSelectionMenu();
    });
    searchButton.addEventListener("click", () => {
        if (!selectionMenuState.word) {
            return;
        }
        const url = `https://www.zdic.net/hans/${encodeURIComponent(selectionMenuState.word)}`;
        window.open(url, "_blank", "noopener");
        hideSelectionMenu();
    });

    document.addEventListener("selectionchange", scheduleSelectionMenuUpdate);
    document.addEventListener("mouseup", scheduleSelectionMenuUpdate);
    document.addEventListener("touchend", scheduleSelectionMenuUpdate);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            hideSelectionMenu();
        }
    });
    document.addEventListener("pointerdown", (event) => {
        if (selectionMenuState.menu && !selectionMenuState.menu.contains(event.target)) {
            hideSelectionMenu();
        }
    });
    if (elements.view) {
        elements.view.addEventListener("scroll", hideSelectionMenu, { passive: true });
    }
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
const PINYIN_ALLOWED_RE = /^[a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüv\s*?'\d]+$/i;
const PINYIN_VOWEL_RE = /[aeiouüvāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]/i;

function normalizePattern(value) {
    return String(value || "")
        .replace(/？/g, "?")
        .replace(/＊/g, "*");
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
    return normalizePattern(value).toLowerCase().replace(/v/g, "ü").replace(/\s+/g, " ").trim();
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
    return String(value || "")
        .trim()
        .split(/\s+/)
        .filter(Boolean);
}

function normalizeErhuaToken(token) {
    const raw = String(token || "")
        .trim()
        .toLowerCase()
        .replace(/v/g, "ü")
        .replace(/['’]/g, "");
    if (!raw) {
        return "";
    }
    let result = "";
    for (const char of raw) {
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

function buildErhuaFlags(word, pinyinRaw) {
    const tokens = parsePinyinTokens(pinyinRaw);
    if (!tokens.length) {
        return Array.from(word).map(() => false);
    }
    const chars = Array.from(word);
    const flags = new Array(chars.length).fill(false);
    let tokenIndex = 0;
    let pendingErhua = false;

    for (let i = 0; i < chars.length; i += 1) {
        const char = chars[i];
        if (pendingErhua) {
            if (char === "儿") {
                flags[i] = true;
                pendingErhua = false;
                continue;
            }
            pendingErhua = false;
        }

        const token = tokens[tokenIndex] || "";
        if (!token) {
            continue;
        }

        if (char === "儿") {
            if (normalizeErhuaToken(token) === "r") {
                flags[i] = true;
            }
            tokenIndex += 1;
            continue;
        }

        if (isErhuaToken(token) && chars[i + 1] === "儿") {
            pendingErhua = true;
            tokenIndex += 1;
            continue;
        }

        tokenIndex += 1;
    }

    return flags;
}

function appendWordTextWithErhua(target, entry) {
    target.textContent = "";
    const chars = Array.from(entry.word);
    const flags = entry.erhuaFlags || [];
    chars.forEach((char, index) => {
        if (flags[index]) {
            const span = document.createElement("span");
            span.className = "erhua";
            span.textContent = char;
            target.appendChild(span);
        } else {
            target.appendChild(document.createTextNode(char));
        }
    });
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

function parseRankValue(value) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed) || parsed <= 1) {
        return { mode: "start" };
    }
    return { mode: "rank", value: parsed };
}

function parseOriginValue(value) {
    const normalized = normalizeOrigin(value);
    if (!normalized || normalized === "all") {
        return { mode: "all" };
    }
    return { mode: "exact", value: normalized };
}

function formatRankOptionLabel(value) {
    if (value % 1000 === 0) {
        return `${value / 1000}k`;
    }
    return formatNumber(value);
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

function formatOriginLabel(value) {
    const normalized = normalizeOrigin(value);
    if (!normalized || normalized === "all") {
        return "";
    }
    if (normalized === "佛源") {
        return "佛源";
    }
    return `Origin: ${value}`;
}

function formatRankLabel(value) {
    const parsed = parseRankValue(value);
    if (parsed.mode === "start") {
        return "";
    }
    if (parsed.value % 1000 === 0) {
        return `From ${parsed.value / 1000}k`;
    }
    return `From ${formatNumber(parsed.value)}`;
}

function updateRankOptions(proofreadCount) {
    if (!elements.rankSelect) {
        return;
    }
    const maxCount = Number.isFinite(proofreadCount) ? proofreadCount : 0;
    const values = RANK_OPTIONS.filter((value) => value <= maxCount);
    const desiredValues = ["1", ...values.map((value) => String(value))];
    let nextValue = rankState.value || "1";
    if (!desiredValues.includes(nextValue)) {
        nextValue = values.length ? String(values[values.length - 1]) : "1";
    }
    elements.rankSelect.textContent = "";
    const startOption = document.createElement("option");
    startOption.value = "1";
    startOption.textContent = "1";
    elements.rankSelect.appendChild(startOption);
    values.forEach((value) => {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = formatRankOptionLabel(value);
        elements.rankSelect.appendChild(option);
    });
    rankState.value = nextValue;
    elements.rankSelect.value = nextValue;
    syncFilterWidths();
}

function getRankStartIndex(entries, parsed) {
    if (!entries.length) {
        return 0;
    }
    if (!parsed || parsed.mode === "start") {
        return 0;
    }
    const index = entries.findIndex((entry) => entry.rankValue >= parsed.value);
    if (index === -1) {
        return Math.max(0, entries.length - renderState.chunkSize);
    }
    return index;
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

function matchesOrigin(entry, parsed) {
    if (!parsed || parsed.mode === "all") {
        return true;
    }
    const origin = entry.originValue || "";
    if (!origin) {
        return false;
    }
    const tokens = origin
        .split(/[,;|]/)
        .map((value) => value.trim())
        .filter(Boolean);
    return tokens.includes(parsed.value);
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
            (patternChars[pIndex] === "?" || patternChars[pIndex] === textChars[tIndex])
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
    const originLabel = formatOriginLabel(originState.value);
    const originText = originLabel ? ` • ${originLabel}` : "";
    const rankLabel = formatRankLabel(rankState.value);
    const rankText = rankLabel ? ` • ${rankLabel}` : "";
    const queryLabel = searchState.query ? ` • "${searchState.query}"` : "";
    setStatus(`${base} • ${label}${originText}${rankText}${queryLabel}`);
}

function updateFilterControl() {
    if (elements.lengthSelect) {
        if (elements.lengthSelect.value !== filterState.value) {
            elements.lengthSelect.value = filterState.value;
        }
    }
    if (elements.rankSelect) {
        if (elements.rankSelect.value !== rankState.value) {
            elements.rankSelect.value = rankState.value;
        }
    }
    if (elements.originSelect) {
        if (elements.originSelect.value !== originState.value) {
            elements.originSelect.value = originState.value;
        }
    }
    syncFilterWidths();
}

function applyFilters() {
    const lengthParsed = parseFilterValue(filterState.value);
    const originParsed = parseOriginValue(originState.value);
    const displayEntries = [];
    const counts = { proofread: 0, total: 0 };
    for (const entry of dataState.allEntries) {
        if (!matchesLength(entry, lengthParsed)) {
            continue;
        }
        if (!matchesOrigin(entry, originParsed)) {
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
    setChunkSize();
    updateRankOptions(counts.proofread);
    const rankParsed = parseRankValue(rankState.value);
    const startIndex = getRankStartIndex(displayEntries, rankParsed);
    const slicedEntries = displayEntries.slice(startIndex);
    dataState.filteredEntries = slicedEntries;
    dataState.matchCounts = counts;
    resetRender(slicedEntries);
    updateMeta();
    updateStatusText();
    updateFilterControl();
    updateFooterSource();
    updateLayout();
}

function applyLengthFilter(value) {
    filterState.value = value || "all";
    applyFilters();
}

function applyRankJump(value) {
    rankState.value = value || "1";
    applyFilters();
}

function applyOriginFilter(value) {
    originState.value = value || "all";
    applyFilters();
}

function initFilters() {
    if (!elements.lengthSelect && !elements.rankSelect && !elements.originSelect) {
        return;
    }
    if (elements.lengthSelect) {
        elements.lengthSelect.addEventListener("change", () => {
            applyLengthFilter(elements.lengthSelect.value);
        });
        filterState.value = elements.lengthSelect.value || "all";
    }
    if (elements.rankSelect) {
        elements.rankSelect.addEventListener("change", () => {
            applyRankJump(elements.rankSelect.value);
        });
        rankState.value = elements.rankSelect.value || "1";
    }
    if (elements.originSelect) {
        elements.originSelect.addEventListener("change", () => {
            applyOriginFilter(elements.originSelect.value);
        });
        originState.value = elements.originSelect.value || "all";
    }
    syncFilterWidths();
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
    elements.count.textContent = `Proofread: ${formatPercent(proofread, total)} (${formatNumber(
        proofread
    )} / ${formatNumber(total)})`;
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
    const end = Math.min(start + renderState.chunkSize, renderState.entries.length);
    const fragment = document.createDocumentFragment();
    for (let i = start; i < end; i += 1) {
        const entry = renderState.entries[i];
        const div = document.createElement("div");
        div.className = "word";
        div.dataset.word = entry.word;
        div.dataset.pinyin = entry.pinyin || "";
        const indexSpan = document.createElement("span");
        indexSpan.className = "word-index";
        indexSpan.textContent = entry.rank;
        const textSpan = document.createElement("span");
        textSpan.className = "word-text";
        appendWordTextWithErhua(textSpan, entry);
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
    return elements.view.scrollLeft + elements.view.clientWidth >= elements.view.scrollWidth - threshold;
}

function maybeRenderMore() {
    let safety = 0;
    while (shouldLoadMore() && renderState.rendered < renderState.entries.length && safety < 6) {
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
    const height = probe.getBoundingClientRect().height || probe.offsetHeight || 0;
    probe.remove();
    return height || 32;
}

function updateLayout() {
    const viewportHeight = document.documentElement.clientHeight || window.innerHeight;
    const visualHeight = window.visualViewport ? window.visualViewport.height : viewportHeight;
    const appHeight = Math.min(visualHeight, viewportHeight);
    document.documentElement.style.setProperty("--app-height", `${appHeight}px`);
    const headerHeight = elements.header ? elements.header.getBoundingClientRect().height : 0;
    const footerHeight = elements.footer ? elements.footer.getBoundingClientRect().height : 0;
    document.documentElement.style.setProperty("--header-height", `${headerHeight}px`);
    document.documentElement.style.setProperty("--footer-height", `${footerHeight}px`);
    const rowHeight = getRowHeight();
    const viewStyles = elements.view ? getComputedStyle(elements.view) : null;
    const paddingTop = viewStyles ? Number.parseFloat(viewStyles.paddingTop) || 0 : 0;
    const viewHeight = elements.view
        ? elements.view.getBoundingClientRect().height
        : Math.max(1, appHeight - headerHeight - footerHeight);
    const available = Math.max(1, viewHeight - paddingTop);
    const rows = Math.max(1, Math.floor(available / rowHeight));
    const nextPaddingBottom = Math.max(0, viewHeight - paddingTop - rows * rowHeight);
    if (elements.view) {
        elements.view.style.paddingBottom = `${Math.max(0, nextPaddingBottom)}px`;
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
    let originIndex = header.indexOf("origin");
    if (originIndex === -1) {
        originIndex = null;
    }

    const proofreadRanges = collectProofreadRanges(stats);
    const isProofreadRow = createRangeChecker(proofreadRanges);
    const entries = [];
    for (let i = 1; i < rows.length; i += 1) {
        const rowIndex = i;
        const word = (rows[i][wordIndex] || "").trim();
        const length = wordLength(word);
        const proofread = isProofreadRow ? isProofreadRow(rowIndex) : true;
        const rankRaw = rows[i][indexIndex];
        const rankText = rankRaw && String(rankRaw).trim() ? String(rankRaw).trim() : String(i);
        const rankValue = Number.parseInt(rankText, 10);
        const safeRankValue = Number.isFinite(rankValue) ? rankValue : i;
        const pinyinRaw = pinyinIndex !== null && pinyinIndex < rows[i].length ? rows[i][pinyinIndex] : "";
        const originRaw = originIndex !== null && originIndex < rows[i].length ? rows[i][originIndex] : "";
        const originValue = normalizeOrigin(originRaw);
        const erhuaFlags = buildErhuaFlags(word, pinyinRaw);
        entries.push({
            rank: rankText,
            rankValue: safeRankValue,
            word,
            proofread,
            length,
            pinyin: pinyinRaw,
            erhuaFlags,
            origin: originRaw,
            originValue,
            search: word.toLowerCase(),
        });
    }
    return { stats, entries };
}

async function init() {
    applyTitle();
    initFilters();
    initSearch();
    initSelectionMenu();
    updateLayout();
    if (elements.view) {
        elements.view.addEventListener("scroll", onScroll, { passive: true });
    }
    window.addEventListener("resize", () => {
        hideSelectionMenu();
        window.clearTimeout(window.__mccResizeTimer);
        window.__mccResizeTimer = window.setTimeout(updateLayout, 150);
    });
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready
            .then(() => {
                updateLayout();
                syncFilterWidths();
            })
            .catch(() => null);
    }
    try {
        const { stats, entries } = await loadWords();
        dataState.stats = stats;
        dataState.allEntries = entries;
        dataState.wordLookup = new Map(entries.map((entry) => [entry.word, entry]));
        applyFilters();
        updateLayout();
    } catch (error) {
        setStatus("Failed to load word list.", true);
        elements.count.textContent = "";
    }
}

init();
