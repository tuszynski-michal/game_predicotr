import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APPROXIMATE_WIN_DEFAULT_DISPLAY,
  APPROXIMATE_WIN_DISPLAY_STORAGE_KEY,
  APPROXIMATE_WIN_STAKES_GROSZE,
  approximateWinDisplayValue,
  approximateWinStakeMultiplier,
  approximateWinStakeOptions,
  effectiveApproximateWinStakeGrosze,
  formatApproximateWinAmount,
  loadApproximateWinDisplay,
  roundDivideHalfAwayFromZero,
  saveApproximateWinDisplay,
  scaleApproximateWinAmount,
} from '../src/board-search-stake.ts';

const stake = (grosze, unit = 'credits') => ({ stakeGrosze: grosze, unit });
const text = (credits, display, spinCost = 100) =>
  formatApproximateWinAmount(
    scaleApproximateWinAmount(credits, display, spinCost),
    display.unit,
  );

test('the stake list is the closed list from D-470', () => {
  assert.deepEqual(
    APPROXIMATE_WIN_STAKES_GROSZE,
    [120, 200, 400, 600, 1000, 2000],
  );
});

test('R1 examples: stake scales payouts and the spin cost linearly', () => {
  assert.equal(
    text(10_000, stake(1000, 'pln')),
    '1000,00 zł'.replace('1000', (1000).toLocaleString('pl-PL')),
  );
  assert.equal(
    text(10_000, stake(600, 'pln')),
    `${(600).toLocaleString('pl-PL')},00 zł`,
  );
  assert.equal(text(10_000, stake(600)), (6000).toLocaleString('pl-PL'));
  assert.equal(
    text(10_000, stake(2000, 'pln')),
    `${(2000).toLocaleString('pl-PL')},00 zł`,
  );
  // Operator example: 4 grapes = 1 000 credits at 10 zł and 600 at 6 zł.
  assert.equal(text(1_000, stake(1000)), (1000).toLocaleString('pl-PL'));
  assert.equal(text(1_000, stake(600)), '600');
  assert.equal(text(1_000, stake(600, 'pln')), '60,00 zł');
  assert.equal(text(5, stake(120, 'pln')), '0,06 zł');
  assert.equal(text(5, stake(120)), '0,6');
  assert.equal(text(100, stake(120, 'pln')), '1,20 zł');
  assert.equal(text(100, stake(120)), '12');
  assert.equal(text(-2_500, stake(600, 'pln')), '-150,00 zł');
});

test('the base stake with credits reproduces the previous display exactly', () => {
  for (const credits of [0, 5, 100, 1234, -17_500, 2_500_000]) {
    assert.equal(
      text(credits, APPROXIMATE_WIN_DEFAULT_DISPLAY),
      credits.toLocaleString('pl-PL'),
    );
    assert.equal(
      text(credits, APPROXIMATE_WIN_DEFAULT_DISPLAY, 20),
      credits.toLocaleString('pl-PL'),
    );
  }
});

test('roundDivideHalfAwayFromZero rounds halves away from zero without floats', () => {
  assert.equal(roundDivideHalfAwayFromZero(5, 10), 1);
  assert.equal(roundDivideHalfAwayFromZero(-5, 10), -1);
  assert.equal(roundDivideHalfAwayFromZero(4, 10), 0);
  assert.equal(roundDivideHalfAwayFromZero(-4, 10), 0);
  assert.ok(!Object.is(roundDivideHalfAwayFromZero(-4, 10), -0));
  assert.equal(roundDivideHalfAwayFromZero(600_000, 100), 6000);
  assert.throws(() => roundDivideHalfAwayFromZero(1.5, 10), RangeError);
  assert.throws(
    () => roundDivideHalfAwayFromZero(Number.MAX_SAFE_INTEGER * 2, 10),
    RangeError,
  );
});

