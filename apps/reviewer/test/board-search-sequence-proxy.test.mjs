import assert from 'node:assert/strict';
import test from 'node:test';
import { proxyBoardSearchShareRequest } from '../src/security/board-search-share-proxy.ts';
import { proxyBoardSearchPanelRequest } from '../src/security/board-search-panel-proxy.ts';
for (const panelMode of [false, true])
  test(`removed POST is blocked in ${panelMode ? 'panel' : 'share'}`, async () => {
    let calls = 0;
    const id = '11111111-1111-4111-8111-111111111111',
      secret = 'a'.repeat(43);
    const path = panelMode
      ? `/board-search-panel-api/panels/${id}/games/${id}/api/v1/board-search-shares/search`
      : '/board-search-api/api/v1/board-search-shares/search';
    const request = new Request('https://share.example' + path, {
      method: 'POST',
      headers: {
        origin: 'https://share.example',
        host: 'share.example',
        'sec-fetch-site': 'same-origin',
        'content-type': 'application/json',
        cookie: panelMode
          ? `gp_board_search_panel=${id}.${secret}`
          : `gp_board_search_token=${secret}`,
      },
      body: '{"patterns":[]}',
    });
    const result = await (
      panelMode ? proxyBoardSearchPanelRequest : proxyBoardSearchShareRequest
    )(request, {
      shareEnabled: true,
      fetchImplementation: async () => {
        calls++;
        throw new Error('must not forward');
      },
    });
    assert.ok(result.status >= 400);
    assert.equal(calls, 0);
  });
