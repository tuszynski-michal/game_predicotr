import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import test from 'node:test';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { recordingCommandKey } from '../src/features/model-quality/recording-groups-command.ts';
import { recordingRegistrationKey } from '../src/features/model-quality/recording-registration.ts';

// These mounted tests inject the narrow client. Request serialization is covered
// separately by the generated-client wrapper tests, without a live API service.
registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('/src/api/admin-api-client.ts'))
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export function createConfiguredAdminApiClient() { throw new Error("Explicit recording test client required"); }',
      };
    return nextLoad(url, context);
  },
});
const { RecordingGroupsPanel } =
  await import('../src/features/model-quality/recording-groups-panel.tsx');

const gameId = '11111111-1111-4111-8111-111111111111';
const groupId = '22222222-2222-4222-8222-222222222222';
const familyId = '33333333-3333-4333-8333-333333333333';
const manifestId = '44444444-4444-4444-8444-444444444444';
const versionId = '55555555-5555-4555-8555-555555555555';
const apiBaseUrl = 'http://127.0.0.1:8000';
const group = (extra = {}) => ({
  id: groupId,
  revision: 1,
  membershipComplete: false,
  expectedSources: 201,
  registeredSources: 0,
  manifestId,
  manifestSha256: 'a'.repeat(64),
  pageCount: 2,
  declared: false,
  independent: false,
  role: null,
  qualification: 'unresolved',
  reasonCodes: ['RECORDING_MEMBERSHIP_INCOMPLETE'],
  resolutionId: null,
  nextPageIndex: 0,
  registeredPages: 0,
  createdAt: '2026-10-15T10:00:00Z',
  importJobId: manifestId,
  ...extra,
});
function fixture(extra = {}) {
  let current = group();
  const requests = [];
  return {
    requests,
    api: {
      async listJobs(query) {
        requests.push(['jobs', query]);
        return {
          data: [
            {
              id: manifestId,
              gameId: query.gameId,
              jobType: 'import',
              createdAt: '2026-10-15T10:00:00Z',
              inputPayload: {
                importKind: 'image_directory',
                sourceDisplayName: 'Film z wtorku',
              },
              progress: { imageImport: { pipelineTotal: 201 } },
            },
          ],
        };
      },
      async getGameGridModelAssignment(game) {
        requests.push(['assignment', game]);
        return {
          data: {
            gameId: game,
            version: { manifest: { familyId, versionId } },
          },
        };
      },
      async listSourceRecordingGroups(game, query) {
        requests.push(['list', game, query]);
        return { data: { items: [current], nextCursor: null } };
      },
      async commandSourceRecordingGroups(game, command) {
        requests.push(['command', game, command]);
        const saved = JSON.parse(
          localStorage.getItem(recordingCommandKey(apiBaseUrl, game)),
        );
        assert.deepEqual(saved.command, command);
        const updates = {
          attach: {
            registeredSources: command.pageIndex === 0 ? 200 : 201,
            registeredPages: command.pageIndex + 1,
            nextPageIndex: command.pageIndex === 0 ? 1 : null,
          },
          complete: { membershipComplete: true },
          declare: { declared: true, independent: true },
          assign_role: { role: command.role },
          freeze: { resolutionId: versionId },
          retract: { declared: false, independent: false, role: null },
        };
        current = {
          ...current,
          ...updates[command.kind],
          revision: current.revision + 1,
        };
        return {
          data: {
            commandKind: command.kind,
            idempotencyKey: command.idempotencyKey,
            group: current,
            statusCode: 200,
            reasonCode: null,
            resolutionId: current.resolutionId,
          },
        };
      },
      ...extra,
    },
  };
}
async function mount(api, saved = {}) {
  const dom = new JSDOM('<div id="root"></div>', {
    url: 'http://127.0.0.1:3000',
  });
  const previous = {};
  for (const [key, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    localStorage: dom.window.localStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    previous[key] = globalThis[key];
    globalThis[key] = value;
  }
  for (const [key, value] of Object.entries(saved))
    localStorage.setItem(key, value);
  const root = createRoot(document.getElementById('root'));
  const render = async (id = gameId) =>
    act(async () =>
      root.render(
        React.createElement(RecordingGroupsPanel, {
          apiBaseUrl,
          gameId: id,
          client: api,
        }),
      ),
    );
  await render();
  return {
    render,
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      Object.assign(globalThis, previous);
    },
  };
}
const button = (label) =>
  [...document.querySelectorAll('button')].find((element) =>
    element.textContent.includes(label),
  );
