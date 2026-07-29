const $ = (selector) => document.querySelector(selector);
const ui = {
  applyIdentical: $('#apply-identical'),
  boardCard: $('#board-card'),
  boardImage: $('#board-image'),
  boardIndex: $('#board-index'),
  boardStatus: $('#board-status'),
  boardsComplete: $('#boards-complete'),
  boardsPending: $('#boards-pending'),
  cellGrid: $('#cell-grid'),
  cellsComplete: $('#cells-complete'),
  cellsTotal: $('#cells-total'),
  clear: $('#clear'),
  clearJump: $('#clear-jump'),
  empty: $('#empty'),
  error: $('#error'),
  filter: $('#filter'),
  gameCode: $('#game-code'),
  jumpForm: $('#jump-form'),
  loading: $('#loading'),
  next: $('#next'),
  perSymbol: $('#per-symbol'),
  position: $('#position'),
  previous: $('#previous'),
  previousLabel: $('#previous-label'),
  profileVersion: $('#profile-version'),
  reject: $('#reject'),
  reviewPanel: $('#review-panel'),
  reviewedBy: $('#reviewed-by'),
  selectedCell: $('#selected-cell'),
  sequenceJump: $('#sequence-jump'),
  sequenceNumber: $('#sequence-number'),
  setupForm: $('#setup-form'),
  setupPanel: $('#setup-panel'),
  sourceGroup: $('#source-group'),
  suggestionButtons: $('#suggestion-buttons'),
  suggestionStatus: $('#suggestion-status'),
  symbolButtons: $('#symbol-buttons'),
  symbolCodes: $('#symbol-codes'),
};

const state = {
  board: null,
  busy: false,
  offset: 0,
  selectedSampleId: null,
  sequenceNumber: '',
  symbols: [],
  token: '',
  totalFiltered: 0,
};

function showError(message = '') {
  ui.error.textContent = message;
  ui.error.hidden = !message;
}

function setBusy(value) {
  state.busy = value;
  document
    .querySelectorAll('button, input, select, textarea')
    .forEach((node) => {
      node.disabled = value;
    });
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(state.token ? { 'X-Review-Token': state.token } : {}),
      ...options.headers,
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok)
    throw new Error(payload?.message || `Błąd HTTP ${response.status}.`);
  return payload;
}

function updateProgress(progress) {
  const completedBoards = progress.boards.accepted + progress.boards.rejected;
  const completedCells = progress.cells.accepted + progress.cells.rejected;
  ui.boardsPending.textContent =
    progress.boards.pending.toLocaleString('pl-PL');
  ui.boardsComplete.textContent = `${completedBoards} / ${progress.boards.total}`;
  ui.cellsComplete.textContent = completedCells.toLocaleString('pl-PL');
  ui.cellsTotal.textContent = progress.cells.total.toLocaleString('pl-PL');
  ui.perSymbol.replaceChildren();
  progress.cells.perSymbol.forEach((item) => {
    const row = document.createElement('div');
    row.innerHTML = `<span>${item.symbolCode}</span><strong>${item.sampleCount}</strong>`;
    ui.perSymbol.append(row);
  });
}

function selectCell(sampleId) {
  state.selectedSampleId = sampleId;
  const cell = state.board?.cells.find((item) => item.sampleId === sampleId);
  ui.selectedCell.textContent = cell
    ? `Rząd ${cell.rowIndex + 1}, kolumna ${cell.columnIndex + 1}`
    : 'Kliknij komórkę';
  document.querySelectorAll('.cell-card').forEach((node) => {
    node.classList.toggle('active', node.dataset.sampleId === sampleId);
  });
  renderSymbols();
  renderSuggestions(cell);
}

