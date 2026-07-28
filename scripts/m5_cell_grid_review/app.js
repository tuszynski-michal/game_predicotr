'use strict';

const CANONICAL_WIDTH = 500;
const CANONICAL_HEIGHT = 300;
const SOURCE_CANVAS_WIDTH = 700;
const CORNER_NAMES = ['Lewy górny', 'Prawy górny', 'Prawy dolny', 'Lewy dolny'];

const state = {
  token: '',
  filter: 'pending',
  offset: 0,
  totalFiltered: 0,
  sample: null,
  sourceImage: null,
  sourcePixels: null,
  sourceRaster: document.createElement('canvas'),
  rectifiedBuffer: document.createElement('canvas'),
  viewport: null,
  quad: [],
  detectedQuad: [],
  impactCells: new Set(),
  draggingCorner: null,
  dirty: false,
  renderScheduled: false,
  profileDocument: null,
};
state.rectifiedBuffer.width = CANONICAL_WIDTH;
state.rectifiedBuffer.height = CANONICAL_HEIGHT;

const elements = {
  acceptButton: document.querySelector('#acceptButton'),
  boardPosition: document.querySelector('#boardPosition'),
  boardTitle: document.querySelector('#boardTitle'),
  clearCellsButton: document.querySelector('#clearCellsButton'),
  cropPreviews: document.querySelector('#cropPreviews'),
  emptyState: document.querySelector('#emptyState'),
  imageId: document.querySelector('#imageId'),
  impactCells: document.querySelector('#impactCells'),
  impactReviewed: document.querySelector('#impactReviewed'),
  nextButton: document.querySelector('#nextButton'),
  pointControls: document.querySelector('#pointControls'),
  positionText: document.querySelector('#positionText'),
  previousButton: document.querySelector('#previousButton'),
  previewsPanel: document.querySelector('#previewsPanel'),
  progressBar: document.querySelector('#progressBar'),
  progressText: document.querySelector('#progressText'),
  profileAnchors: document.querySelector('#profileAnchors'),
  profileId: document.querySelector('#profileId'),
  profileInterpolation: document.querySelector('#profileInterpolation'),
  profileScope: document.querySelector('#profileScope'),
  profileStatus: document.querySelector('#profileStatus'),
  profileVersion: document.querySelector('#profileVersion'),
  quadSummary: document.querySelector('#quadSummary'),
  rectifiedCanvas: document.querySelector('#rectifiedCanvas'),
  reopenButton: document.querySelector('#reopenButton'),
  resetButton: document.querySelector('#resetButton'),
  reviewBadge: document.querySelector('#reviewBadge'),
  reviewContent: document.querySelector('#reviewContent'),
  reviewerInput: document.querySelector('#reviewerInput'),
  saveDraftButton: document.querySelector('#saveDraftButton'),
  saveState: document.querySelector('#saveState'),
  selectAllCellsButton: document.querySelector('#selectAllCellsButton'),
  sequenceNumber: document.querySelector('#sequenceNumber'),
  sourceCanvas: document.querySelector('#sourceCanvas'),
  sourcePhoto: document.querySelector('#sourcePhoto'),
  sourceGroup: document.querySelector('#sourceGroup'),
  statusFilter: document.querySelector('#statusFilter'),
  toast: document.querySelector('#toast'),
};

const sourceContext = elements.sourceCanvas.getContext('2d');
const rectifiedContext = elements.rectifiedCanvas.getContext('2d');
const rectifiedBufferContext = state.rectifiedBuffer.getContext('2d');
const previewCanvases = [];

for (let index = 0; index < 15; index += 1) {
  const card = document.createElement('div');
  card.className = 'crop-card';
  const canvas = document.createElement('canvas');
  canvas.width = 120;
  canvas.height = 120;
  const label = document.createElement('span');
  label.textContent = `komórka ${index} · r${Math.floor(index / 5) + 1} k${(index % 5) + 1}`;
  card.append(canvas, label);
  elements.cropPreviews.append(card);
  previewCanvases.push({ canvas, card });

  const impactButton = document.createElement('button');
  impactButton.className = 'impact-cell';
  impactButton.type = 'button';
  impactButton.textContent = `${index}`;
  impactButton.title = `Komórka ${index}`;
  impactButton.addEventListener('click', () => {
    if (state.sample?.reviewStatus === 'accepted') return;
    if (state.impactCells.has(index)) {
      state.impactCells.delete(index);
    } else {
      state.impactCells.add(index);
    }
    markDirty();
    renderImpact();
    renderPreviews();
  });
  elements.impactCells.append(impactButton);
}