async function click(label) {
  const item = button(label);
  assert.ok(item, label);
  await act(async () => item.click());
}
async function selectGroup() {
  await act(async () => {
    const select = document.querySelector('[aria-label="Nagranie"]');
    select.value = groupId;
    select.dispatchEvent(new window.Event('change', { bubbles: true }));
  });
}

test('reads only own bounded list, shows unresolved provenance and performs no automatic commands', async () => {
  const f = fixture();
  const m = await mount(f.api);
  try {
    assert.deepEqual(
      f.requests.filter((item) => item[0] !== 'jobs').map((item) => item[0]),
      ['assignment', 'list'],
    );
    assert.deepEqual(
      f.requests.find((item) => item[0] === 'list'),
      ['list', gameId, { familyId, limit: 100, after: undefined }],
    );
    assert.match(document.body.textContent, /Nierozstrzygnięte pochodzenie/);
    assert.match(document.body.textContent, /bez roli/);
    await selectGroup();
    assert.equal(button('Potwierdź kompletne').disabled, true);
    assert.equal(button('Przypisz rolę').disabled, true);
    assert.equal(button('Zapisz prowizoryczne').disabled, true);
  } finally {
    await m.cleanup();
  }
});

test('whole-recording pages, declaration, roles and provisional resolution stay separate', async () => {
  const f = fixture();
  const m = await mount(f.api);
  try {
    await selectGroup();
    await click('Zarejestruj stronę');
    assert.equal(button('Potwierdź kompletne').disabled, true);
    await click('Zarejestruj stronę');
    await click('Potwierdź kompletne');
    await act(async () =>
      [...document.querySelectorAll('input[type="checkbox"]')]
        .find((item) => item.parentElement.textContent.includes('niezależny'))
        .click(),
    );
    await click('Zapisz deklarację');
    await click('Przypisz rolę');
    await click('Zapisz prowizoryczne');
    const commands = f.requests
      .filter((item) => item[0] === 'command')
      .map((item) => item[2]);
    assert.deepEqual(
      commands.map((item) => item.kind),
      ['attach', 'attach', 'complete', 'declare', 'assign_role', 'freeze'],
    );
    assert.deepEqual(
      commands.slice(0, 2).map((item) => [item.pageIndex, item.manifestId]),
      [
        [0, manifestId],
        [1, manifestId],
      ],
    );
    assert.deepEqual(
      commands.map((item) => item.expectedRevision),
      [1, 2, 3, 4, 5, 6],
    );
    assert.equal(commands[2].manifestId, undefined);
    assert.equal(commands[3].independenceConfirmed, true);
    assert.equal(commands[4].role, 'TRAIN');
    assert.equal(commands[5].baseVersionId, versionId);
    assert.equal(commands[5].familyId, familyId);
    assert.match(
      document.body.textContent,
      /Nie zamrożono kohorty ani nie uruchomiono treningu/,
    );
  } finally {
    await m.cleanup();
  }
});

