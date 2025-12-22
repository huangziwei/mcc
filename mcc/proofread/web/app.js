(() => {
  const byId = (id) => document.getElementById(id);

  const state = {
    postDir: null,
    csvDir: null,
    metaDir: null,
    columnsDir: null,
    items: [],
    currentIndex: -1,
    tableData: [],
    columnNames: [],
    selectedRow: null,
    selectedCol: null,
    meta: null,
    config: null,
    originalCsvSerialized: "",
    originalMetaSerialized: "",
    originalPass: null,
    sessionStartedAt: "",
  };

  const elements = {
    columnSelect: byId("column-select"),
    prevBtn: byId("prev-btn"),
    nextBtn: byId("next-btn"),
    saveBtn: byId("save-btn"),
    addRowBtn: byId("add-row"),
    removeRowBtn: byId("remove-row"),
    addColBtn: byId("add-col"),
    removeColBtn: byId("remove-col"),
    shiftRange: byId("shift-range"),
    shiftStart: byId("shift-start"),
    shiftEnd: byId("shift-end"),
    shiftBy: byId("shift-by"),
    shiftMode: byId("shift-mode"),
    shiftApply: byId("shift-apply"),
    shiftTarget: byId("shift-target"),
    tableContainer: byId("table-container"),
    status: byId("status"),
    progress: byId("progress"),
    stats: byId("stats"),
    statsBtn: byId("stats-btn"),
    pathsHint: byId("paths-hint"),
    image: byId("column-image"),
    imageFrame: byId("image-frame"),
    imageEmpty: byId("image-empty"),
    zoomIn: byId("zoom-in"),
    zoomOut: byId("zoom-out"),
    fitWidth: byId("fit-width"),
    fitHeight: byId("fit-height"),
    metaLevel: byId("proofread-level"),
    metaBy: byId("proofread-by"),
    metaStarted: byId("proofread-started"),
    metaCompleted: byId("proofread-completed"),
    metaNotes: byId("proofread-notes"),
  };

  const zoomState = {
    scale: 1,
    dragging: false,
    startX: 0,
    startY: 0,
    startScrollLeft: 0,
    startScrollTop: 0,
  };

  const DEFAULT_COLUMNS = ["index", "word"];
  const STORAGE_PROOFREAD_BY = "mcc-proofread-by";

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
  }

  async function fetchText(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return response.text();
  }

  function setStatus(message, isError = false) {
    elements.status.textContent = message;
    elements.status.style.color = isError ? "#b42318" : "";
  }

  function setStatsText(message) {
    if (!elements.stats) {
      return;
    }
    elements.stats.textContent = message;
  }

  function getStoredProofreadBy() {
    try {
      return localStorage.getItem(STORAGE_PROOFREAD_BY) || "";
    } catch (error) {
      return "";
    }
  }

  function setStoredProofreadBy(value) {
    try {
      if (value) {
        localStorage.setItem(STORAGE_PROOFREAD_BY, value);
      } else {
        localStorage.removeItem(STORAGE_PROOFREAD_BY);
      }
    } catch (error) {
      // Ignore storage failures (private mode, quota, etc).
    }
  }

  function toLocalInputValue(date) {
    const pad = (value) => String(value).padStart(2, "0");
    return (
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
      `T${pad(date.getHours())}:${pad(date.getMinutes())}`
    );
  }

  function nowLocalValue() {
    return toLocalInputValue(new Date());
  }

  function normalizePassValue(meta) {
    if (!meta) {
      return "";
    }
    if (meta.proofread_pass) {
      return String(meta.proofread_pass);
    }
    const level = meta.proofread_level || "";
    const match = /(pass|level)-(\d+)/.exec(level);
    return match ? match[2] : "";
  }

  function extractPassNumber(meta) {
    const value = normalizePassValue(meta);
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function parsePassInput() {
    const raw = elements.metaLevel.value.trim();
    if (!raw) {
      return null;
    }
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return null;
    }
    return parsed;
  }

  function baseName(filename) {
    const lastDot = filename.lastIndexOf(".");
    return lastDot === -1 ? filename : filename.slice(0, lastDot);
  }

  function sortKey(name) {
    const match = /page-(\d+)-col-(\d+)/.exec(name);
    if (!match) {
      return [Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER, name];
    }
    return [parseInt(match[1], 10), parseInt(match[2], 10), name];
  }

  function compareItems(a, b) {
    const keyA = sortKey(a.base);
    const keyB = sortKey(b.base);
    for (let i = 0; i < keyA.length; i += 1) {
      if (keyA[i] < keyB[i]) return -1;
      if (keyA[i] > keyB[i]) return 1;
    }
    return 0;
  }

  async function fetchConfig() {
    try {
      const response = await fetch("config.json", { cache: "no-store" });
      if (!response.ok) {
        return;
      }
      state.config = await response.json();
    } catch (error) {
      setStatus("Unable to load config.json", true);
    }
  }

  function updatePathsHint() {
    if (!elements.pathsHint) {
      return;
    }
    const post = (state.config && state.config.default_post_dir) || "post";
    const csv = (state.config && state.config.default_csv_dir) || `${post}/csv`;
    const meta = (state.config && state.config.default_meta_dir) || `${post}/meta`;
    const columns = (state.config && state.config.default_columns_dir) || "pre/columns";
    elements.pathsHint.textContent = `Paths: ${csv}, ${meta}, ${columns}`;
  }

  function setServerPathsFromConfig() {
    const post = (state.config && state.config.default_post_dir) || "post";
    state.postDir = post;
    state.csvDir = (state.config && state.config.default_csv_dir) || `${post}/csv`;
    state.metaDir = (state.config && state.config.default_meta_dir) || `${post}/meta`;
    state.columnsDir = (state.config && state.config.default_columns_dir) || "pre/columns";
  }

  function initializeMode() {
    setServerPathsFromConfig();
    updatePathsHint();
  }

  async function listFilesServer(dirPath, extensions) {
    const extParam = extensions
      .map((ext) => ext.replace(".", "").toLowerCase())
      .filter((ext) => ext.length > 0)
      .join(",");
    const params = new URLSearchParams({ dir: dirPath });
    if (extParam) {
      params.set("ext", extParam);
    }
    const data = await fetchJson(`/api/list?${params.toString()}`);
    return data.files || [];
  }

  async function writeServer(path, body, contentType) {
    const response = await fetch(`/api/write?path=${encodeURIComponent(path)}`, {
      method: "POST",
      headers: { "Content-Type": contentType },
      body,
    });
    if (!response.ok) {
      throw new Error(`Write failed: ${response.status}`);
    }
  }

  async function updateReadmeStats() {
    if (!state.config || !state.config.readme_stats_path) {
      return true;
    }
    try {
      await fetchJson("/api/readme-stats", { method: "POST" });
      return true;
    } catch (error) {
      return false;
    }
  }

  async function refreshItems() {
    await refreshItemsServer();
  }

  async function refreshItemsServer() {
    if (!state.csvDir || !state.columnsDir) {
      return;
    }
    let csvFiles = [];
    let imageFiles = [];
    try {
      setStatus("Loading file list...");
      csvFiles = await listFilesServer(state.csvDir, [".csv"]);
      imageFiles = await listFilesServer(state.columnsDir, [".png", ".jpg", ".jpeg"]);
    } catch (error) {
      setStatus("Unable to list files from server.", true);
      return;
    }
    const imageMap = new Map(
      imageFiles.map((name) => [baseName(name), name])
    );
    state.items = csvFiles.map((name) => ({
      base: baseName(name),
      csvPath: `${state.csvDir}/${name}`,
      imagePath: imageMap.get(baseName(name))
        ? `${state.columnsDir}/${imageMap.get(baseName(name))}`
        : null,
      meta: null,
    }));

    state.items.sort(compareItems);

    if (state.items.length === 0) {
      setStatus("No CSV files found in post/csv.", true);
      elements.columnSelect.innerHTML = "";
      elements.progress.textContent = "";
      setStatsText("Stats: no items");
      return;
    }
    renderColumnSelect();
    const startIndex = await findFirstUnproofreadIndex();
    await loadItem(startIndex);
  }

  async function findFirstUnproofreadIndex() {
    if (!state.metaDir || state.items.length === 0) {
      return 0;
    }
    let metaFiles = [];
    try {
      metaFiles = await listFilesServer(state.metaDir, [".json"]);
    } catch (error) {
      return 0;
    }
    const metaSet = new Set(metaFiles.map((name) => baseName(name)));
    const missingIndex = state.items.findIndex((item) => !metaSet.has(item.base));
    if (missingIndex !== -1) {
      return missingIndex;
    }
    setStatus("Scanning for next unproofread...");
    for (let i = 0; i < state.items.length; i += 1) {
      const item = state.items[i];
      if (!item.meta) {
        item.meta = await readMetadata(item.base);
      }
      if (!extractPassNumber(item.meta)) {
        return i;
      }
      if (i === 0 || (i + 1) % 25 === 0 || i + 1 === state.items.length) {
        setStatus(`Scanning for next unproofread ${i + 1}/${state.items.length}`);
      }
    }
    return 0;
  }

  async function computeStats() {
    if (!state.metaDir || state.items.length === 0) {
      setStatsText("Stats: no items");
      return;
    }
    const statsBtn = elements.statsBtn;
    if (statsBtn) {
      statsBtn.disabled = true;
    }
    setStatsText("Stats: loading...");
    try {
      let metaFiles = [];
      try {
        metaFiles = await listFilesServer(state.metaDir, [".json"]);
      } catch (error) {
        setStatsText("Stats: failed to list metadata.");
        return;
      }
      const metaSet = new Set(metaFiles.map((name) => baseName(name)));
      let proofread = 0;
      let unproofread = 0;
      const passCounts = new Map();
      for (let i = 0; i < state.items.length; i += 1) {
        const item = state.items[i];
        if (!metaSet.has(item.base)) {
          unproofread += 1;
        } else {
          let meta = item.meta;
          if (!meta) {
            meta = await readMetadata(item.base);
            item.meta = meta;
          }
          const pass = extractPassNumber(meta);
          if (!pass) {
            unproofread += 1;
          } else {
            proofread += 1;
            passCounts.set(pass, (passCounts.get(pass) || 0) + 1);
          }
        }
        if (i === 0 || (i + 1) % 25 === 0 || i + 1 === state.items.length) {
          setStatsText(`Stats: scanning ${i + 1}/${state.items.length}...`);
        }
      }
      const total = state.items.length;
      const passEntries = Array.from(passCounts.entries()).sort((a, b) => a[0] - b[0]);
      let statsText = `Stats: ${proofread} proofread, ${unproofread} unproofread (${total} total)`;
      const maxPass = passEntries.length ? passEntries[passEntries.length - 1][0] : 0;
      if (maxPass > 1) {
        const passText = passEntries
          .map(([pass, count]) => `pass ${pass}: ${count}`)
          .join(", ");
        statsText += ` | ${passText}`;
      }
      setStatsText(statsText);
      renderColumnSelect();
    } finally {
      if (statsBtn) {
        statsBtn.disabled = false;
      }
    }
  }

  async function readMetadata(base) {
    if (!state.metaDir) {
      return null;
    }
    const path = `${state.metaDir}/${base}.json`;
    try {
      const text = await fetchText(`/api/read?path=${encodeURIComponent(path)}`);
      return JSON.parse(text);
    } catch (error) {
      return null;
    }
  }

  function renderColumnSelect() {
    elements.columnSelect.innerHTML = "";
    state.items.forEach((item, index) => {
      const option = document.createElement("option");
      const pass = extractPassNumber(item.meta);
      const level = pass ? ` [pass ${pass}]` : "";
      option.value = String(index);
      option.textContent = `${item.base}${level}`;
      elements.columnSelect.appendChild(option);
    });
    if (state.currentIndex >= 0) {
      elements.columnSelect.value = String(state.currentIndex);
    }
  }

  function updateProgress() {
    if (state.items.length === 0 || state.currentIndex < 0) {
      elements.progress.textContent = "";
      return;
    }
    elements.progress.textContent = `${state.currentIndex + 1} / ${state.items.length}`;
  }

  async function loadItem(index) {
    if (index < 0 || index >= state.items.length) {
      return;
    }
    state.currentIndex = index;
    state.selectedRow = null;
    state.selectedCol = null;
    const item = state.items[index];
    setStatus(`Loading ${item.base}...`);
    let text = "";
    try {
      text = await fetchText(`/api/read?path=${encodeURIComponent(item.csvPath)}`);
    } catch (error) {
      setStatus("Failed to read CSV from server.", true);
      return;
    }
    state.tableData = parseCsv(text);
    const meta = item.meta || (await readMetadata(item.base)) || {};
    item.meta = meta;
    state.meta = meta;
    state.originalCsvSerialized = serializeCsv(state.tableData);
    state.originalMetaSerialized = JSON.stringify(meta, null, 2);
    state.originalPass = extractPassNumber(meta);
    state.sessionStartedAt = nowLocalValue();
    setupColumns(meta.columns);
    setDefaultShiftColumn();
    renderTable();
    renderMetadata();
    await loadImage(item);
    elements.tableContainer.scrollTop = 0;
    renderColumnSelect();
    updateProgress();
    setStatus(`Loaded ${item.base}`);
  }

  async function navigateTo(index) {
    if (index < 0 || index >= state.items.length) {
      return;
    }
    if (state.currentIndex >= 0 && parsePassInput()) {
      const saved = await saveCurrent();
      if (!saved) {
        return;
      }
    }
    await loadItem(index);
  }

  function setupColumns(savedColumns) {
    const maxCols = Math.max(
      savedColumns ? savedColumns.length : 0,
      ...state.tableData.map((row) => row.length),
      DEFAULT_COLUMNS.length
    );
    state.tableData = state.tableData.map((row) => {
      const next = row.slice(0);
      while (next.length < maxCols) {
        next.push("");
      }
      return next;
    });
    state.columnNames = [];
    for (let i = 0; i < maxCols; i += 1) {
      if (savedColumns && savedColumns[i]) {
        state.columnNames.push(savedColumns[i]);
      } else if (DEFAULT_COLUMNS[i]) {
        state.columnNames.push(DEFAULT_COLUMNS[i]);
      } else {
        state.columnNames.push(`col-${i + 1}`);
      }
    }
  }

  function renderTable() {
    elements.tableContainer.innerHTML = "";
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    const corner = document.createElement("th");
    corner.textContent = "#";
    headRow.appendChild(corner);

    state.columnNames.forEach((name, colIndex) => {
      const th = document.createElement("th");
      const input = document.createElement("input");
      input.value = name;
      input.dataset.col = String(colIndex);
      input.addEventListener("input", (event) => {
        const target = event.target;
        const idx = Number(target.dataset.col);
        state.columnNames[idx] = target.value;
        if (idx === state.selectedCol) {
          updateShiftTarget();
        }
      });
      input.addEventListener("focus", () => {
        state.selectedCol = colIndex;
        state.selectedRow = null;
        highlightSelection();
      });
      th.appendChild(input);
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    state.tableData.forEach((row, rowIndex) => {
      const tr = document.createElement("tr");
      const rowHeader = document.createElement("th");
      rowHeader.textContent = String(rowIndex + 1);
      rowHeader.addEventListener("click", () => {
        state.selectedRow = rowIndex;
        state.selectedCol = null;
        highlightSelection();
      });
      tr.appendChild(rowHeader);

      row.forEach((cell, colIndex) => {
        const td = document.createElement("td");
        if (rowIndex === state.selectedRow && colIndex === state.selectedCol) {
          td.classList.add("selected");
        }
        const input = document.createElement("input");
        input.value = cell;
        input.dataset.row = String(rowIndex);
        input.dataset.col = String(colIndex);
        input.addEventListener("input", (event) => {
          const target = event.target;
          const r = Number(target.dataset.row);
          const c = Number(target.dataset.col);
          state.tableData[r][c] = target.value;
        });
        input.addEventListener("focus", () => {
          state.selectedRow = rowIndex;
          state.selectedCol = colIndex;
          highlightSelection();
        });
        input.addEventListener("keydown", (event) => {
          if (
            event.key !== "Enter" &&
            event.key !== "ArrowUp" &&
            event.key !== "ArrowDown"
          ) {
            return;
          }
          if (
            event.altKey ||
            event.ctrlKey ||
            event.metaKey ||
            event.shiftKey ||
            event.isComposing
          ) {
            return;
          }
          const direction = event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 1;
          event.preventDefault();
          const nextRow = rowIndex + direction;
          if (nextRow < 0 || nextRow >= state.tableData.length) {
            return;
          }
          focusCell(nextRow, colIndex);
        });
        td.appendChild(input);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    elements.tableContainer.appendChild(table);
    updateShiftTarget();
  }

  function highlightSelection() {
    const cells = elements.tableContainer.querySelectorAll("td");
    cells.forEach((cell) => cell.classList.remove("selected"));
    updateShiftTarget();
    if (state.selectedRow === null || state.selectedCol === null) {
      return;
    }
    const selector = `input[data-row='${state.selectedRow}'][data-col='${state.selectedCol}']`;
    const input = elements.tableContainer.querySelector(selector);
    if (input && input.parentElement) {
      input.parentElement.classList.add("selected");
    }
  }

  function focusCell(rowIndex, colIndex) {
    const selector = `input[data-row='${rowIndex}'][data-col='${colIndex}']`;
    const input = elements.tableContainer.querySelector(selector);
    if (input) {
      input.focus();
    }
  }

  function updateShiftTarget() {
    if (!elements.shiftTarget) {
      return;
    }
    if (state.selectedCol === null) {
      elements.shiftTarget.textContent = "Target: select a column";
      return;
    }
    const name =
      state.columnNames[state.selectedCol] || `col-${state.selectedCol + 1}`;
    elements.shiftTarget.textContent = `Target: ${name}`;
  }

  function parseIntegerInput(value) {
    const text = value.trim();
    if (!text) {
      return null;
    }
    const parsed = Number.parseInt(text, 10);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function normalizeColumnName(name) {
    return String(name || "").trim().toLowerCase();
  }

  function findColumnIndexByName(name) {
    const target = normalizeColumnName(name);
    for (let i = 0; i < state.columnNames.length; i += 1) {
      if (normalizeColumnName(state.columnNames[i]) === target) {
        return i;
      }
    }
    return null;
  }

  function setDefaultShiftColumn() {
    if (
      state.selectedCol !== null &&
      state.selectedCol >= 0 &&
      state.selectedCol < state.columnNames.length
    ) {
      updateShiftTarget();
      return;
    }
    const indexCol = findColumnIndexByName("index");
    if (indexCol !== null) {
      state.selectedCol = indexCol;
      updateShiftTarget();
      return;
    }
    if (state.columnNames.length > 0) {
      state.selectedCol = 0;
      updateShiftTarget();
    }
  }

  function ensureShiftColumn() {
    if (state.selectedCol !== null) {
      return state.selectedCol;
    }
    const indexCol = findColumnIndexByName("index");
    if (indexCol !== null) {
      state.selectedCol = indexCol;
      updateShiftTarget();
      return indexCol;
    }
    if (state.columnNames.length > 0) {
      state.selectedCol = 0;
      updateShiftTarget();
      return 0;
    }
    return null;
  }

  function findRowByColumnValue(colIndex, value, fromEnd = false) {
    const target = String(value).trim();
    if (!target) {
      return null;
    }
    const start = fromEnd ? state.tableData.length - 1 : 0;
    const end = fromEnd ? -1 : state.tableData.length;
    const step = fromEnd ? -1 : 1;
    for (let i = start; i !== end; i += step) {
      const row = state.tableData[i];
      if (!row) {
        continue;
      }
      const cell = row[colIndex];
      if (cell === null || cell === undefined) {
        continue;
      }
      if (String(cell).trim() === target) {
        return i;
      }
    }
    return null;
  }

  function shiftColumnCells(colIndex, startRow, endRow, delta) {
    const length = endRow - startRow + 1;
    const shifted = new Array(length).fill("");
    let moved = 0;
    for (let i = 0; i < length; i += 1) {
      const nextIndex = i + delta;
      if (nextIndex < 0 || nextIndex >= length) {
        continue;
      }
      const value = state.tableData[startRow + i][colIndex] ?? "";
      if (value !== "") {
        moved += 1;
      }
      shifted[nextIndex] = value;
    }
    for (let i = 0; i < length; i += 1) {
      state.tableData[startRow + i][colIndex] = shifted[i];
    }
    return moved;
  }

  function offsetColumnNumbers(colIndex, startRow, endRow, delta) {
    let updated = 0;
    for (let row = startRow; row <= endRow; row += 1) {
      const raw = state.tableData[row][colIndex];
      const text = raw === null || raw === undefined ? "" : String(raw).trim();
      if (!/^-?\d+$/.test(text)) {
        continue;
      }
      const next = Number.parseInt(text, 10) + delta;
      state.tableData[row][colIndex] = String(next);
      updated += 1;
    }
    return updated;
  }

  function applyShift() {
    if (state.tableData.length === 0) {
      setStatus("No rows to shift.", true);
      return;
    }
    const targetCol = ensureShiftColumn();
    if (targetCol === null) {
      setStatus("No columns available to shift.", true);
      return;
    }
    const delta = parseIntegerInput(elements.shiftBy.value);
    if (delta === null || delta === 0) {
      setStatus("Shift value must be a non-zero number.", true);
      return;
    }
    const rowCount = state.tableData.length;
    const startInput = parseIntegerInput(elements.shiftStart.value);
    const endInput = parseIntegerInput(elements.shiftEnd.value);
    const rangeMode = elements.shiftRange ? elements.shiftRange.value : "row";
    let startRow = null;
    let endRow = null;
    let rangeLabel = "";
    let start = null;
    let end = null;
    if (rangeMode === "index" && (startInput !== null || endInput !== null)) {
      const indexCol = findColumnIndexByName("index");
      if (indexCol === null) {
        setStatus('Index column not found for "Index values" range.', true);
        return;
      }
      startRow =
        startInput === null
          ? 0
          : findRowByColumnValue(indexCol, startInput, false);
      endRow =
        endInput === null
          ? rowCount - 1
          : findRowByColumnValue(indexCol, endInput, true);
      if (startInput !== null && startRow === null) {
        setStatus(`Index value ${startInput} not found.`, true);
        return;
      }
      if (endInput !== null && endRow === null) {
        setStatus(`Index value ${endInput} not found.`, true);
        return;
      }
      if (startRow > endRow) {
        [startRow, endRow] = [endRow, startRow];
      }
      const startLabel =
        startInput !== null ? startInput : state.tableData[startRow][indexCol];
      const endLabel =
        endInput !== null ? endInput : state.tableData[endRow][indexCol];
      rangeLabel = `index ${startLabel}-${endLabel}`;
      start = startRow + 1;
      end = endRow + 1;
    } else {
      if (
        rangeMode === "row" &&
        ((startInput !== null && startInput > rowCount) ||
          (endInput !== null && endInput > rowCount)) &&
        findColumnIndexByName("index") !== null
      ) {
        setStatus(
          `Row range exceeds ${rowCount}. If you meant index values, switch Range to "Index values".`,
          true
        );
        return;
      }
      start = startInput;
      end = endInput;
      if (start === null && end === null) {
        if (state.selectedRow !== null) {
          start = state.selectedRow + 1;
          end = state.selectedRow + 1;
        } else {
          start = 1;
          end = rowCount;
        }
      } else {
        if (start === null) {
          start = 1;
        }
        if (end === null) {
          end = rowCount;
        }
      }
      start = Math.min(Math.max(start, 1), rowCount);
      end = Math.min(Math.max(end, 1), rowCount);
      if (start > end) {
        [start, end] = [end, start];
      }
      startRow = start - 1;
      endRow = end - 1;
      rangeLabel = `rows ${start}-${end}`;
    }
    const colName =
      state.columnNames[targetCol] || `col-${targetCol + 1}`;
    if (elements.shiftMode.value === "offset") {
      const updated = offsetColumnNumbers(targetCol, startRow, endRow, delta);
      renderTable();
      setStatus(
        `Offset ${updated} value(s) in "${colName}" ${rangeLabel} by ${delta}.`
      );
      return;
    }
    const moved = shiftColumnCells(targetCol, startRow, endRow, delta);
    renderTable();
    setStatus(
      `Shifted ${moved} value(s) in "${colName}" ${rangeLabel} by ${delta}.`
    );
  }

  function addRow() {
    const insertAt = state.selectedRow !== null ? state.selectedRow + 1 : state.tableData.length;
    const newRow = new Array(state.columnNames.length).fill("");
    state.tableData.splice(insertAt, 0, newRow);
    state.selectedRow = insertAt;
    renderTable();
  }

  function removeRow() {
    if (state.tableData.length === 0) {
      return;
    }
    const removeAt = state.selectedRow !== null ? state.selectedRow : state.tableData.length - 1;
    state.tableData.splice(removeAt, 1);
    state.selectedRow = null;
    renderTable();
  }

  function addColumn() {
    const insertAt = state.selectedCol !== null ? state.selectedCol + 1 : state.columnNames.length;
    state.columnNames.splice(insertAt, 0, `col-${state.columnNames.length + 1}`);
    state.tableData.forEach((row) => row.splice(insertAt, 0, ""));
    state.selectedCol = insertAt;
    renderTable();
  }

  function removeColumn() {
    if (state.columnNames.length <= 1) {
      return;
    }
    const removeAt = state.selectedCol !== null ? state.selectedCol : state.columnNames.length - 1;
    state.columnNames.splice(removeAt, 1);
    state.tableData.forEach((row) => row.splice(removeAt, 1));
    state.selectedCol = null;
    renderTable();
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
      } else {
        if (char === '"') {
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
    }
    row.push(cell);
    if (row.length > 1 || row[0] !== "") {
      rows.push(row);
    }
    return rows;
  }

  function escapeCell(value) {
    if (value === null || value === undefined) {
      return "";
    }
    const text = String(value);
    if (/[",\n\r]/.test(text)) {
      return '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
  }

  function serializeCsv(rows) {
    return rows
      .map((row) => row.map((cell) => escapeCell(cell)).join(","))
      .join("\n");
  }

  async function saveCurrent() {
    if (state.currentIndex < 0) {
      setStatus("No CSV loaded.", true);
      return false;
    }
    const item = state.items[state.currentIndex];
    const currentCsvSerialized = serializeCsv(state.tableData);
    const csvChanged = currentCsvSerialized !== state.originalCsvSerialized;
    const passInput = parsePassInput();
    let pass = passInput;
    if (csvChanged && !pass) {
      const base = state.originalPass || 0;
      pass = base + 1;
      elements.metaLevel.value = String(pass);
    }
    const startedAt = csvChanged
      ? state.sessionStartedAt || nowLocalValue()
      : state.meta?.proofread_started_at || null;
    const completedAt = csvChanged
      ? nowLocalValue()
      : state.meta?.proofread_completed_at || null;
    const metadata = buildMetadata(item, { pass, startedAt, completedAt });
    const metadataSerialized = JSON.stringify(metadata, null, 2);
    const metadataChanged = metadataSerialized !== state.originalMetaSerialized;
    const didSave = csvChanged || metadataChanged;
    if (!didSave) {
      setStatus(`No changes to save for ${item.base}`);
      return true;
    }
    if (!state.csvDir || !state.metaDir) {
      setStatus("Server paths are not configured.", true);
      return false;
    }
    try {
      if (csvChanged) {
        await writeServer(
          `${state.csvDir}/${item.base}.csv`,
          currentCsvSerialized,
          "text/csv; charset=utf-8"
        );
      }
      if (metadataChanged) {
        await writeServer(
          `${state.metaDir}/${item.base}.json`,
          metadataSerialized,
          "application/json"
        );
      }
    } catch (error) {
      setStatus("Failed to save via server.", true);
      return false;
    }
    item.meta = metadata;
    state.meta = metadata;
    state.originalCsvSerialized = currentCsvSerialized;
    state.originalMetaSerialized = metadataSerialized;
    state.originalPass = metadata.proofread_pass ?? null;
    if (csvChanged) {
      elements.metaStarted.value = startedAt || "";
      elements.metaCompleted.value = completedAt || "";
    }
    renderColumnSelect();
    updateProgress();
    const readmeUpdated = await updateReadmeStats();
    if (!readmeUpdated) {
      setStatus(`Saved ${item.base} (README update failed)`, true);
      return true;
    }
    setStatus(`Saved ${item.base}`);
    return true;
  }

  function buildMetadata(item, overrides = {}) {
    const pass = overrides.pass ?? parsePassInput();
    const startedAt = overrides.startedAt ?? state.meta?.proofread_started_at ?? null;
    const completedAt =
      overrides.completedAt ?? state.meta?.proofread_completed_at ?? null;
    const imageName = item.imagePath ? item.imagePath.split("/").pop() : null;
    return {
      source_csv: `${item.base}.csv`,
      source_image: imageName,
      proofread_pass: pass,
      proofread_level: pass ? `pass-${pass}` : null,
      proofread_by: elements.metaBy.value || null,
      proofread_started_at: startedAt || null,
      proofread_completed_at: completedAt || null,
      notes: elements.metaNotes.value || null,
      columns: state.columnNames.slice(0),
    };
  }

  function renderMetadata() {
    const meta = state.meta || {};
    elements.metaLevel.value = normalizePassValue(meta);
    elements.metaBy.value = meta.proofread_by || getStoredProofreadBy();
    elements.metaStarted.value = meta.proofread_started_at || "";
    elements.metaCompleted.value = meta.proofread_completed_at || "";
    elements.metaNotes.value = meta.notes || "";
  }


  async function loadImage(item) {
    if (!item.imagePath) {
      elements.image.src = "";
      elements.imageEmpty.style.display = "block";
      return;
    }
    elements.image.src = `/api/file?path=${encodeURIComponent(item.imagePath)}`;
    elements.imageEmpty.style.display = "none";
    resetZoom();
  }

  function frameContentSize() {
    const style = window.getComputedStyle(elements.imageFrame);
    const paddingX =
      parseFloat(style.paddingLeft || "0") + parseFloat(style.paddingRight || "0");
    const paddingY =
      parseFloat(style.paddingTop || "0") + parseFloat(style.paddingBottom || "0");
    return {
      width: Math.max(0, elements.imageFrame.clientWidth - paddingX),
      height: Math.max(0, elements.imageFrame.clientHeight - paddingY),
    };
  }

  function applyScale() {
    const img = elements.image;
    if (!img.naturalWidth || !img.naturalHeight) {
      return;
    }
    img.style.width = `${img.naturalWidth * zoomState.scale}px`;
    img.style.height = `${img.naturalHeight * zoomState.scale}px`;
  }

  function resetZoom() {
    zoomState.scale = 1;
    applyScale();
    elements.imageFrame.scrollLeft = 0;
    elements.imageFrame.scrollTop = 0;
  }

  function zoomBy(factor, anchor) {
    const img = elements.image;
    if (!img.naturalWidth || !img.naturalHeight) {
      return;
    }
    const prevScale = zoomState.scale;
    const nextScale = Math.max(0.1, Math.min(prevScale * factor, 8));
    if (nextScale === prevScale) {
      return;
    }
    zoomState.scale = nextScale;
    applyScale();
    if (anchor) {
      const frame = elements.imageFrame.getBoundingClientRect();
      const anchorX = anchor.clientX - frame.left + elements.imageFrame.scrollLeft;
      const anchorY = anchor.clientY - frame.top + elements.imageFrame.scrollTop;
      const scaleRatio = nextScale / prevScale;
      elements.imageFrame.scrollLeft = anchorX * scaleRatio - (anchor.clientX - frame.left);
      elements.imageFrame.scrollTop = anchorY * scaleRatio - (anchor.clientY - frame.top);
    }
  }

  function fitToWidth() {
    const img = elements.image;
    if (!img.naturalWidth) {
      return;
    }
    const frame = frameContentSize();
    zoomState.scale = frame.width / img.naturalWidth;
    applyScale();
    elements.imageFrame.scrollLeft = 0;
    elements.imageFrame.scrollTop = 0;
  }

  function fitToHeight() {
    const img = elements.image;
    if (!img.naturalHeight) {
      return;
    }
    const tableRect = elements.tableContainer.getBoundingClientRect();
    const frame = frameContentSize();
    const targetHeight = tableRect.height || frame.height;
    zoomState.scale = targetHeight / img.naturalHeight;
    applyScale();
    elements.imageFrame.scrollLeft = 0;
    elements.imageFrame.scrollTop = 0;
  }

  function onPointerDown(event) {
    if (!elements.image.src) {
      return;
    }
    zoomState.dragging = true;
    zoomState.startX = event.clientX;
    zoomState.startY = event.clientY;
    zoomState.startScrollLeft = elements.imageFrame.scrollLeft;
    zoomState.startScrollTop = elements.imageFrame.scrollTop;
    elements.imageFrame.classList.add("dragging");
  }

  function onPointerMove(event) {
    if (!zoomState.dragging) {
      return;
    }
    const deltaX = event.clientX - zoomState.startX;
    const deltaY = event.clientY - zoomState.startY;
    elements.imageFrame.scrollLeft = zoomState.startScrollLeft - deltaX;
    elements.imageFrame.scrollTop = zoomState.startScrollTop - deltaY;
  }

  function onPointerUp() {
    zoomState.dragging = false;
    elements.imageFrame.classList.remove("dragging");
  }

  function onGlobalKeydown(event) {
    if (event.isComposing || event.repeat) {
      return;
    }
    if (!event.metaKey && !event.ctrlKey) {
      return;
    }
    if (event.altKey) {
      return;
    }
    const key = event.key.toLowerCase();
    const code = event.code;
    const isPrev = key === "j" || code === "KeyJ";
    const isNext = key === "k" || code === "KeyK";
    if (isPrev || isNext) {
      event.preventDefault();
      event.stopPropagation();
      const direction = isPrev ? -1 : 1;
      navigateTo(state.currentIndex + direction);
      return;
    }
    if (key !== "s") {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    saveCurrent();
  }

  function bindEvents() {
    elements.columnSelect.addEventListener("change", (event) => {
      const index = Number(event.target.value);
      navigateTo(index);
    });
    elements.prevBtn.addEventListener("click", () => navigateTo(state.currentIndex - 1));
    elements.nextBtn.addEventListener("click", () => navigateTo(state.currentIndex + 1));
    elements.saveBtn.addEventListener("click", () => saveCurrent());
    if (elements.statsBtn) {
      elements.statsBtn.addEventListener("click", () => computeStats());
    }
    elements.addRowBtn.addEventListener("click", addRow);
    elements.removeRowBtn.addEventListener("click", removeRow);
    elements.addColBtn.addEventListener("click", addColumn);
    elements.removeColBtn.addEventListener("click", removeColumn);
    elements.shiftApply.addEventListener("click", applyShift);
    elements.zoomIn.addEventListener("click", () => zoomBy(1.1));
    elements.zoomOut.addEventListener("click", () => zoomBy(0.9));
    elements.fitWidth.addEventListener("click", fitToWidth);
    elements.fitHeight.addEventListener("click", fitToHeight);
    elements.imageFrame.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("keydown", onGlobalKeydown);
    elements.image.addEventListener("load", fitToWidth);
    elements.metaBy.addEventListener("input", () => {
      setStoredProofreadBy(elements.metaBy.value.trim());
    });
  }

  async function init() {
    await fetchConfig();
    initializeMode();
    bindEvents();
    await refreshItems();
  }

  init();
})();
