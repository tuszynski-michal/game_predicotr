import test from 'node:test';
import assert from 'node:assert/strict';
import { outputDirectoryName } from '../src/contracts.ts';
import { validateCreate } from '../src/native/project-controller.ts';
import { randomUUID } from 'node:crypto';

const options = {
  gameName: '777',
  gameUpdate: 'a2',
  firstLayout: 1,
  sequenceUpperBound: 500,
};
test('output directory names preserve game, update and configured range', () => {
  assert.equal(outputDirectoryName(options), '777 a2 1-500');
  assert.equal(
    outputDirectoryName({ ...options, gameUpdate: 'z_a003' }),
    '777 z_a003 1-500',
  );
  assert.equal(
    outputDirectoryName({
      ...options,
      gameName: ' Siódemki 777 ',
      sequenceUpperBound: null,
    }),
    'Siódemki 777 a2 1-500000',
  );
  assert.equal(
    outputDirectoryName({
      ...options,
      firstLayout: 499996,
      sequenceUpperBound: 500000,
    }),
    '777 a2 499996-500000',
  );
  assert.equal(
    outputDirectoryName({ ...options, gameName: 'CON' }),
    'CON a2 1-500',
  );
});
test('Windows path characters and overlong components fail before native create', () => {
  const native = {
    ...options,
    sourceToken: randomUUID(),
    direction: 'ascending',
    customLocations: false,
    localStorageConfirmed: true,
  };
  for (const gameName of [
    '../777',
    'Mumie\\777',
    '777:ads',
    '777<',
    '777>',
    '777"',
    '777|',
    '777?',
    '777*',
  ]) {
    assert.throws(() => outputDirectoryName({ ...options, gameName }), {
      code: 'INVALID_ARGUMENT',
    });
    assert.throws(() => validateCreate({ ...native, gameName }), {
      code: 'INVALID_ARGUMENT',
    });
  }
  const fixed = outputDirectoryName(options).length - options.gameUpdate.length;
  const longest = `a${'1'.repeat(255 - fixed - 1)}`;
  assert.equal(
    outputDirectoryName({ ...options, gameUpdate: longest }).length,
    255,
  );
  assert.throws(
    () => outputDirectoryName({ ...options, gameUpdate: `${longest}1` }),
    { code: 'INVALID_ARGUMENT' },
  );
  for (const changed of [
    { firstLayout: 0 },
    { firstLayout: 501 },
    { firstLayout: 1.5 },
    { sequenceUpperBound: 500001 },
    { sequenceUpperBound: NaN },
  ])
    assert.throws(() => outputDirectoryName({ ...options, ...changed }), {
      code: 'INVALID_ARGUMENT',
    });
});