test('a half grosz rounds once on the final value', () => {
  // spin cost 400 credits = 40 zł base; stake 1,20 zł => 1 credit = 0,3 gr.
  assert.equal(scaleApproximateWinAmount(1, stake(120), 400), 0);
  assert.equal(scaleApproximateWinAmount(5, stake(120), 400), 2); // 1,5 gr
  assert.equal(scaleApproximateWinAmount(-5, stake(120), 400), -2);
});

test('a base stake outside the list is offered as an extra "bazowa" option', () => {
  const options = approximateWinStakeOptions(25);
  assert.equal(options[0].grosze, 250);
  assert.equal(options[0].isBase, true);
  assert.equal(options.length, 7);
  assert.equal(options.filter((option) => option.isBase).length, 1);
  assert.equal(approximateWinStakeOptions(20)[1].isBase, true);
  assert.equal(approximateWinStakeOptions(100).length, 6);
  assert.match(approximateWinStakeOptions(100)[4].label, /10,00 zł \(bazowa\)/);
  const odd = approximateWinStakeOptions(35);
  assert.equal(odd.length, 7);
  assert.equal(odd[0].grosze, 350);
});

test('unknown stakes fall back to the base stake and the multiplier is shown', () => {
  assert.equal(effectiveApproximateWinStakeGrosze(stake(333), 100), 1000);
  assert.equal(effectiveApproximateWinStakeGrosze(stake(null), 100), 1000);
  assert.equal(approximateWinStakeMultiplier(stake(600), 100), '0,6');
  assert.equal(approximateWinStakeMultiplier(stake(2000), 100), '2');
  assert.equal(approximateWinStakeMultiplier(stake(null), 100), '1');
});

test('a zero spin cost keeps złote at credits / 10 and ignores the stake', () => {
  assert.equal(scaleApproximateWinAmount(1_000, stake(600, 'pln'), 0), 10_000);
  assert.equal(
    text(1_000, stake(600, 'pln'), 0),
    `${(100).toLocaleString('pl-PL')},00 zł`,
  );
  assert.equal(text(1_000, stake(600), 0), (1000).toLocaleString('pl-PL'));
});

test('display values for plotting use the chosen unit', () => {
  assert.equal(approximateWinDisplayValue(6000, 'pln'), 60);
  assert.equal(approximateWinDisplayValue(6000, 'credits'), 600);
});

test('the preference survives storage and invalid values mean defaults', () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  assert.deepEqual(
    loadApproximateWinDisplay(storage),
    APPROXIMATE_WIN_DEFAULT_DISPLAY,
  );
  saveApproximateWinDisplay(stake(600, 'pln'), storage);
  assert.deepEqual(loadApproximateWinDisplay(storage), stake(600, 'pln'));
  values.set(APPROXIMATE_WIN_DISPLAY_STORAGE_KEY, '{not json');
  assert.deepEqual(
    loadApproximateWinDisplay(storage),
    APPROXIMATE_WIN_DEFAULT_DISPLAY,
  );
  values.set(
    APPROXIMATE_WIN_DISPLAY_STORAGE_KEY,
    '{"stakeGrosze":-3,"unit":"eur"}',
  );
  assert.deepEqual(
    loadApproximateWinDisplay(storage),
    APPROXIMATE_WIN_DEFAULT_DISPLAY,
  );
  const broken = {
    getItem: () => {
      throw new Error('blocked');
    },
    setItem: () => {
      throw new Error('blocked');
    },
  };
  assert.deepEqual(
    loadApproximateWinDisplay(broken),
    APPROXIMATE_WIN_DEFAULT_DISPLAY,
  );
  assert.doesNotThrow(() => saveApproximateWinDisplay(stake(600), broken));
  assert.deepEqual(
    loadApproximateWinDisplay(null),
    APPROXIMATE_WIN_DEFAULT_DISPLAY,
  );
});

test('the stake resolution is cheap enough for every chart point', () => {
  const started = performance.now();
  for (let index = 0; index < 20_000; index += 1) {
    scaleApproximateWinAmount(index, stake(600), 100);
  }
  assert.ok(performance.now() - started < 500);
});
