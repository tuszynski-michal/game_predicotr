import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  DomainValidationError,
  decodeSignature,
  encodeSignature,
  encodeSignaturePrefix,
  validateBoardPrefix,
  validateFullBoard,
  validateGameConfig,
  validatePaylines,
  validatePayoutRules,
  validatePayoutSymbols,
} from '../dist/index.js';

const fixturePath = new URL(
  '../../domain-fixtures/domain-contract-cases.json',
  import.meta.url,
);
const fixture = JSON.parse(await readFile(fixturePath, 'utf8'));

function assertDomainError(expectedCode, callback) {
  assert.throws(
    callback,
    (error) =>
      error instanceof DomainValidationError && error.code === expectedCode,
  );
}

test('fixed-width signature golden cases encode and decode', () => {
  const { cellWidth, fullCases } = fixture.signatureCodec;

  for (const testCase of fullCases) {
    const signature = encodeSignature(testCase.cells, cellWidth);
    assert.equal(signature, testCase.expected, testCase.name);
    assert.deepEqual(
      decodeSignature(signature, cellWidth, testCase.cells.length),
      testCase.cells,
      testCase.name,
    );
  }

  assert.notEqual(fullCases[1].expected, fullCases[2].expected);
});

test('signature prefix golden cases are deterministic', () => {
  const { cellWidth, prefixCases } = fixture.signatureCodec;

  for (const testCase of prefixCases) {
    assert.equal(
      encodeSignaturePrefix(testCase.cells, cellWidth),
      testCase.expected,
      testCase.name,
    );
  }
});

test('signature codec reports stable validation codes', () => {
  for (const testCase of fixture.signatureCodec.invalidEncodeCases) {
    assertDomainError(testCase.errorCode, () => {
      if (testCase.prefix === true) {
        encodeSignaturePrefix(testCase.cells, testCase.cellWidth);
      } else {
        encodeSignature(testCase.cells, testCase.cellWidth);
      }
    });
  }

  for (const testCase of fixture.signatureCodec.invalidDecodeCases) {
    assertDomainError(testCase.errorCode, () =>
      decodeSignature(
        testCase.signature,
        testCase.cellWidth,
        testCase.expectedCellCount,
      ),
    );
  }
});

test('valid shared game, board, paylines and payout rules pass validation', () => {
  const validation = fixture.validation;

  validateGameConfig(validation.game);
  validateFullBoard(validation.fullBoard, validation.game);
  validateBoardPrefix(validation.validPrefix, validation.game);
  validatePaylines(validation.validPaylines, validation.game);
  validatePayoutSymbols(validation.validPayoutSymbols, validation.game);
  validatePayoutRules(
    validation.validPayoutRules,
    validation.validPayoutSymbols,
    validation.game,
  );
});

test('invalid game configuration reports shared error codes', () => {
  for (const testCase of fixture.validation.invalidGamePatches) {
    assertDomainError(testCase.errorCode, () =>
      validateGameConfig({ ...fixture.validation.game, ...testCase.patch }),
    );
  }
});

test('invalid board prefixes report shared error codes', () => {
  for (const testCase of fixture.validation.invalidPrefixes) {
    assertDomainError(testCase.errorCode, () =>
      validateBoardPrefix(testCase.cells, fixture.validation.game),
    );
  }
});

test('invalid full boards report shared error codes', () => {
  for (const testCase of fixture.validation.invalidFullBoards) {
    assertDomainError(testCase.errorCode, () =>
      validateFullBoard(testCase.cells, fixture.validation.game),
    );
  }
});

test('invalid paylines report shared error codes', () => {
  const game = fixture.validation.game;

  for (const testCase of fixture.validation.invalidPaylines) {
    assertDomainError(testCase.errorCode, () =>
      validatePaylines(testCase.paylines, game),
    );
  }
});

test('invalid payout rules report shared error codes', () => {
  const game = fixture.validation.game;
  const payoutSymbols = fixture.validation.validPayoutSymbols;

  for (const testCase of fixture.validation.invalidPayoutRules) {
    assertDomainError(testCase.errorCode, () =>
      validatePayoutRules(testCase.rules, payoutSymbols, game),
    );
  }
});

test('invalid payout symbol configuration reports shared error codes', () => {
  const game = fixture.validation.game;

  for (const testCase of fixture.validation.invalidPayoutSymbols) {
    assertDomainError(testCase.errorCode, () =>
      validatePayoutSymbols(testCase.payoutSymbols, game),
    );
  }
});