function renderSuggestions(cell) {
  ui.suggestionButtons.replaceChildren();
  ui.previousLabel.hidden = true;
  ui.previousLabel.textContent = '';
  if (!cell) {
    ui.suggestionStatus.textContent = 'Wybierz komórkę';
    return;
  }
  if (cell.previousGeometryLabel) {
    ui.previousLabel.textContent = `Poprzednia geometria: ${cell.previousGeometryLabel.symbolCode}`;
    ui.previousLabel.hidden = false;
  }
  const suggestions = cell.suggestions || [];
  if (!suggestions.length) {
    ui.suggestionStatus.textContent = 'Brak bezpiecznej sugestii';
    return;
  }
  ui.suggestionStatus.textContent = `Próg podobieństwa ${(
    cell.suggestionEvidence.minimumCosineSimilarity * 100
  ).toFixed(1)}%`;
  const shortcuts = ['Q', 'W', 'E'];
  suggestions.forEach((suggestion, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'suggestion';
    button.innerHTML = `<strong>${shortcuts[index]} · ${suggestion.symbolCode}</strong>
      <small>podobieństwo ${(suggestion.cosineSimilarity * 100).toFixed(1)}% · model ${Math.round(suggestion.classifierConfidence * 100)}%</small>`;
    button.addEventListener('click', () =>
      decide('accepted', suggestion.symbolCode),
    );
    ui.suggestionButtons.append(button);
  });
}

function renderSymbols() {
  ui.symbolButtons.replaceChildren();
  const selected = state.board?.cells.find(
    (cell) => cell.sampleId === state.selectedSampleId,
  );
  state.symbols.forEach((symbol, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = `${index < 9 ? `${index + 1} · ` : ''}${symbol.symbolCode}`;
    button.classList.toggle(
      'selected',
      selected?.decision === 'accepted' &&
        selected.symbolCode === symbol.symbolCode,
    );
    button.addEventListener('click', () =>
      decide('accepted', symbol.symbolCode),
    );
    ui.symbolButtons.append(button);
  });
}

function renderCells(cells) {
  ui.cellGrid.replaceChildren();
  cells.forEach((cell) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `cell-card ${cell.decision}`;
    button.dataset.sampleId = cell.sampleId;
    const image = document.createElement('img');
    image.src = `${cell.cropUrl}?v=${cell.cropChecksumSha256}`;
    image.alt = `Rząd ${cell.rowIndex + 1}, kolumna ${cell.columnIndex + 1}`;
    const badge = document.createElement('span');
    badge.textContent =
      cell.decision === 'accepted'
        ? cell.symbolCode
        : cell.decision === 'rejected'
          ? 'Odrzucono'
          : `${cell.rowIndex + 1}:${cell.columnIndex + 1}`;
    button.append(image, badge);
    button.addEventListener('click', () => selectCell(cell.sampleId));
    ui.cellGrid.append(button);
  });
  const stillExists = cells.some(
    (cell) => cell.sampleId === state.selectedSampleId,
  );
  selectCell(stillExists ? state.selectedSampleId : cells[0]?.sampleId || null);
}

function renderBoard(payload) {
  state.board = payload.board;
  state.symbols = payload.configuration.symbols;
  state.totalFiltered = payload.totalFiltered;
  updateProgress(payload.progress);
  ui.loading.hidden = true;
  ui.empty.hidden = Boolean(payload.board);
  ui.boardCard.hidden = !payload.board;
  ui.position.textContent = payload.board
    ? `${payload.offset + 1} / ${payload.totalFiltered}`
    : `0 / ${payload.totalFiltered}`;
  ui.previous.disabled = state.busy || payload.offset <= 0;
  ui.next.disabled =
    state.busy || !payload.board || payload.offset + 1 >= payload.totalFiltered;
  if (!payload.board) return;
  const board = payload.board;
  ui.boardImage.src = `${board.boardUrl}?v=${board.boardChecksumSha256}`;
  ui.sequenceNumber.textContent = board.sequenceNumber;
  ui.boardIndex.textContent = board.boardIndex + 1;
  ui.sourceGroup.textContent = board.sourceGroup;
  ui.boardStatus.textContent =
    board.status === 'pending'
      ? 'Niedokończona'
      : board.status === 'accepted'
        ? 'Zaakceptowana'
        : 'Kompletna z odrzuceniem';
  ui.profileVersion.textContent = `v${board.calibrationProfileVersion}`;
  renderCells(board.cells);
}