function cloneQuad(quad) {
  return quad.map((point) => ({ x: Number(point.x), y: Number(point.y) }));
}

function showToast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle('error', error);
  elements.toast.hidden = false;
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, 3800);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) {
    headers['Content-Type'] = 'application/json';
    headers['X-Review-Token'] = state.token;
  }
  const response = await fetch(path, { ...options, headers });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(`${body.code || 'HTTP_ERROR'}: ${body.message || 'Błąd'}`);
  }
  return body;
}

function markDirty() {
  state.dirty = true;
  elements.saveState.textContent = 'Niezapisane zmiany';
}

function markSaved(message = 'Zapisano') {
  state.dirty = false;
  elements.saveState.textContent = message;
}

function cross(first, second, third) {
  return (
    (second.x - first.x) * (third.y - second.y) -
    (second.y - first.y) * (third.x - second.x)
  );
}

function quadIsValid(quad) {
  if (!state.sample || quad.length !== 4) return false;
  const width = state.sample.sourceImageWidth;
  const height = state.sample.sourceImageHeight;
  if (
    quad.some(
      (point) =>
        !Number.isFinite(point.x) ||
        !Number.isFinite(point.y) ||
        point.x < 0 ||
        point.y < 0 ||
        point.x > width - 1 ||
        point.y > height - 1,
    )
  ) {
    return false;
  }
  const edges = quad.map((point, index) => {
    const next = quad[(index + 1) % 4];
    return Math.hypot(next.x - point.x, next.y - point.y);
  });
  const crosses = quad.map((point, index) =>
    cross(point, quad[(index + 1) % 4], quad[(index + 2) % 4]),
  );
  const area =
    Math.abs(
      quad.reduce((sum, point, index) => {
        const next = quad[(index + 1) % 4];
        return sum + point.x * next.y - next.x * point.y;
      }, 0),
    ) / 2;
  const leftCenter = (quad[0].x + quad[3].x) / 2;
  const rightCenter = (quad[1].x + quad[2].x) / 2;
  const topCenter = (quad[0].y + quad[1].y) / 2;
  const bottomCenter = (quad[2].y + quad[3].y) / 2;
  return (
    Math.min(...edges) >= 20 &&
    area >= 1000 &&
    crosses.every((value) => value > 0) &&
    leftCenter < rightCenter &&
    topCenter < bottomCenter
  );
}

function squareToQuad(quad) {
  const [p0, p1, p2, p3] = quad;
  const dx1 = p1.x - p2.x;
  const dx2 = p3.x - p2.x;
  const dx3 = p0.x - p1.x + p2.x - p3.x;
  const dy1 = p1.y - p2.y;
  const dy2 = p3.y - p2.y;
  const dy3 = p0.y - p1.y + p2.y - p3.y;
  let g = 0;
  let h = 0;
  if (Math.abs(dx3) > 1e-9 || Math.abs(dy3) > 1e-9) {
    const denominator = dx1 * dy2 - dx2 * dy1;
    if (Math.abs(denominator) < 1e-9) {
      throw new Error('Nie można wyznaczyć perspektywy dla tego quadu.');
    }
    g = (dx3 * dy2 - dx2 * dy3) / denominator;
    h = (dx1 * dy3 - dx3 * dy1) / denominator;
  }
  return {
    a: p1.x - p0.x + g * p1.x,
    b: p3.x - p0.x + h * p3.x,
    c: p0.x,
    d: p1.y - p0.y + g * p1.y,
    e: p3.y - p0.y + h * p3.y,
    f: p0.y,
    g,
    h,
  };
}

function projectUnit(matrix, u, v) {
  const denominator = matrix.g * u + matrix.h * v + 1;
  return {
    x: (matrix.a * u + matrix.b * v + matrix.c) / denominator,
    y: (matrix.d * u + matrix.e * v + matrix.f) / denominator,
  };
}

