import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  reviewRunId,
  preferredV7Source,
  v7ReviewUrl,
} from '../src/features/semi-automatic-image-selection/v7-review-navigation.ts';

test('an explicit existing-run link takes priority over local history without accepting arbitrary input', () => {
  const id = '6867966c-c0ee-456f-a148-452399cd66ca';
  const root =
    'http://127.0.0.1:3020/?workspace=semi-automatic-image-selection';
  assert.equal(reviewRunId(root, id), id);
  assert.equal(reviewRunId(root, null), null);
  assert.equal(reviewRunId(`${root}&semiAutomaticRunId=${id}`, 'old-run'), id);
  assert.equal(reviewRunId(`${root}&semiAutomaticRunId=not-a-run`, id), null);
});

test('reopen changes the current run and source priority preserves owners over drafts', () => {
  const url = v7ReviewUrl(
    'http://localhost:3020/?workspace=jobs&semiAutomaticRunId=old',
    'new',
  );
  assert.equal(new URL(url).searchParams.get('semiAutomaticRunId'), 'new');
  assert.equal(
    new URL(url).searchParams.get('workspace'),
    'semi-automatic-image-selection',
  );
  const row = {
    status: 'missing',
    sourceIndex: null,
    v7Review: { candidate: null, draft: { sourceIndex: 12 } },
  };
  assert.equal(preferredV7Source(row), 12);
  row.v7Review.candidate = { sourceIndex: 9 };
  assert.equal(preferredV7Source(row), 9);
  row.status = 'output_synced';
  row.sourceIndex = 4;
  assert.equal(preferredV7Source(row), 4);
});
