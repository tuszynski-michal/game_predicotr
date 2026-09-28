import { test } from 'node:test';
import assert from 'node:assert/strict';
import { gameDisplayName } from '../src/lib/game-display-name.ts';

test('legacy snapshot IDs show the operator game names without changing identities', () => {
  assert.equal(gameDisplayName('local-8f24e7200f37e017db540839', 'blazing zd'), 'blazing');
  assert.equal(gameDisplayName('local-ca1a5075dbd40725f464d429', 'gang zd'), 'gang');
  assert.equal(gameDisplayName('local-7a0650634c7a607f30c93774', 'mumie wybrane'), 'mumie');
  assert.equal(gameDisplayName('local-d0e1a94c35b78ceb9211ee6a', 'tresure zd'), 'treasure');
});

test('other snapshots keep their own game names', () => {
  assert.equal(gameDisplayName('local-other', 'Nowa gra'), 'Nowa gra');
  assert.equal(gameDisplayName('local-other', 'treasure'), 'treasure');
});