function calculateViewport(quad, imageWidth, imageHeight) {
  const xValues = quad.map((point) => point.x);
  const yValues = quad.map((point) => point.y);
  const rawWidth = Math.max(...xValues) - Math.min(...xValues);
  const rawHeight = Math.max(...yValues) - Math.min(...yValues);
  const marginX = Math.max(30, rawWidth * 0.28);
  const marginY = Math.max(30, rawHeight * 0.35);
  const left = Math.max(0, Math.min(...xValues) - marginX);
  const top = Math.max(0, Math.min(...yValues) - marginY);
  const right = Math.min(imageWidth, Math.max(...xValues) + marginX);
  const bottom = Math.min(imageHeight, Math.max(...yValues) + marginY);
  return {
    x: left,
    y: top,
    width: Math.max(1, right - left),
    height: Math.max(1, bottom - top),
  };
}

function sourceToCanvas(point) {
  return {
    x:
      ((point.x - state.viewport.x) / state.viewport.width) *
      elements.sourceCanvas.width,
    y:
      ((point.y - state.viewport.y) / state.viewport.height) *
      elements.sourceCanvas.height,
  };
}

function canvasToSource(point) {
  return {
    x:
      state.viewport.x +
      (point.x / elements.sourceCanvas.width) * state.viewport.width,
    y:
      state.viewport.y +
      (point.y / elements.sourceCanvas.height) * state.viewport.height,
  };
}

function drawPerspectiveGrid(quad, color, dash, width, handles = false) {
  const matrix = squareToQuad(quad);
  sourceContext.save();
  sourceContext.strokeStyle = color;
  sourceContext.fillStyle = color;
  sourceContext.lineWidth = width;
  sourceContext.setLineDash(dash);
  for (let column = 0; column <= 5; column += 1) {
    const top = sourceToCanvas(projectUnit(matrix, column / 5, 0));
    const bottom = sourceToCanvas(projectUnit(matrix, column / 5, 1));
    sourceContext.beginPath();
    sourceContext.moveTo(top.x, top.y);
    sourceContext.lineTo(bottom.x, bottom.y);
    sourceContext.stroke();
  }
  for (let row = 0; row <= 3; row += 1) {
    const left = sourceToCanvas(projectUnit(matrix, 0, row / 3));
    const right = sourceToCanvas(projectUnit(matrix, 1, row / 3));
    sourceContext.beginPath();
    sourceContext.moveTo(left.x, left.y);
    sourceContext.lineTo(right.x, right.y);
    sourceContext.stroke();
  }
  if (handles) {
    sourceContext.setLineDash([]);
    quad.forEach((point, index) => {
      const canvasPoint = sourceToCanvas(point);
      sourceContext.beginPath();
      sourceContext.arc(canvasPoint.x, canvasPoint.y, 9, 0, Math.PI * 2);
      sourceContext.fill();
      sourceContext.fillStyle = '#071117';
      sourceContext.font = 'bold 11px sans-serif';
      sourceContext.textAlign = 'center';
      sourceContext.textBaseline = 'middle';
      sourceContext.fillText(String(index + 1), canvasPoint.x, canvasPoint.y);
      sourceContext.fillStyle = color;
    });
  }
  sourceContext.restore();
}

function renderSource() {
  if (!state.sourceImage || !state.viewport) return;
  sourceContext.clearRect(
    0,
    0,
    elements.sourceCanvas.width,
    elements.sourceCanvas.height,
  );
  drawPerspectiveGrid(state.detectedQuad, 'rgba(255,255,255,.8)', [7, 6], 2);
  drawPerspectiveGrid(state.quad, '#20d6c7', [], 3, true);
}

