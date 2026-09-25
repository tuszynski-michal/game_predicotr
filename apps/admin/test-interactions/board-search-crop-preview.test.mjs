import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://localhost',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'HTMLInputElement',
  'HTMLImageElement',
  'Element',
  'Event',
  'MouseEvent',
  'KeyboardEvent',
  'Image',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const { createRoot } = await import('react-dom/client');
const { BoardSearchWorkspace } = await import(
  '../src/features/board-search/board-search-workspace.tsx'
);

after(() => dom.window.close());

const gameId = '11111111-1111-4111-8111-111111111111';
const symbol = {
  code: 'cherry',
  displayOrder: 0,
  id: 'symbol-cherry',
  imagePath: null,
  mobileCode: 1,
  name: 'Wiśnia',
  status: 'active',
};

function boardResult(sequenceNumber, overrides = {}) {
  return {
    assetMode: 'operational_review',
    boardChecksumSha256: String(sequenceNumber).padStart(64, '0'),
    importJobId: `job-${sequenceNumber}`,
    recognizedBoardId: `board-${sequenceNumber}`,
    reviewItemId: `review-${sequenceNumber}`,
    score: {
      alternativeMatchCount: 0,
      exactMatchCount: 1,
      mismatchCount: 0,
      score: 100,
      unknownCount: 0,
    },
    sequenceNumber,
    status: 'pending',
    ...overrides,
  };
}

const quad = [
  { x: 100, y: 200 },
  { x: 300, y: 200 },
  { x: 300, y: 400 },
  { x: 100, y: 400 },
];

async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function eventually(predicate, label) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    if (predicate()) return;
    await settle();
  }
  assert.fail(label);
}

function symbolButton() {
  const current = [...document.querySelectorAll('.boardSearchSymbolButton')].find(
    (node) => node.title === symbol.name,
  );
  assert.ok(current);
  return current;
}

function searchButton() {
  const current = [...document.querySelectorAll('button')].find((node) =>
    node.textContent.includes('Szukaj plansz'),
  );
  assert.ok(current);
  return current;
}

function boardImage() {
  const current = document.querySelector('.boardSearchBoardAsset');
  assert.ok(current);
  return current;
}

async function click(node) {
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}

async function fireImageLoad(img, width, height) {
  Object.defineProperty(img, 'naturalWidth', { configurable: true, value: width });
  Object.defineProperty(img, 'naturalHeight', { configurable: true, value: height });
  await act(async () => img.dispatchEvent(new dom.window.Event('load')));
}

function makeClient({ geometryImpl, searchImpl }) {
  return {
    archivedBoardSearchAssetUrl: () => 'http://127.0.0.1:8000/archive.jpg',
    getOperationalImageReviewItem: geometryImpl,
    listSymbols: async () => ({ data: [symbol] }),
    operationalImageReviewBoardAssetUrl: () =>
      'http://127.0.0.1:8000/board.jpg',
    searchGameBoards: searchImpl,
    symbolImageAssetUrl: () => 'http://127.0.0.1:8000/symbol.jpg',
  };
}

async function renderWorkspace(client) {
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(BoardSearchWorkspace, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client,
        gameId,
      }),
    ),
  );
  await eventually(() => symbolButton() !== null, 'palette should render');
  await click(symbolButton());
  await click(searchButton());
  await eventually(
    () => document.querySelector('.boardSearchResults') !== null,
    'search results should render',
  );
  return root;
}

