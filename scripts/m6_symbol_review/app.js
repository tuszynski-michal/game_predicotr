const ui = {
  accepted: document.querySelector('#accepted-count'),
  applyIdentical: document.querySelector('#apply-identical'),
  boardIndex: document.querySelector('#board-index'),
  cellPosition: document.querySelector('#cell-position'),
  clear: document.querySelector('#clear'),
  cropImage: document.querySelector('#crop-image'),
  currentDecision: document.querySelector('#current-decision'),
  empty: document.querySelector('#empty'),
  error: document.querySelector('#error'),
  filter: document.querySelector('#filter'),
  gameCode: document.querySelector('#game-code'),
  loading: document.querySelector('#loading'),
  next: document.querySelector('#next'),
  pending: document.querySelector('#pending-count'),
  position: document.querySelector('#position'),
  previous: document.querySelector('#previous'),
  reject: document.querySelector('#reject'),
  rejected: document.querySelector('#rejected-count'),
  reviewPanel: document.querySelector('#review-panel'),
  reviewedBy: document.querySelector('#reviewed-by'),
  sampleCard: document.querySelector('#sample-card'),
  sequenceNumber: document.querySelector('#sequence-number'),
  setupForm: document.querySelector('#setup-form'),
  setupPanel: document.querySelector('#setup-panel'),
  skip: document.querySelector('#skip'),
  symbolButtons: document.querySelector('#symbol-buttons'),
  symbolCodes: document.querySelector('#symbol-codes'),
  total: document.querySelector('#total-count'),
};

const state = {
  busy: false,
  offset: 0,
  sample: null,
  symbols: [],
  token: '',
  totalFiltered: 0,
};

function showError(message) {
  ui.error.textContent = message;
  ui.error.hidden = !message;
}