function renderRectified() {
  if (!state.sourcePixels || !quadIsValid(state.quad)) return;
  const matrix = squareToQuad(state.quad);
  const output = rectifiedBufferContext.createImageData(
    CANONICAL_WIDTH,
    CANONICAL_HEIGHT,
  );
  const sourceData = state.sourcePixels.data;
  const sourceWidth = state.sourcePixels.width;
  const sourceHeight = state.sourcePixels.height;
  for (let y = 0; y < CANONICAL_HEIGHT; y += 1) {
    const v = y / (CANONICAL_HEIGHT - 1);
    for (let x = 0; x < CANONICAL_WIDTH; x += 1) {
      const u = x / (CANONICAL_WIDTH - 1);
      const sourcePoint = projectUnit(matrix, u, v);
      const sourceX = Math.max(
        0,
        Math.min(sourceWidth - 1, Math.round(sourcePoint.x)),
      );
      const sourceY = Math.max(
        0,
        Math.min(sourceHeight - 1, Math.round(sourcePoint.y)),
      );
      const sourceIndex = (sourceY * sourceWidth + sourceX) * 4;
      const outputIndex = (y * CANONICAL_WIDTH + x) * 4;
      output.data[outputIndex] = sourceData[sourceIndex];
      output.data[outputIndex + 1] = sourceData[sourceIndex + 1];
      output.data[outputIndex + 2] = sourceData[sourceIndex + 2];
      output.data[outputIndex + 3] = 255;
    }
  }
  rectifiedBufferContext.putImageData(output, 0, 0);
  rectifiedContext.clearRect(0, 0, CANONICAL_WIDTH, CANONICAL_HEIGHT);
  rectifiedContext.drawImage(state.rectifiedBuffer, 0, 0);
  rectifiedContext.save();
  rectifiedContext.strokeStyle = '#20d6c7';
  rectifiedContext.lineWidth = 2;
  for (let column = 1; column < 5; column += 1) {
    rectifiedContext.beginPath();
    rectifiedContext.moveTo(column * 100, 0);
    rectifiedContext.lineTo(column * 100, CANONICAL_HEIGHT);
    rectifiedContext.stroke();
  }
  for (let row = 1; row < 3; row += 1) {
    rectifiedContext.beginPath();
    rectifiedContext.moveTo(0, row * 100);
    rectifiedContext.lineTo(CANONICAL_WIDTH, row * 100);
    rectifiedContext.stroke();
  }
  rectifiedContext.restore();
  renderPreviews();
}

function scheduleGeometryRender() {
  renderSource();
  if (state.renderScheduled) return;
  state.renderScheduled = true;
  window.requestAnimationFrame(() => {
    state.renderScheduled = false;
    renderRectified();
  });
}

function renderPreviews() {
  for (let row = 0; row < 3; row += 1) {
    for (let column = 0; column < 5; column += 1) {
      const index = row * 5 + column;
      const { canvas, card } = previewCanvases[index];
      const context = canvas.getContext('2d');
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(
        state.rectifiedBuffer,
        column * 100,
        row * 100,
        100,
        100,
        0,
        0,
        canvas.width,
        canvas.height,
      );
      card.classList.toggle('v1-cut', state.impactCells.has(index));
    }
  }
}

function renderImpact() {
  const locked = state.sample?.reviewStatus === 'accepted';
  [...elements.impactCells.children].forEach((button, index) => {
    button.classList.toggle('selected', state.impactCells.has(index));
    button.setAttribute('aria-pressed', String(state.impactCells.has(index)));
    button.disabled = locked;
  });
  elements.impactReviewed.disabled = locked;
  elements.clearCellsButton.disabled = locked;
  elements.selectAllCellsButton.disabled = locked;
  elements.resetButton.disabled = locked;
  elements.reviewerInput.disabled = locked;
}

function updateQuadSummary() {
  elements.quadSummary.textContent = state.quad
    .map(
      (point, index) =>
        `${index + 1}: ${point.x.toFixed(1)},${point.y.toFixed(1)}`,
    )
    .join(' · ');
}

function renderPointControls() {
  elements.pointControls.replaceChildren();
  const locked = state.sample?.reviewStatus === 'accepted';
  state.quad.forEach((point, index) => {
    const row = document.createElement('div');
    row.className = 'point-control';
    const label = document.createElement('strong');
    label.textContent = `${index + 1}. ${CORNER_NAMES[index]}`;
    const xInput = document.createElement('input');
    const yInput = document.createElement('input');
    for (const [axis, input] of [
      ['x', xInput],
      ['y', yInput],
    ]) {
      input.type = 'number';
      input.step = '0.1';
      input.min = '0';
      input.max = String(
        axis === 'x'
          ? state.sample.sourceImageWidth - 1
          : state.sample.sourceImageHeight - 1,
      );
      input.value = point[axis].toFixed(1);
      input.disabled = locked;
      input.setAttribute('aria-label', `${CORNER_NAMES[index]} ${axis}`);
      const applyPointInput = (showError) => {
        const candidate = cloneQuad(state.quad);
        candidate[index][axis] = Number(input.value);
        if (!quadIsValid(candidate)) {
          if (showError) {
            input.value = state.quad[index][axis].toFixed(1);
            showToast('Ten punkt tworzy nieprawidłowy czworokąt.', true);
          }
          return;
        }
        state.quad = candidate;
        markDirty();
        updateQuadSummary();
        scheduleGeometryRender();
      };
      input.addEventListener('input', () => applyPointInput(false));
      input.addEventListener('change', () => applyPointInput(true));
    }
    row.append(label, xInput, yInput);
    elements.pointControls.append(row);
  });
  updateQuadSummary();
}