test('lost response survives reload with exact body/key and never retries automatically', async () => {
  const commands = [];
  const f = fixture({
    async commandSourceRecordingGroups(game, body) {
      assert.deepEqual(
        JSON.parse(localStorage.getItem(recordingCommandKey(apiBaseUrl, game)))
          .command,
        body,
      );
      commands.push(body);
      if (commands.length === 1) throw new Error('Lost response');
      return {
        data: {
          idempotencyKey: body.idempotencyKey,
          commandKind: body.kind,
          statusCode: 200,
          group: group({ registeredSources: 200, revision: 2 }),
        },
      };
    },
  });
  let m = await mount(f.api);
  let raw;
  try {
    await selectGroup();
    await click('Zarejestruj stronę');
    raw = localStorage.getItem(recordingCommandKey(apiBaseUrl, gameId));
    assert.ok(raw);
  } finally {
    await m.cleanup();
  }
  m = await mount(f.api, { [recordingCommandKey(apiBaseUrl, gameId)]: raw });
  try {
    assert.equal(commands.length, 1);
    assert.equal(
      button('Zarejestruj nagranie').closest('fieldset').disabled,
      true,
    );
    await click('Ponów dokładne');
    assert.deepEqual(commands[1], commands[0]);
    assert.equal(
      localStorage.getItem(recordingCommandKey(apiBaseUrl, gameId)),
      null,
    );
  } finally {
    await m.cleanup();
  }
});

test('409 preserves pending and explicit discard archives exact raw before allowing new work', async () => {
  const f = fixture({
    async commandSourceRecordingGroups() {
      return {
        error: { code: 'RECORDING_PROTECTED' },
        response: { status: 409 },
      };
    },
  });
  const m = await mount(f.api);
  try {
    await selectGroup();
    await click('Zarejestruj stronę');
    const key = recordingCommandKey(apiBaseUrl, gameId);
    const raw = localStorage.getItem(key);
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /HTTP 409/,
    );
    assert.equal(button('Zachowaj archiwum').disabled, true);
    await act(async () =>
      document.querySelector('aside input[type="checkbox"]').click(),
    );
    await click('Zachowaj archiwum');
    assert.equal(localStorage.getItem(key), null);
    const archive = Object.keys(localStorage).find((item) =>
      item.startsWith(`${key}:archive:`),
    );
    assert.equal(JSON.parse(localStorage.getItem(archive)).raw, raw);
  } finally {
    await m.cleanup();
  }
});

test('malformed stored intent blocks mutations and remains available for confirmed recovery', async () => {
  const f = fixture();
  const key = recordingCommandKey(apiBaseUrl, gameId);
  const m = await mount(f.api, { [key]: '{broken' });
  try {
    assert.equal(
      button('Zarejestruj nagranie').closest('fieldset').disabled,
      true,
    );
    assert.equal(button('Ponów dokładne'), undefined);
    assert.equal(localStorage.getItem(key), '{broken');
    await act(async () => document.querySelector('aside input').click());
    await click('Zachowaj archiwum');
    assert.equal(
      button('Zarejestruj nagranie').closest('fieldset').disabled,
      false,
    );
    assert.equal(f.requests.filter((item) => item[0] === 'command').length, 0);
  } finally {
    await m.cleanup();
  }
});

test('late list and mutation responses from the previous game do not enter the current view', async () => {
  let finishList;
  let finishCommand;
  const secondGame = '66666666-6666-4666-8666-666666666666';
  const f = fixture({
    async listSourceRecordingGroups(game) {
      return game === secondGame
        ? new Promise((resolve) => {
            finishList = resolve;
          })
        : { data: { items: [group()], nextCursor: null } };
    },
    async commandSourceRecordingGroups(_game, command) {
      return new Promise((resolve) => {
        finishCommand = () =>
          resolve({
            data: {
              idempotencyKey: command.idempotencyKey,
              commandKind: command.kind,
              statusCode: 200,
              group: group({ registeredSources: 200 }),
            },
          });
      });
    },
  });
  const m = await mount(f.api);
  try {
    await selectGroup();
    await act(async () => {
      button('Zarejestruj stronę').click();
    });
    const key = recordingCommandKey(apiBaseUrl, gameId);
    const raw = localStorage.getItem(key);
    await m.render(secondGame);
    await act(async () => finishCommand());
    assert.equal(localStorage.getItem(key), raw);
    assert.doesNotMatch(
      document.body.textContent,
      /Potwierdzono zapis nagrania/,
    );
    await m.render(gameId);
    await act(async () =>
      finishList({
        data: { items: [group({ id: secondGame })], nextCursor: null },
      }),
    );
    assert.doesNotMatch(document.body.textContent, new RegExp(secondGame));
  } finally {
    await m.cleanup();
  }
});

