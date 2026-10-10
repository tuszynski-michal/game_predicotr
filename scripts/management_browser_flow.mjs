const scenario = new URLSearchParams(location.search).get('scenario') ?? 'flow';
const server = backend({ existing: true, locked: scenario === 'flow' });
if (scenario !== 'flow') {
  const count = Number(scenario);
  if (![1, 4, 40].includes(count)) throw Error('Unsupported fixture size');
  const original = server.points[0];
  const machines = Array.from({ length: 40 }, (_, index) => ({
    ...original.machines[0],
    id: index ? `machine-${index}` : 'machine',
    name: `Maszyna ${index + 1}`,
  }));
  server.points = Array.from({ length: count }, (_, index) => ({
    ...original,
    id: index ? `point-${index}` : 'point',
    name: `Punkt ${index + 1}`,
    machines,
  }));
  server.activeGames = Array.from({ length: 200 }, (_, index) => ({
    id: index ? `game-${index}` : 'game',
    name: `Gra ${index + 1}`,
  }));
}
const baseFetch = server.fetch;
server.fetch = async (request) => {
  const path = new URL(request.url).pathname.replace(
    '/management-api/api/v1/management-public',
    '',
  );
  const body = request.method === 'GET' ? null : await request.clone().json();
  const structural =
    /^\/points\/([^/]+)(?:\/machines\/([^/]+))?\/(delete-preview|delete)$/.exec(
      path,
    );
  if (structural) {
    const [, pointId, machineId, action] = structural;
    server.calls.push({
      path,
      method: request.method,
      body,
      session: request.headers.get('X-Management-Session'),
    });
    const point = server.points.find((item) => item.id === pointId);
    const machine = point?.machines.find((item) => item.id === machineId);
    const target = machineId ? machine : point;
    const json = (value, status = 200) =>
      new Response(JSON.stringify(value), {
        status,
        headers: { 'Content-Type': 'application/json' },
      });
    if (!target) return json({ code: 'MANAGEMENT_NOT_FOUND' }, 404);
    if (body.expectedRevision !== target.revision)
      return json({ code: 'MANAGEMENT_REVISION_CONFLICT' }, 409);
    const counts = {
      points: machineId ? 0 : 1,
      machines: machineId ? 1 : point.machines.length,
      assignments: 1,
      slots: 1,
      searchContexts: 1,
      journalEntries: server.entries.length,
    };
    if (action === 'delete-preview')
      return json({
        counts,
        previewToken: 'p'.repeat(43),
        expiresAt: '2099-01-01T00:00:00Z',
      });
    if (!body.confirmed || body.previewToken !== 'p'.repeat(43))
      return json({ code: 'MANAGEMENT_PREVIEW_CONFLICT' }, 409);
    if (machineId)
      point.machines = point.machines.filter((item) => item.id !== machineId);
    else server.points = server.points.filter((item) => item.id !== pointId);
    return json({
      deleted: true,
      operationId: body.operationId,
      pointId,
      machineId: machineId ?? null,
      counts,
    });
  }
  const response = await baseFetch(request);
  if (path.endsWith('/search') && response.ok) {
    const payload = await response.json();
    payload.search.results.push({
      ...payload.search.results[0],
      sequenceNumber: 10,
    });
    return new Response(JSON.stringify(payload), {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  if (/\/stakes\/\d+$/.test(path) && request.method === 'PUT' && response.ok) {
    const stake = Number(path.split('/').at(-1));
    server.slots = server.slots.map((item) =>
      item.stakeGrosze === stake
        ? { ...item, startSequenceNumber: body.startSequenceNumber }
        : item,
    );
    return new Response(
      JSON.stringify(server.slots.find((item) => item.stakeGrosze === stake)),
      {
        status: response.status,
        headers: { 'Content-Type': 'application/json' },
      },
    );
  }
  return response;
};
const adapter = createManagementPublicAdapter({
  sessionId,
  fetchImplementation: server.fetch,
});
// Only the bitmap asset is a fixture. Session-bound URL behavior has separate request tests.
const originalForMachine = adapter.forMachine;
adapter.forMachine = (machine) => ({
  ...originalForMachine(machine),
  symbolImageAssetUrl: () =>
    'data:image/svg+xml,' +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><rect width="48" height="48" fill="#132238"/><circle cx="24" cy="24" r="12" fill="#70e1b4"/></svg>',
    ),
});
createRoot(document.getElementById('root')).render(
  React.createElement(ManagementGate, { sessionId, adapter }),
);
const pause = () => new Promise((r) => setTimeout(r, 30));
const button = (label, within = document) =>
  [...within.querySelectorAll('button')].find(
    (n) => n.textContent.trim() === label,
  );
async function until(predicate) {
  for (let i = 0; i < 200; i++) {
    if (predicate()) return;
    await pause();
  }
  throw Error('Missing ' + document.body.textContent.slice(-600));
}
async function touch(node) {
  if (!node) throw Error('Missing touch target');
  node.scrollIntoView({ block: 'center', behavior: 'instant' });
  await pause();
  const rect = node.getBoundingClientRect();
  // Allow only subpixel layout rounding around the 44px touch requirement.
  if (rect.height < 44 - 0.1)
    throw Error(
      'Touch target shorter than44: ' + node.textContent + ' ' + rect.height,
    );
  window.touchRequest = {
    x: rect.x + rect.width / 2,
    y: rect.y + rect.height / 2,
  };
  await new Promise((r) => (window.touchResolve = r));
  window.touchRequest = null;
  await pause();
}
async function input(node, value) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(
    node,
    String(value),
  );
  node.dispatchEvent(new Event('input', { bubbles: true }));
  await pause();
}
function checkLayout(stage) {
  if (document.documentElement.scrollWidth > window.innerWidth + 1)
    throw Error(
      'Horizontal overflow ' +
        stage +
        ': ' +
        document.documentElement.scrollWidth +
        '/' +
        innerWidth,
    );
  const tileGrid = document.querySelector('.management-tiles');
  const gridColumns = tileGrid
    ? getComputedStyle(tileGrid).gridTemplateColumns.split(' ').length
    : 0;
  const workspace = document.querySelector('.management-workspace');
  const workspaceStyle = workspace ? getComputedStyle(workspace) : null;
  const containerWidth = workspace
    ? workspace.clientWidth -
      parseFloat(workspaceStyle.paddingLeft) -
      parseFloat(workspaceStyle.paddingRight)
    : innerWidth;
  if (
    tileGrid &&
    gridColumns !==
      (containerWidth >= 1000
        ? 4
        : containerWidth >= 750
          ? 3
          : containerWidth >= 500
            ? 2
            : 1)
  )
    throw Error('Wrong grid columns at ' + stage + ': ' + gridColumns);
  if (document.querySelector('button button'))
    throw Error('Nested buttons at ' + stage);
  for (const node of document.querySelectorAll('.management-tile button')) {
    if (node.getBoundingClientRect().height < 43.9)
      throw Error('Tile control shorter than 44px at ' + stage);
  }
  for (const tile of document.querySelectorAll('.management-tile')) {
    const bounds = tile.getBoundingClientRect();
    const choice = tile.matches('button')
      ? tile
      : tile.querySelector('.management-tile-choice');
    const name = choice?.querySelector('strong');
    if (name) {
      const content = name.getBoundingClientRect();
      if (content.left - bounds.left < 15.9 || content.top - bounds.top < 15.9)
        throw Error('Tile content touches the edge at ' + stage);
    }
    const controls = tile.querySelector('.management-tile-controls');
    if (controls) {
      const actions = controls.getBoundingClientRect();
      if (
        actions.top - bounds.top < 15.9 ||
        bounds.right - actions.right < 15.9
      )
        throw Error('Tile controls touch the edge at ' + stage);
      if (name && name.getBoundingClientRect().right > actions.left - 8)
        throw Error('Tile name overlaps controls at ' + stage);
    }
  }
  window.layoutChecks.push({
    stage,
    width: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    tileCount: document.querySelectorAll('.management-tiles > .management-tile')
      .length,
    maxTileWidth: Math.max(
      0,
      ...[
        ...document.querySelectorAll('.management-tiles > .management-tile'),
      ].map((node) => node.getBoundingClientRect().width),
    ),
    gridColumns,
    containerWidth,
  });
  if (window.layoutChecks.at(-1).maxTileWidth > 320.5)
    throw Error(
      'Tile wider than 320px at ' +
        stage +
        ': ' +
        window.layoutChecks.at(-1).maxTileWidth,
    );
  window.stageRequest = stage;
  return new Promise((resolve) => {
    window.layoutResolve = () => {
      window.stageRequest = null;
      resolve();
    };
  });
}
window.layoutChecks = [];
async function checkStructureModal(label, stage) {
  await touch(button(label));
  await until(() => document.querySelector('.management-modal'));
  const modal = document.querySelector('.management-modal');
  const bounds = modal.getBoundingClientRect();
  const viewportWidth = document.documentElement.clientWidth;
  const viewportHeight = document.documentElement.clientHeight;
  if (
    Math.abs(bounds.x + bounds.width / 2 - viewportWidth / 2) > 2 ||
    Math.abs(bounds.y + bounds.height / 2 - viewportHeight / 2) > 2
  )
    throw Error(
      'Structure modal not centered: ' +
        stage +
        ' ' +
        JSON.stringify({
          x: bounds.x,
          y: bounds.y,
          width: bounds.width,
          height: bounds.height,
          viewportWidth,
          viewportHeight,
          scrollY,
          position: getComputedStyle(modal).position,
        }),
    );
  if (bounds.x < 0 || bounds.right > viewportWidth + 1)
    throw Error('Structure modal outside viewport: ' + stage);
  const name = modal.querySelector('input:not([type="checkbox"])');
  const style = getComputedStyle(modal);
  const available =
    modal.clientWidth -
    parseFloat(style.paddingLeft) -
    parseFloat(style.paddingRight);
  if (Math.abs(name.getBoundingClientRect().width - available) > 4)
    throw Error('Name input does not use modal width: ' + stage);
  const nameStyle = getComputedStyle(name);
  if (
    parseFloat(nameStyle.paddingLeft) < 8 ||
    parseFloat(nameStyle.borderTopWidth) < 1 ||
    parseFloat(nameStyle.borderTopLeftRadius) < 1 ||
    nameStyle.backgroundColor === 'rgba(0, 0, 0, 0)'
  )
    throw Error('Name input lost the panel theme: ' + stage);
  await checkLayout(stage);
  await touch(button('Anuluj', modal));
  await until(() => !document.querySelector('.management-modal'));
}
window.acceptance = (async () => {
  if (scenario === 'flow') {
    await until(() => document.querySelector('form'));
    await checkLayout('gate');
    await input(document.querySelector('input'), 'ABCD-EFGH');
    await touch(button('Otwórz panel'));
  }
  await until(() => button('Dodaj punkt'));
  await until(() => document.querySelector('.management-tile-choice'));
  if (
    scenario !== 'flow' &&
    document.querySelectorAll('.management-tile-choice').length !==
      Number(scenario)
  )
    throw Error('Wrong point tile count');
  await checkLayout(`points-${scenario}`);
  if (innerWidth === 1440 && scenario === '4') {
    const workspace = document.querySelector('.management-workspace');
    const previousWidth = workspace.style.width;
    const style = getComputedStyle(workspace);
    const boxAdjustment =
      style.boxSizing === 'border-box'
        ? parseFloat(style.paddingLeft) +
          parseFloat(style.paddingRight) +
          parseFloat(style.borderLeftWidth) +
          parseFloat(style.borderRightWidth)
        : 0;
    for (const size of [1000, 750, 500, 320]) {
      workspace.style.width = `${size + boxAdjustment}px`;
      await pause();
      await checkLayout(`container-${size}`);
    }
    workspace.style.width = previousWidth;
    await pause();
  }
  await checkStructureModal('Dodaj punkt', `point-modal-${scenario}`);
  await touch(document.querySelector('.management-tile-choice'));
  await until(() => button('Dodaj maszynę'));
  await checkStructureModal('Dodaj maszynę', `machine-modal-${scenario}`);
  if (scenario !== 'flow') {
    await until(
      () => document.querySelectorAll('.management-tile-choice').length === 40,
    );
    await checkLayout(`machines-${scenario}`);
    await touch(document.querySelector('.management-tile-choice'));
    await until(
      () => document.querySelectorAll('.management-stake-choice').length === 6,
    );
    await checkLayout(`stakes-${scenario}`);
    return {
      passed: true,
      scenario,
      layout: window.layoutChecks,
      points: server.points.length,
      machinesPerPoint: 40,
      activeGames: server.activeGames.length,
      touch: true,
    };
  }
  await touch(document.querySelector('.management-tile-choice'));
  await until(
    () => document.querySelectorAll('.management-stake-choice').length === 6,
  );
  await checkLayout('six-stakes');
  const card = () => document.querySelector('.management-stake-choice');
  await touch(card());
  await until(() => document.querySelector('.boardSearchPaletteGrid button'));
  await touch(
    [...document.querySelectorAll('.boardSearchPaletteGrid button')].find((n) =>
      n.textContent.includes('Wiśnia'),
    ),
  );
  await touch(button('Szukaj plansz'));
  await until(() =>
    document.querySelector(
      'input[aria-label="Zakres wygranej — liczba kolejnych spinów"]',
    ),
  );
  await checkLayout('search');
  await touch(button('Zapisz zmiany'));
  await until(() => server.entries.length === 1);
  if (server.slots[0].empty || !server.slots[1].empty)
    throw Error('Stakes not independent');
  await touch(button('Nowy układ'));
  if (server.slots[0].empty || server.entries.length !== 1)
    throw Error('Draft reset changed saved slot');
  await touch(
    [...document.querySelectorAll('.boardSearchPaletteGrid button')].find((n) =>
      n.textContent.includes('Wiśnia'),
    ),
  );
  await touch(button('Szukaj plansz'));
  await until(() =>
    [...document.querySelectorAll('.boardSearchCompactResults button')].some(
      (node) => node.textContent.includes('#10'),
    ),
  );
  await touch(
    [...document.querySelectorAll('.boardSearchCompactResults button')].find(
      (node) => node.textContent.includes('#10'),
    ),
  );
  await until(() => button('Zastąp układ'));
  await touch(button('Zastąp układ'));
  await until(() => server.entries.length === 2);
  if (server.slots[0].startSequenceNumber !== 10)
    throw Error('Replacement did not select second start');
  await touch(button('Zamknij szkic'));
  await until(() =>
    [...document.querySelectorAll('summary')].some(
      (n) => n.textContent === 'Pełny zapisany wynik',
    ),
  );
  await touch(
    [...document.querySelectorAll('summary')].find(
      (n) => n.textContent === 'Pełny zapisany wynik',
    ),
  );
  await until(() => document.querySelector('.management-result'));
  document
    .querySelector('.management-result')
    .scrollIntoView({ behavior: 'instant' });
  await checkLayout('result-history');
  await touch(card());
  await until(() => button('Usuń zapisany układ'));
  await touch(button('Usuń zapisany układ'));
  await until(() => server.entries.length === 3);
  if (!server.slots[0].empty || server.entries[2].action !== 'stake.clear')
    throw Error('Clear failed');
  if (button('Zamknij szkic')) await touch(button('Zamknij szkic'));
  await touch(button('Cofnij do maszyn'));
  await until(() =>
    document.querySelector('button[aria-label="Usuń maszynę Maszyna"]'),
  );
  await touch(
    document.querySelector('button[aria-label="Usuń maszynę Maszyna"]'),
  );
  await until(() => button('Potwierdź usunięcie'));
  await touch(button('Potwierdź usunięcie'));
  await until(() => server.points[0].machines.length === 0);
  await touch(button('Punkty'));
  await until(() =>
    document.querySelector('button[aria-label="Usuń punkt Punkt"]'),
  );
  await touch(document.querySelector('button[aria-label="Usuń punkt Punkt"]'));
  await until(() => button('Potwierdź usunięcie'));
  await touch(button('Potwierdź usunięcie'));
  await until(() => server.points.length === 0);
  if (
    !server.calls.every(
      (c) => c.session === sessionId && !c.path.includes('/admin'),
    )
  )
    throw Error('Public scope failed');
  await checkLayout('clear');
  return {
    passed: true,
    layout: window.layoutChecks,
    stakes: server.slots.length,
    events: server.entries.length,
    structuralDeletes: server.calls.filter((call) =>
      call.path.endsWith('/delete'),
    ).length,
    touch: true,
  };
})()
  .then((result) => (window.acceptanceResult = result))
  .catch(
    (error) =>
      (window.acceptanceResult = {
        passed: false,
        error: String(error),
        stack: error.stack,
      }),
  );
