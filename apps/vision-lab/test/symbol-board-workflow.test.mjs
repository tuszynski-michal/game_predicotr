import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import {
  boardChoices,
  boardDecision,
  boardImagesReady,
  boardOverlay,
  boardReadSession,
} from '../src/lib/symbol-board-workflow.ts';

function preview(columns = 5) {
  const dictionary = {
    version: 2,
    digest: 'dict',
    entries: [{ id: 'unknown', display_name: 'Real class' }],
  };
  return {
    kind: 'lab_board',
    revision: 7,
    topology: { columns, rows: 3 },
    dictionary,
    nodes: Array.from({ length: (columns + 1) * 4 }, (_, i) => ({
      x: (i % (columns + 1)) * 100,
      y: Math.floor(i / (columns + 1)) * 100,
    })),
    cells: Array.from({ length: columns * 3 }, (_, i) => ({
      binding: { crop_id: `crop-${i}`, cell_index: i },
      current: null,
    })),
  };
}

test('whole board restores only matching decisions and keeps explicit nonapproval separate from class IDs', () => {
  const p = preview();
  function saved(index, action, changes = {}) {
    p.cells[index].current = {
      action,
      label_valid: action === 'approve',
      symbol_id: action === 'approve' ? 'unknown' : null,
      metadata: {
        binding: p.cells[index].binding,
        dictionary_version: 2,
        dictionary_digest: 'dict',
      },
      reasons:
        action === 'approve'
          ? []
          : ['SYMBOL_NOT_APPROVED', 'SYMBOL_CLASS_UNKNOWN'],
      ...changes,
    };
  }
  saved(0, 'approve');
  saved(1, 'unknown');
  saved(2, 'unreadable');
  saved(3, 'grid_issue');
  saved(4, 'withdraw');
  saved(5, 'approve', { label_valid: false });
  saved(6, 'unknown', {
    reasons: ['SYMBOL_NOT_APPROVED', 'SYMBOL_GEOMETRY_STALE'],
  });
  saved(7, 'approve', {
    metadata: {
      dictionary_version: 1,
      dictionary_digest: 'old',
      binding: p.cells[7].binding,
    },
  });
  saved(8, 'approve', {
    metadata: {
      dictionary_version: 2,
      dictionary_digest: 'dict',
      binding: { crop_id: 'old' },
    },
  });
  assert.deepEqual(boardChoices(p).slice(0, 9), [
    'class:unknown',
    'state:unknown',
    'state:unreadable',
    'state:grid_issue',
    '',
    '',
    '',
    '',
    '',
  ]);
  const choices = Array(15).fill('class:unknown');
  choices[1] = 'state:unknown';
  const body = boardDecision(p, choices, 'stable-id');
  assert.equal(body.expected_revision, 7);
  assert.equal(body.request_id, 'stable-id');
  assert.equal(body.cells.length, 15);
  assert.deepEqual(
    body.cells.map((c) => c.binding.cell_index),
    Array.from({ length: 15 }, (_, i) => i),
  );
  assert.equal(body.cells[0].symbol_id, 'unknown');
  assert.equal(body.cells[0].action, 'approve');
  assert.equal(body.cells[1].symbol_id, null);
  assert.equal(body.cells[1].action, 'unknown');
  assert.throws(() => boardDecision(p, boardChoices(p), 'no'), /INCOMPLETE/);
  assert.throws(
    () => boardDecision(p, Array(15).fill('class:missing'), 'no'),
    /INVALID/,
  );
  assert.equal(
    boardDecision(preview(3), Array(9).fill('state:unreadable'), 'nine').cells
      .length,
    9,
  );
});

test('overlay uses actual internal nodes and row-major numbering', () => {
  const p = preview();
  p.nodes[8] = { x: 217, y: 83 };
  const overlay = boardOverlay(p);
  assert.equal(overlay.lines.length, 10);
  assert.match(overlay.lines[1], /217,83/);
  assert.match(overlay.lines[6], /217,83/);
  assert.equal(overlay.labels.length, 15);
  assert.deepEqual(overlay.labels[1], {
    index: 1,
    x: (100 + 200 + 217 + 100) / 4,
    y: (0 + 0 + 83 + 100) / 4,
  });
});

test('actual UI read token rejects late responses and old PNG events, every reread has a new image key', async () => {
  const session = boardReadSession();
  const old = session.begin();
  let finish;
  const oldResponse = new Promise((resolve) => {
    finish = resolve;
  });
  let shown = null;
  const read = oldResponse.then((value) => {
    if (session.isCurrent(old)) shown = value;
  });
  session.invalidate();
  const current = session.begin();
  finish('old');
  await read;
  assert.equal(shown, null);
  assert.equal(session.isCurrent(old), false);
  assert.equal(session.isCurrent(current), true);
  const sameBytesReread = session.begin();
  assert.notEqual(sameBytesReread, current);
  assert.equal(session.isCurrent(current), false);
  const component = await readFile(
    new URL('../src/components/symbol-board-editor.tsx', import.meta.url),
    'utf8',
  );
  assert.match(component, /key=\{previewSession\}/);
  assert.match(component, /readSession\.current\.isCurrent\(session\)/);
});

test('every shown PNG is required and one error blocks save', () => {
  const p = preview();
  const loaded = new Set([
    'board',
    ...Array.from({ length: 14 }, (_, i) => String(i)),
  ]);
  assert.equal(boardImagesReady(p, loaded, false), false);
  loaded.add('14');
  assert.equal(boardImagesReady(p, loaded, false), true);
  assert.equal(boardImagesReady(p, loaded, true), false);
  assert.equal(boardImagesReady(p, new Set(), false), false);
});
