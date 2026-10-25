import assert from 'node:assert/strict';
import test from 'node:test';
import { proxyBoardSearchShareRequest } from '../src/security/board-search-share-proxy.ts';
import { proxyBoardSearchPanelRequest } from '../src/security/board-search-panel-proxy.ts';

const origin = 'https://share.trycloudflare.com';
const panel = '11111111-1111-4111-8111-111111111111';
const child = '22222222-2222-4222-8222-222222222222';
const secret = 'a'.repeat(43);

function request(panelMode, length, suffix = 'search', streamed = false) {
  const path = panelMode
    ? `/board-search-panel-api/panels/${panel}/games/${child}/api/v1/board-search-shares/${suffix}`
    : `/board-search-api/api/v1/board-search-shares/${suffix}`;
  const body = ' '.repeat(length - 2) + '{}';
  return new Request(origin + path, {
    method: 'POST',
    headers: {
      host: 'share.trycloudflare.com',
      origin,
      'sec-fetch-site': 'same-origin',
      'content-type': 'application/json',
      cookie: panelMode
        ? `gp_board_search_panel=${panel}.${secret}`
        : `gp_board_search_token=${secret}`,
    },
    body: streamed
      ? new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(body.slice(0, 4000)));
            controller.enqueue(new TextEncoder().encode(body.slice(4000)));
            controller.close();
          },
        })
      : body,
    ...(streamed ? { duplex: 'half' } : {}),
  });
}

for (const panelMode of [false, true]) {
  const proxy = panelMode
    ? proxyBoardSearchPanelRequest
    : proxyBoardSearchShareRequest;
  test(`${panelMode ? 'panel' : 'single'} sequence alone permits a bounded 32 KiB body`, async () => {
    let calls = 0;
    const options = {
      shareEnabled: true,
      fetchImplementation: async (url, init) => {
        calls++;
        assert.equal(init.method, 'POST');
        assert.equal(new Uint8Array(init.body).length, 32000);
        return Response.json({ patternCount: 4, results: [] });
      },
    };
    assert.equal((await proxy(request(panelMode, 32000), options)).status, 200);
    assert.equal(
      (await proxy(request(panelMode, 32769, 'search', true), options)).status,
      413,
    );
    assert.equal(
      (
        await proxy(
          request(panelMode, 5000, 'boards/1/cells/0/decision'),
          options,
        )
      ).status,
      413,
    );
    assert.equal(
      (await proxy(request(panelMode, 5000, 'search?limit=2'), options)).status,
      403,
    );
    assert.equal(calls, 1);
  });
  test(`${panelMode ? 'panel' : 'single'} sequence refuses nested internal IDs`, async () => {
    const result = await proxy(request(panelMode, 30), {
      shareEnabled: true,
      fetchImplementation: async () =>
        Response.json({ results: [{ boards: [{ reviewItemId: 'secret' }] }] }),
    });
    assert.equal(result.status, 502);
  });
}