test('a valid quad crops the image around the board with padding, undistorted', async () => {
  const geometryCalls = [];
  const client = makeClient({
    geometryImpl: async (reviewItemId, options) => {
      geometryCalls.push({ options, reviewItemId });
      return { data: { geometry: { sourceQuad: quad } } };
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspace(client);

  await eventually(() => geometryCalls.length === 1, 'geometry should be fetched');
  assert.equal(geometryCalls[0].reviewItemId, 'review-10');
  assert.deepEqual(geometryCalls[0].options, { gameId, importJobId: 'job-10' });

  await fireImageLoad(boardImage(), 1000, 600);

  await eventually(
    () => document.querySelector('.boardSearchBoardAssetFrame') !== null,
    'crop frame should render once geometry and image size are both known',
  );
  const frame = document.querySelector('.boardSearchBoardAssetFrame');
  const croppedImage = document.querySelector('.boardSearchBoardAssetCropped');
  assert.ok(croppedImage);

  // board bbox: 200x200 at (100, 200); 20% padding -> 40 each side
  const paddedWidth = 200 + 2 * 40;
  const paddedHeight = 200 + 2 * 40;
  const cropX = 100 - 40;
  const cropY = 200 - 40;
  assert.equal(frame.style.aspectRatio, `${paddedWidth} / ${paddedHeight}`);
  assert.equal(
    croppedImage.style.width,
    `${(1000 / paddedWidth) * 100}%`,
  );
  assert.equal(
    croppedImage.style.height,
    `${(600 / paddedHeight) * 100}%`,
  );
  assert.equal(
    croppedImage.style.left,
    `${(-cropX / paddedWidth) * 100}%`,
  );
  assert.equal(
    croppedImage.style.top,
    `${(-cropY / paddedHeight) * 100}%`,
  );

  await act(async () => root.unmount());
});

test('missing or invalid geometry falls back to the full, uncropped image', async () => {
  const client = makeClient({
    geometryImpl: async () => ({ data: { geometry: {} } }),
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspace(client);

  await settle();
  await fireImageLoad(boardImage(), 1000, 600);
  await settle();

  assert.equal(document.querySelector('.boardSearchBoardAssetFrame'), null);
  assert.ok(document.querySelector('.boardSearchBoardAsset'));

  await act(async () => root.unmount());
});

test('a failed geometry fetch never blocks the search result; the full image still renders', async () => {
  const client = makeClient({
    geometryImpl: async () => {
      throw new Error('network down');
    },
    searchImpl: async () => ({ data: { results: [boardResult(10)] } }),
  });
  const root = await renderWorkspace(client);

  await settle();
  await fireImageLoad(boardImage(), 1000, 600);
  await settle();

  assert.equal(document.querySelector('.boardSearchBoardAssetFrame'), null);
  assert.ok(document.querySelector('.boardSearchBoardAsset'));
  assert.equal(document.querySelector('.boardSearchBoardAssetError'), null);

  await act(async () => root.unmount());
});

test('legacy_archive results never fetch board geometry', async () => {
  const geometryCalls = [];
  const client = makeClient({
    geometryImpl: async (...args) => {
      geometryCalls.push(args);
      return { data: { geometry: { sourceQuad: quad } } };
    },
    searchImpl: async () => ({
      data: {
        results: [
          boardResult(10, {
            assetMode: 'legacy_archive',
            importJobId: null,
            recognizedBoardId: null,
            reviewItemId: null,
          }),
        ],
      },
    }),
  });
  const root = await renderWorkspace(client);

  await settle();
  await fireImageLoad(boardImage(), 1000, 600);
  await settle();

  assert.equal(geometryCalls.length, 0);
  assert.equal(document.querySelector('.boardSearchBoardAssetFrame'), null);

  await act(async () => root.unmount());
});

test('switching to the next result replaces the crop instead of keeping the previous board geometry', async () => {
  const quadForSequence = {
    10: quad,
    19: [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
      { x: 100, y: 50 },
      { x: 0, y: 50 },
    ],
  };
  const client = makeClient({
    geometryImpl: async (reviewItemId) => {
      const sequenceNumber = Number(reviewItemId.split('-')[1]);
      return { data: { geometry: { sourceQuad: quadForSequence[sequenceNumber] } } };
    },
    searchImpl: async () => ({
      data: { results: [boardResult(10), boardResult(19)] },
    }),
  });
  const root = await renderWorkspace(client);

  await settle();
  await fireImageLoad(boardImage(), 1000, 600);
  await eventually(
    () => document.querySelector('.boardSearchBoardAssetFrame') !== null,
    'first board crop should render',
  );
  const firstFrame = document.querySelector('.boardSearchBoardAssetFrame');
  const firstAspectRatio = firstFrame.style.aspectRatio;

  await click(
    [...document.querySelectorAll('button')].find((node) =>
      node.textContent.includes('Następna'),
    ),
  );
  await settle();
  // The carousel remounts BoardCrop for the new board (key change), so the
  // old crop frame must disappear until the new board's own image loads.
  assert.equal(document.querySelector('.boardSearchBoardAssetFrame'), null);

  await fireImageLoad(boardImage(), 1000, 600);
  await eventually(
    () => document.querySelector('.boardSearchBoardAssetFrame') !== null,
    'second board crop should render',
  );
  const secondFrame = document.querySelector('.boardSearchBoardAssetFrame');
  assert.notEqual(secondFrame.style.aspectRatio, firstAspectRatio);

  await act(async () => root.unmount());
});