test('list pagination remains explicit and uses only server cursor', async () => {
  const reads = [];
  const f = fixture({
    async listSourceRecordingGroups(_game, query) {
      reads.push(query);
      return {
        data: { items: [group()], nextCursor: query.after ? null : groupId },
      };
    },
  });
  const m = await mount(f.api);
  try {
    assert.equal(reads.length, 1);
    await click('Wczytaj kolejne');
    assert.equal(reads.length, 2);
    assert.equal(reads[1].after, groupId);
    assert.equal(
      document.querySelectorAll('[aria-label="Nagranie"] option').length,
      2,
    );
  } finally {
    await m.cleanup();
  }
});

async function chooseImport() {
  const select = document.querySelector('[aria-label="Import nagrania"]');
  assert.match(select.textContent, /Film z wtorku/);
  assert.match(select.textContent, /201 zdjęć/);
  await act(async () => {
    select.value = manifestId;
    select.dispatchEvent(new window.Event('change', { bubbles: true }));
  });
  await act(async () =>
    [...document.querySelectorAll('input[type="checkbox"]')]
      .find((input) =>
        input.parentElement.textContent.includes('wybrany import'),
      )
      .click(),
  );
}

test('readable own import picker runs all membership pages through one explicit registration action', async () => {
  const f = fixture();
  const m = await mount(f.api);
  try {
    assert.deepEqual(f.requests.find((item) => item[0] === 'jobs')[1], {
      gameId,
      jobType: 'import',
      limit: 200,
    });
    await chooseImport();
    await click('Zarejestruj nagranie');
    const commands = f.requests
      .filter((item) => item[0] === 'command')
      .map((item) => item[2]);
    assert.deepEqual(
      commands.map((item) => item.kind),
      ['prepare', 'attach', 'attach', 'complete'],
    );
    assert.deepEqual(commands[0].selection, { importJobId: manifestId });
    assert.equal(
      localStorage.getItem(recordingRegistrationKey(apiBaseUrl, gameId)),
      null,
    );
    assert.match(document.body.textContent, /Zarejestrowano całe nagranie/);
    assert.equal(
      commands.some((item) =>
        ['declare', 'assign_role', 'freeze'].includes(item.kind),
      ),
      false,
    );
  } finally {
    await m.cleanup();
  }
});

test('cancel between bounded pages survives reload and explicit resume fetches the exact own group', async () => {
  const f = fixture();
  const original = f.api.commandSourceRecordingGroups;
  let finish;
  f.api.commandSourceRecordingGroups = async (game, command) => {
    const result = await original(game, command);
    return command.kind === 'attach' && command.pageIndex === 0
      ? new Promise((resolve) => {
          finish = () => resolve(result);
        })
      : result;
  };
  let m = await mount(f.api);
  let saved;
  try {
    await chooseImport();
    await click('Zarejestruj nagranie');
    await click('Zatrzymaj po bieżącej partii');
    await act(async () => finish());
    assert.deepEqual(
      f.requests
        .filter((item) => item[0] === 'command')
        .map((item) => item[2].kind),
      ['prepare', 'attach'],
    );
    saved = { ...localStorage };
  } finally {
    await m.cleanup();
  }
  m = await mount(f.api, saved);
  try {
    assert.equal(f.requests.filter((item) => item[0] === 'command').length, 2);
    await click('Wznów rejestrację');
    const point = f.requests.find(
      (item) => item[0] === 'list' && item[2].groupId,
    );
    assert.deepEqual(point, ['list', gameId, { groupId, familyId, limit: 1 }]);
    assert.deepEqual(
      f.requests
        .filter((item) => item[0] === 'command')
        .map((item) => [item[2].kind, item[2].pageIndex]),
      [
        ['prepare', undefined],
        ['attach', 0],
        ['attach', 1],
        ['complete', undefined],
      ],
    );
  } finally {
    await m.cleanup();
  }
});