async function loadBoard() {
  showError();
  ui.loading.hidden = false;
  ui.boardCard.hidden = true;
  ui.empty.hidden = true;
  const query = new URLSearchParams({
    offset: String(state.offset),
    status: ui.filter.value,
  });
  if (state.sequenceNumber) query.set('sequenceNumber', state.sequenceNumber);
  try {
    const payload = await request(`/api/boards?${query}`);
    if (!payload.configuration.configured) {
      ui.setupPanel.hidden = false;
      ui.reviewPanel.hidden = true;
      updateProgress(payload.progress);
      return;
    }
    ui.setupPanel.hidden = true;
    ui.reviewPanel.hidden = false;
    renderBoard(payload);
  } catch (error) {
    ui.loading.hidden = true;
    showError(error.message);
  }
}

async function decide(decision, symbolCode = null) {
  if (state.busy || !state.board || !state.selectedSampleId) return;
  setBusy(true);
  showError();
  try {
    await request('/api/board-decisions', {
      method: 'POST',
      body: JSON.stringify({
        applyToIdentical: ui.applyIdentical.checked,
        boardId: state.board.boardId,
        decisions: [{ decision, sampleId: state.selectedSampleId, symbolCode }],
      }),
    });
    await loadBoard();
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

ui.setupForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setBusy(true);
  try {
    await request('/api/configure', {
      method: 'POST',
      body: JSON.stringify({
        gameCode: ui.gameCode.value.trim(),
        reviewedBy: ui.reviewedBy.value.trim(),
        symbolCodes: ui.symbolCodes.value
          .split(/[\n,;]/)
          .map((value) => value.trim())
          .filter(Boolean),
      }),
    });
    await loadBoard();
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
});

ui.filter.addEventListener('change', () => {
  state.offset = 0;
  loadBoard();
});
ui.previous.addEventListener('click', () => {
  state.offset = Math.max(0, state.offset - 1);
  loadBoard();
});
ui.next.addEventListener('click', () => {
  state.offset += 1;
  loadBoard();
});
ui.jumpForm.addEventListener('submit', (event) => {
  event.preventDefault();
  state.sequenceNumber = ui.sequenceJump.value;
  state.offset = 0;
  loadBoard();
});
ui.clearJump.addEventListener('click', () => {
  state.sequenceNumber = '';
  ui.sequenceJump.value = '';
  state.offset = 0;
  loadBoard();
});
ui.reject.addEventListener('click', () => decide('rejected'));
ui.clear.addEventListener('click', () => decide('clear'));

window.addEventListener('keydown', (event) => {
  if (
    state.busy ||
    event.target instanceof HTMLInputElement ||
    event.target instanceof HTMLTextAreaElement ||
    event.target instanceof HTMLSelectElement
  )
    return;
  if (/^[1-9]$/.test(event.key)) {
    const symbol = state.symbols[Number(event.key) - 1];
    if (symbol) decide('accepted', symbol.symbolCode);
  } else if (['q', 'w', 'e'].includes(event.key.toLowerCase())) {
    const selected = state.board?.cells.find(
      (cell) => cell.sampleId === state.selectedSampleId,
    );
    const index = ['q', 'w', 'e'].indexOf(event.key.toLowerCase());
    const suggestion = selected?.suggestions?.[index];
    if (suggestion) decide('accepted', suggestion.symbolCode);
  } else if (event.key.toLowerCase() === 'r') {
    decide('rejected');
  } else if (event.key.toLowerCase() === 'c') {
    decide('clear');
  } else if (event.key === 'ArrowRight') {
    ui.next.click();
  } else if (event.key === 'ArrowLeft') {
    ui.previous.click();
  }
});

request('/api/bootstrap')
  .then((payload) => {
    state.token = payload.token;
    return loadBoard();
  })
  .catch((error) => {
    ui.loading.hidden = true;
    showError(error.message);
  });
