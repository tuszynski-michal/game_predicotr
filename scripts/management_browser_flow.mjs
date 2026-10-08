const server = backend({ existing: false, locked: true });
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
  window.layoutChecks.push({
    stage,
    width: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
  });
  window.stageRequest = stage;
  return new Promise((resolve) => {
    window.layoutResolve = () => {
      window.stageRequest = null;
      resolve();
    };
  });
}
window.layoutChecks = [];
window.acceptance = (async () => {
  await until(() => document.querySelector('form'));
  await checkLayout('gate');
  await input(document.querySelector('input'), 'ABCD-EFGH');
  await touch(button('Otwórz panel'));
  await until(() => button('Dodaj punkt'));
  await touch(button('Dodaj punkt'));
  const pointForm = document.querySelector('form[aria-label="Edycja punktu"]');
  for (const [i, v] of ['Punkt', 'Miasto', 'Ulica'].entries())
    await input(pointForm.querySelectorAll('input')[i], v);
  await touch(button('Zapisz', pointForm));
  await until(() => document.querySelector('.management-tile > button'));
  await checkLayout('point');
  await touch(document.querySelector('.management-tile > button'));
  await touch(button('Dodaj maszynę'));
  const machineForm = document.querySelector(
    'form[aria-label="Edycja maszyny"]',
  );
  await input(machineForm.querySelector('input'), 'Maszyna');
  await touch(button('Zapisz', machineForm));
  await until(() => document.querySelector('fieldset input'));
  // Checkbox label is the browser's full touch target.
  await touch(document.querySelector('fieldset input').closest('label'));
  await touch(button('Otwórz gry maszyny Maszyna'));
  await until(
    () =>
      document.querySelectorAll('.management-stake-cards article').length === 6,
  );
  await checkLayout('six-stakes');
  const card = () => document.querySelector('.management-stake-cards article');
  await touch(button('Wyszukaj układ', card()));
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
  await touch(button('Zapisz układ'));
  await until(() => server.entries.length === 1);
  if (server.slots[0].empty || !server.slots[1].empty)
    throw Error('Stakes not independent');
  await touch(button('Otwórz', card()));
  await until(() =>
    document.body.textContent.includes('Ostatni zapisany wynik'),
  );
  document
    .querySelector('.management-result')
    .scrollIntoView({ behavior: 'instant' });
  await checkLayout('result-history');
  await touch(button('Wyczyść', card()));
  await until(() => server.entries.length === 2);
  if (!server.slots[0].empty || server.entries[1].action !== 'stake.clear')
    throw Error('Clear failed');
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