test('missing authoritative membership progress stops registration without guessing source totals', async () => {
  const f = fixture();
  const original = f.api.commandSourceRecordingGroups;
  f.api.commandSourceRecordingGroups = async (game, command) => {
    const result = await original(game, command);
    delete result.data.group.nextPageIndex;
    return result;
  };
  const m = await mount(f.api);
  try {
    await chooseImport();
    await click('Zarejestruj nagranie');
    assert.equal(f.requests.filter((item) => item[0] === 'command').length, 1);
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /potwierdzonego postępu/,
    );
    assert.ok(
      localStorage.getItem(recordingRegistrationKey(apiBaseUrl, gameId)),
    );
  } finally {
    await m.cleanup();
  }
});

test('late imports from the previous game never become options of the selected game', async () => {
  let finish;
  const secondGame = '66666666-6666-4666-8666-666666666666';
  const f = fixture({
    async listJobs(query) {
      return query.gameId === gameId
        ? new Promise((resolve) => {
            finish = resolve;
          })
        : { data: [] };
    },
  });
  const m = await mount(f.api);
  try {
    assert.match(document.body.textContent, /Odczytywanie importów tej gry/);
    await m.render(secondGame);
    await act(async () =>
      finish({
        data: [
          {
            id: manifestId,
            gameId,
            jobType: 'import',
            createdAt: '2026-10-15T10:00:00Z',
            inputPayload: {
              importKind: 'image_directory',
              sourceDisplayName: 'Obcy film',
            },
            progress: {},
          },
        ],
      }),
    );
    assert.doesNotMatch(document.body.textContent, /Obcy film/);
    assert.match(document.body.textContent, /Brak importów zdjęć tej gry/);
  } finally {
    await m.cleanup();
  }
});

test('registration replays an ambiguous page with its original key after reload', async () => {
  const f = fixture();
  const original = f.api.commandSourceRecordingGroups;
  const receipts = new Map();
  const sent = [];
  let lost = false;
  f.api.commandSourceRecordingGroups = async (game, command) => {
    sent.push(command);
    if (receipts.has(command.idempotencyKey))
      return receipts.get(command.idempotencyKey);
    const result = await original(game, command);
    receipts.set(command.idempotencyKey, result);
    if (command.kind === 'attach' && !lost) {
      lost = true;
      throw new Error('Lost attach response');
    }
    return result;
  };
  let m = await mount(f.api);
  let saved;
  try {
    await chooseImport();
    await click('Zarejestruj nagranie');
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /Lost attach response/,
    );
    saved = { ...localStorage };
  } finally {
    await m.cleanup();
  }
  m = await mount(f.api, saved);
  try {
    assert.equal(sent.length, 2);
    await click('Wznów rejestrację');
    assert.deepEqual(sent[2], sent[1]);
    assert.deepEqual(
      sent.map((command) => command.kind),
      ['prepare', 'attach', 'attach', 'attach', 'complete'],
    );
    assert.equal(
      localStorage.getItem(recordingRegistrationKey(apiBaseUrl, gameId)),
      null,
    );
  } finally {
    await m.cleanup();
  }
});