function renderAll() {
  renderPointControls();
  renderImpact();
  scheduleGeometryRender();
}

function renderCalibrationProfile() {
  const profiles = state.profileDocument?.profiles || [];
  const sample = state.sample;
  const profile = profiles.find(
    (item) =>
      item.sourceGroup === sample?.sourceGroup &&
      item.boardPosition === sample?.boardPosition,
  );
  if (!profile || !sample) {
    elements.profileStatus.textContent = 'Brak opublikowanego profilu';
    elements.profileVersion.textContent = 'niedostępny';
    elements.profileScope.textContent = '—';
    elements.profileAnchors.textContent = '—';
    elements.profileInterpolation.textContent = '—';
    elements.profileId.textContent = '—';
    return;
  }
  const anchors = profile.anchors.map((anchor) => anchor.sequenceNumber);
  const sequence = sample.sequenceNumber;
  let behavior;
  if (sequence <= anchors[0]) {
    behavior = `clamp do ${anchors[0]}`;
  } else if (sequence >= anchors.at(-1)) {
    behavior = `clamp do ${anchors.at(-1)}`;
  } else {
    const rightIndex = anchors.findIndex((value) => value >= sequence);
    const left = anchors[rightIndex - 1];
    const right = anchors[rightIndex];
    if (sequence === right) {
      behavior = `dokładna kotwica ${right}`;
    } else {
      const weight = (sequence - left) / (right - left);
      behavior = `interpolacja ${left} → ${right} · ${(weight * 100).toFixed(1)}%`;
    }
  }
  elements.profileStatus.textContent = 'Profil opublikowany';
  elements.profileVersion.textContent = `v${profile.profileVersion}`;
  elements.profileScope.textContent = `${profile.sourceGroup} · pozycja ${profile.boardPosition}`;
  elements.profileAnchors.textContent = anchors.join(', ');
  elements.profileInterpolation.textContent = behavior;
  elements.profileId.textContent = profile.profileId.slice(0, 16);
  elements.profileId.title = profile.profileId;
}

async function loadImage(url, image = new Image()) {
  image.decoding = 'async';
  await new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = () =>
      reject(new Error('Nie można odczytać zdjęcia źródłowego.'));
    image.src = url;
  });
  return image;
}

function positionSourcePhoto() {
  const { viewport } = state;
  elements.sourcePhoto.style.width = `${(state.sample.sourceImageWidth / viewport.width) * 100}%`;
  elements.sourcePhoto.style.height = `${(state.sample.sourceImageHeight / viewport.height) * 100}%`;
  elements.sourcePhoto.style.left = `${(-viewport.x / viewport.width) * 100}%`;
  elements.sourcePhoto.style.top = `${(-viewport.y / viewport.height) * 100}%`;
}

function prepareSourcePixels() {
  state.sourceRaster.width = state.sourceImage.naturalWidth;
  state.sourceRaster.height = state.sourceImage.naturalHeight;
  const context = state.sourceRaster.getContext('2d', {
    willReadFrequently: true,
  });
  context.drawImage(state.sourceImage, 0, 0);
  state.sourcePixels = context.getImageData(
    0,
    0,
    state.sourceRaster.width,
    state.sourceRaster.height,
  );
}