function setBusy(value) {
  state.busy = value;
  document
    .querySelectorAll('button, input, select, textarea')
    .forEach((element) => {
      element.disabled = value;
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
  if (!response.ok) {
    throw new Error(payload?.message || `Błąd HTTP ${response.status}.`);
  }
  return payload;
}

function updateProgress(progress) {
  ui.pending.textContent = progress.pending.toLocaleString('pl-PL');
  ui.accepted.textContent = progress.accepted.toLocaleString('pl-PL');
  ui.rejected.textContent = progress.rejected.toLocaleString('pl-PL');
  ui.total.textContent = progress.total.toLocaleString('pl-PL');
}

function renderSymbolButtons() {
  ui.symbolButtons.replaceChildren();
  state.symbols.forEach((symbol, index) => {
    const button = document.createElement('button');
    const shortcut = index < 9 ? `${index + 1} · ` : '';
    button.type = 'button';
    button.textContent = `${shortcut}${symbol.symbolCode}`;
    button.dataset.symbolCode = symbol.symbolCode;
    button.classList.toggle(
      'selected',
      state.sample?.decision === 'accepted' &&
        state.sample?.symbolCode === symbol.symbolCode,
    );
    button.addEventListener('click', () =>
      decide('accepted', symbol.symbolCode),
    );
    ui.symbolButtons.append(button);
  });
}

function renderSample(payload) {
  const sample = payload.samples[0] || null;
  state.sample = sample;
  state.totalFiltered = payload.totalFiltered;
  state.symbols = payload.configuration.symbols;
  updateProgress(payload.progress);
  ui.loading.hidden = true;
  ui.empty.hidden = Boolean(sample);
  ui.sampleCard.hidden = !sample;
  ui.position.textContent = sample
    ? `${payload.offset + 1} / ${payload.totalFiltered}`
    : `0 / ${payload.totalFiltered}`;
  ui.previous.disabled = state.busy || payload.offset <= 0;
  ui.next.disabled =
    state.busy || !sample || payload.offset + 1 >= payload.totalFiltered;
  if (!sample) {
    return;
  }
  ui.cropImage.src = `${sample.cropUrl}?v=${sample.cropChecksumSha256}`;
  ui.sequenceNumber.textContent = sample.sequenceNumber;
  ui.boardIndex.textContent = sample.boardIndex;
  ui.cellPosition.textContent = `r${sample.rowIndex} · c${sample.columnIndex}`;
  ui.currentDecision.textContent =
    sample.decision === 'accepted'
      ? `Zaakceptowano: ${sample.symbolCode}`
      : sample.decision === 'rejected'
        ? 'Odrzucono'
        : 'Oczekuje';
  renderSymbolButtons();
}

async function loadPage() {
  showError('');
  ui.loading.hidden = false;
  ui.sampleCard.hidden = true;
  ui.empty.hidden = true;
  try {
    const payload = await request(
      `/api/state?status=${encodeURIComponent(ui.filter.value)}&offset=${state.offset}&limit=1`,
    );
    if (!payload.configuration.configured) {
      ui.setupPanel.hidden = false;
      ui.reviewPanel.hidden = true;
      updateProgress(payload.progress);
      return;
    }
    ui.setupPanel.hidden = true;
    ui.reviewPanel.hidden = false;
    renderSample(payload);
  } catch (error) {
    ui.loading.hidden = true;
    showError(error.message);
  }
}

async function mutate(path, body) {
  if (state.busy) return;
  setBusy(true);
  showError('');
  try {
    await request(path, { method: 'POST', body: JSON.stringify(body) });
    if (ui.filter.value !== 'pending') {
      state.offset = Math.min(
        state.offset + 1,
        Math.max(0, state.totalFiltered - 1),
      );
    }
    await loadPage();
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

function decide(decision, symbolCode = null) {
  if (!state.sample) return;
  return mutate('/api/decision', {
    applyToIdentical: ui.applyIdentical.checked,
    decision,
    sampleId: state.sample.sampleId,
    symbolCode,
  });
}

ui.setupForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const symbols = ui.symbolCodes.value
    .split(/[\n,;]/)
    .map((value) => value.trim())
    .filter(Boolean);
  setBusy(true);
  showError('');
  try {
    await request('/api/configure', {
      method: 'POST',
      body: JSON.stringify({
        gameCode: ui.gameCode.value.trim(),
        reviewedBy: ui.reviewedBy.value.trim(),
        symbolCodes: symbols,
      }),
    });
    await loadPage();
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
});

ui.filter.addEventListener('change', () => {
  state.offset = 0;
  loadPage();
});
ui.previous.addEventListener('click', () => {
  state.offset = Math.max(0, state.offset - 1);
  loadPage();
});
ui.next.addEventListener('click', () => {
  state.offset += 1;
  loadPage();
});
ui.skip.addEventListener('click', () => {
  state.offset = Math.min(
    state.offset + 1,
    Math.max(0, state.totalFiltered - 1),
  );
  loadPage();
});
ui.reject.addEventListener('click', () => decide('rejected'));
ui.clear.addEventListener('click', () => {
  if (!state.sample) return;
  mutate('/api/clear', {
    applyToIdentical: ui.applyIdentical.checked,
    sampleId: state.sample.sampleId,
  });
});

window.addEventListener('keydown', (event) => {
  if (
    state.busy ||
    event.target instanceof HTMLInputElement ||
    event.target instanceof HTMLTextAreaElement ||
    event.target instanceof HTMLSelectElement
  ) {
    return;
  }
  if (/^[1-9]$/.test(event.key)) {
    const symbol = state.symbols[Number(event.key) - 1];
    if (symbol) decide('accepted', symbol.symbolCode);
  } else if (event.key.toLowerCase() === 'r') {
    decide('rejected');
  } else if (event.key.toLowerCase() === 'c') {
    ui.clear.click();
  } else if (event.key.toLowerCase() === 's' || event.key === 'ArrowRight') {
    ui.skip.click();
  } else if (event.key === 'ArrowLeft') {
    ui.previous.click();
  }
});

async function bootstrap() {
  try {
    const payload = await request('/api/bootstrap');
    state.token = payload.token;
    await loadPage();
  } catch (error) {
    ui.loading.hidden = true;
    showError(error.message);
  }
}

bootstrap();