test('import picker pages bounded own jobs locally without loading foreign options', async () => {
  let reads = 0;
  const job = (index, game = gameId) => ({
    id: `77777777-7777-4777-8777-${String(index).padStart(12, '0')}`,
    gameId: game,
    jobType: 'import',
    createdAt: '2026-10-15T10:00:00Z',
    inputPayload: {
      importKind: 'image_directory',
      sourceDisplayName: game === gameId ? `Nagranie ${index}` : 'Obca nazwa',
    },
    progress: { imageImport: { pipelineTotal: index } },
  });
  const f = fixture({
    async listJobs() {
      reads++;
      return {
        data: [
          ...Array.from({ length: 21 }, (_, index) => job(index)),
          job(99, familyId),
        ],
      };
    },
  });
  const m = await mount(f.api);
  try {
    assert.equal(
      document.querySelectorAll('[aria-label="Import nagrania"] option').length,
      21,
    );
    assert.doesNotMatch(document.body.textContent, /Obca nazwa/);
    await click('Następna strona importów');
    assert.equal(
      document.querySelectorAll('[aria-label="Import nagrania"] option').length,
      2,
    );
    assert.equal(reads, 1);
    assert.match(document.body.textContent, /Strona importów 2 z 2/);
  } finally {
    await m.cleanup();
  }
});

test('automatic membership stops on page conflict and keeps the exact outstanding command', async () => {
  const f = fixture();
  const original = f.api.commandSourceRecordingGroups;
  const sent = [];
  f.api.commandSourceRecordingGroups = async (game, command) => {
    sent.push(command);
    return command.kind === 'attach'
      ? {
          error: { code: 'RECORDING_SOURCE_IDENTITY_DRIFT' },
          response: { status: 409 },
        }
      : original(game, command);
  };
  const m = await mount(f.api);
  try {
    await chooseImport();
    await click('Zarejestruj nagranie');
    assert.deepEqual(
      sent.map((item) => item.kind),
      ['prepare', 'attach'],
    );
    assert.deepEqual(
      JSON.parse(localStorage.getItem(recordingCommandKey(apiBaseUrl, gameId)))
        .command,
      sent[1],
    );
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /HTTP 409/,
    );
    assert.ok(
      localStorage.getItem(recordingRegistrationKey(apiBaseUrl, gameId)),
    );
  } finally {
    await m.cleanup();
  }
});

test('missing assigned family does not fabricate a role or permit resolution', async () => {
  const f = fixture({
    async getGameGridModelAssignment() {
      return { data: { gameId, version: null } };
    },
  });
  const m = await mount(f.api);
  try {
    await selectGroup();
    assert.match(document.body.textContent, /Brak potwierdzonej rodziny/);
    assert.equal(button('Przypisz rolę').disabled, true);
    assert.equal(button('Zapisz prowizoryczne').disabled, true);
  } finally {
    await m.cleanup();
  }
});

test('failed durable write prevents POST and leaves the form recoverable', async () => {
  const f = fixture();
  const m = await mount(f.api);
  try {
    await selectGroup();
    const prototype = Object.getPrototypeOf(localStorage);
    const original = prototype.setItem;
    prototype.setItem = () => {
      throw new Error('Storage quota');
    };
    try {
      await click('Zarejestruj stronę');
      assert.match(
        document.querySelector('[role="alert"]').textContent,
        /Storage quota/,
      );
      assert.equal(
        f.requests.filter((item) => item[0] === 'command').length,
        0,
      );
    } finally {
      prototype.setItem = original;
    }
    await click('Zarejestruj stronę');
    assert.equal(f.requests.filter((item) => item[0] === 'command').length, 1);
  } finally {
    await m.cleanup();
  }
});

test('an unrelated receipt cannot clear pending intent or publish its group', async () => {
  const foreignGroup = '66666666-6666-4666-8666-666666666666';
  const f = fixture({
    async commandSourceRecordingGroups(_game, command) {
      return {
        data: {
          idempotencyKey: command.idempotencyKey,
          commandKind: command.kind,
          statusCode: 200,
          group: group({ id: foreignGroup }),
        },
      };
    },
  });
  const m = await mount(f.api);
  try {
    await selectGroup();
    await click('Zarejestruj stronę');
    assert.match(
      document.querySelector('[role="alert"]').textContent,
      /nie potwierdza/,
    );
    assert.ok(localStorage.getItem(recordingCommandKey(apiBaseUrl, gameId)));
    assert.doesNotMatch(document.body.textContent, new RegExp(foreignGroup));
  } finally {
    await m.cleanup();
  }
});