async function loadCurrent() {
  elements.saveState.textContent = 'Ładowanie…';
  const data = await api(
    `/api/state?status=${encodeURIComponent(state.filter)}&offset=${state.offset}&limit=1`,
  );
  state.totalFiltered = data.totalFiltered;
  const { accepted, pending, total } = data.progress;
  elements.progressText.textContent = `${accepted}/${total} zaakceptowanych · ${pending} oczekuje`;
  elements.progressBar.style.width = `${total ? (accepted / total) * 100 : 0}%`;
  elements.positionText.textContent = data.totalFiltered
    ? `${state.offset + 1} / ${data.totalFiltered}`
    : '0 / 0';
  elements.previousButton.disabled = state.offset <= 0;
  elements.nextButton.disabled = state.offset + 1 >= data.totalFiltered;
  elements.emptyState.hidden = data.samples.length > 0;
  elements.reviewContent.hidden = data.samples.length === 0;
  elements.previewsPanel.hidden = data.samples.length === 0;
  if (!data.samples.length) {
    state.sample = null;
    markSaved('');
    return;
  }

  const sample = data.samples[0];
  state.sample = sample;
  state.quad = cloneQuad(sample.sourceQuad);
  state.detectedQuad = cloneQuad(sample.detectedSourceQuad);
  state.impactCells = new Set(sample.v1CutCellIndexes);
  elements.impactReviewed.checked = sample.v1ImpactReviewed;
  state.sourceImage = await loadImage(
    sample.sourceImageUrl,
    elements.sourcePhoto,
  );
  if (
    state.sourceImage.naturalWidth !== sample.sourceImageWidth ||
    state.sourceImage.naturalHeight !== sample.sourceImageHeight
  ) {
    throw new Error('Wymiary zdjęcia nie zgadzają się z manifestem.');
  }
  prepareSourcePixels();
  state.viewport = calculateViewport(
    state.detectedQuad,
    sample.sourceImageWidth,
    sample.sourceImageHeight,
  );
  elements.sourceCanvas.width = SOURCE_CANVAS_WIDTH;
  elements.sourceCanvas.height = Math.max(
    260,
    Math.round(
      SOURCE_CANVAS_WIDTH * (state.viewport.height / state.viewport.width),
    ),
  );
  positionSourcePhoto();
  elements.boardTitle.textContent = `Sekwencja ${sample.sequenceNumber}`;
  elements.sequenceNumber.textContent = sample.sequenceNumber;
  elements.boardPosition.textContent = sample.boardPosition;
  elements.sourceGroup.textContent = sample.sourceGroup;
  elements.imageId.textContent = sample.imageId;
  elements.imageId.title = sample.imageId;
  renderCalibrationProfile();
  const acceptedEntry = sample.reviewStatus === 'accepted';
  elements.reviewBadge.textContent = acceptedEntry
    ? `Zaakceptowana · ${sample.reviewedBy}`
    : 'Do sprawdzenia';
  elements.reviewBadge.classList.toggle('accepted', acceptedEntry);
  elements.acceptButton.hidden = acceptedEntry;
  elements.saveDraftButton.hidden = acceptedEntry;
  elements.reopenButton.hidden = !acceptedEntry;
  elements.reviewerInput.value =
    sample.reviewedBy || elements.reviewerInput.value || 'owner';
  markSaved(acceptedEntry ? 'Decyzja przywrócona' : 'Szkic załadowany');
  renderAll();
}

function payload() {
  return {
    observationId: state.sample.observationId,
    sourceQuad: state.quad.map((point) => ({
      x: Number(point.x.toFixed(4)),
      y: Number(point.y.toFixed(4)),
    })),
    v1CutCellIndexes: [...state.impactCells].sort((a, b) => a - b),
    v1ImpactReviewed: elements.impactReviewed.checked,
  };
}

async function saveDraft() {
  if (!state.sample || state.sample.reviewStatus === 'accepted') return;
  await api('/api/draft', {
    method: 'POST',
    body: JSON.stringify(payload()),
  });
  markSaved('Szkic zapisany');
  showToast('Szkic zapisany.');
}

async function acceptCurrent() {
  if (!state.sample || state.sample.reviewStatus === 'accepted') return;
  const reviewedBy = elements.reviewerInput.value.trim();
  if (!reviewedBy) {
    showToast('Podaj osobę weryfikującą.', true);
    elements.reviewerInput.focus();
    return;
  }
  if (!elements.impactReviewed.checked) {
    showToast('Najpierw potwierdź ocenę wpływu historycznego v1.', true);
    elements.impactReviewed.focus();
    return;
  }
  await api('/api/accept', {
    method: 'POST',
    body: JSON.stringify({ ...payload(), reviewedBy }),
  });
  showToast('Plansza zaakceptowana.');
  if (state.filter === 'pending' && state.offset >= state.totalFiltered - 1) {
    state.offset = Math.max(0, state.offset - 1);
  }
  await loadCurrent();
}

async function reopenCurrent() {
  if (!state.sample || state.sample.reviewStatus !== 'accepted') return;
  await api('/api/reopen', {
    method: 'POST',
    body: JSON.stringify({ observationId: state.sample.observationId }),
  });
  showToast('Plansza wróciła do kolejki.');
  if (state.filter === 'accepted' && state.offset >= state.totalFiltered - 1) {
    state.offset = Math.max(0, state.offset - 1);
  }
  await loadCurrent();
}

async function navigate(delta) {
  const next = Math.max(
    0,
    Math.min(state.totalFiltered - 1, state.offset + delta),
  );
  if (next === state.offset) return;
  if (state.dirty && state.sample?.reviewStatus !== 'accepted') {
    await saveDraft();
  }
  state.offset = next;
  await loadCurrent();
}

function canvasPoint(event) {
  const rectangle = elements.sourceCanvas.getBoundingClientRect();
  return {
    x:
      ((event.clientX - rectangle.left) / rectangle.width) *
      elements.sourceCanvas.width,
    y:
      ((event.clientY - rectangle.top) / rectangle.height) *
      elements.sourceCanvas.height,
  };
}

elements.sourceCanvas.addEventListener('pointerdown', (event) => {
  if (!state.sample || state.sample.reviewStatus === 'accepted') return;
  const point = canvasPoint(event);
  const distances = state.quad.map((quadPoint, index) => {
    const visible = sourceToCanvas(quadPoint);
    return {
      index,
      distance: Math.hypot(visible.x - point.x, visible.y - point.y),
    };
  });
  const nearest = distances.sort(
    (left, right) => left.distance - right.distance,
  )[0];
  if (nearest.distance <= 18) {
    state.draggingCorner = nearest.index;
    elements.sourceCanvas.setPointerCapture(event.pointerId);
  }
});

elements.sourceCanvas.addEventListener('pointermove', (event) => {
  if (state.draggingCorner === null) return;
  const sourcePoint = canvasToSource(canvasPoint(event));
  const candidate = cloneQuad(state.quad);
  candidate[state.draggingCorner] = {
    x: Math.max(0, Math.min(state.sample.sourceImageWidth - 1, sourcePoint.x)),
    y: Math.max(0, Math.min(state.sample.sourceImageHeight - 1, sourcePoint.y)),
  };
  if (!quadIsValid(candidate)) return;
  state.quad = candidate;
  markDirty();
  renderPointControls();
  scheduleGeometryRender();
});

elements.sourceCanvas.addEventListener('pointerup', () => {
  state.draggingCorner = null;
});

elements.previousButton.addEventListener('click', () =>
  navigate(-1).catch(handleError),
);
elements.nextButton.addEventListener('click', () =>
  navigate(1).catch(handleError),
);
elements.saveDraftButton.addEventListener('click', () =>
  saveDraft().catch(handleError),
);
elements.acceptButton.addEventListener('click', () =>
  acceptCurrent().catch(handleError),
);
elements.reopenButton.addEventListener('click', () =>
  reopenCurrent().catch(handleError),
);
elements.resetButton.addEventListener('click', () => {
  state.quad = cloneQuad(state.detectedQuad);
  markDirty();
  renderAll();
});
elements.selectAllCellsButton.addEventListener('click', () => {
  state.impactCells = new Set(Array.from({ length: 15 }, (_, index) => index));
  markDirty();
  renderImpact();
  renderPreviews();
});
elements.clearCellsButton.addEventListener('click', () => {
  state.impactCells.clear();
  markDirty();
  renderImpact();
  renderPreviews();
});
elements.impactReviewed.addEventListener('change', markDirty);
elements.statusFilter.addEventListener('change', () => {
  state.filter = elements.statusFilter.value;
  state.offset = 0;
  loadCurrent().catch(handleError);
});

document.addEventListener('keydown', (event) => {
  const editingText =
    event.target instanceof HTMLInputElement &&
    !['checkbox'].includes(event.target.type);
  if (editingText) return;
  if (event.ctrlKey && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveDraft().catch(handleError);
  } else if (event.ctrlKey && event.key === 'Enter') {
    event.preventDefault();
    acceptCurrent().catch(handleError);
  } else if (event.ctrlKey && event.key.toLowerCase() === 'r') {
    event.preventDefault();
    elements.resetButton.click();
  } else if (event.key === 'ArrowLeft') {
    navigate(-1).catch(handleError);
  } else if (event.key === 'ArrowRight') {
    navigate(1).catch(handleError);
  }
});

function handleError(error) {
  console.error(error);
  showToast(error.message || String(error), true);
  elements.saveState.textContent = 'Błąd zapisu';
}

async function start() {
  const bootstrap = await api('/api/bootstrap');
  state.token = bootstrap.token;
  state.profileDocument = await api('/api/profiles');
  await loadCurrent();
}

start().catch(handleError);
