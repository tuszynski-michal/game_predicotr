import { DomainValidationError } from './errors.js';

export const MAX_SIGNATURE_CELL_WIDTH = 5;
export const MAX_SYMBOL_MOBILE_CODE = 32_767;

function validateCellWidth(cellWidth: number): void {
  if (
    !Number.isInteger(cellWidth) ||
    cellWidth < 1 ||
    cellWidth > MAX_SIGNATURE_CELL_WIDTH
  ) {
    throw new DomainValidationError(
      'invalid_cell_width',
      `Signature cell width must be between 1 and ${MAX_SIGNATURE_CELL_WIDTH}.`,
    );
  }
}

function encodeCell(symbolCode: number, cellWidth: number): string {
  if (
    !Number.isSafeInteger(symbolCode) ||
    symbolCode < 1 ||
    symbolCode > MAX_SYMBOL_MOBILE_CODE
  ) {
    throw new DomainValidationError(
      'invalid_symbol_code',
      `Symbol code must be between 1 and ${MAX_SYMBOL_MOBILE_CODE}.`,
    );
  }

  const encoded = symbolCode.toString(10);
  if (encoded.length > cellWidth) {
    throw new DomainValidationError(
      'symbol_code_out_of_range',
      `Symbol code ${symbolCode} does not fit width ${cellWidth}.`,
    );
  }

  return encoded.padStart(cellWidth, '0');
}

export function encodeSignature(
  cells: readonly number[],
  cellWidth: number,
): string {
  validateCellWidth(cellWidth);
  return cells.map((cell) => encodeCell(cell, cellWidth)).join('');
}

export function encodeSignaturePrefix(
  cells: readonly (number | null)[],
  cellWidth: number,
): string {
  validateCellWidth(cellWidth);

  const prefix: number[] = [];
  let reachedEmptyCell = false;

  for (const cell of cells) {
    if (cell === null) {
      reachedEmptyCell = true;
      continue;
    }
    if (reachedEmptyCell) {
      throw new DomainValidationError(
        'non_prefix_board',
        'A populated cell cannot occur after an empty prefix cell.',
      );
    }
    prefix.push(cell);
  }

  return prefix.map((cell) => encodeCell(cell, cellWidth)).join('');
}

export function decodeSignature(
  signature: string,
  cellWidth: number,
  expectedCellCount?: number,
): readonly number[] {
  validateCellWidth(cellWidth);

  if (signature.length % cellWidth !== 0 || !/^[0-9]*$/.test(signature)) {
    throw new DomainValidationError(
      'invalid_signature',
      'Signature must contain complete fixed-width decimal cells.',
    );
  }

  const cellCount = signature.length / cellWidth;
  if (
    expectedCellCount !== undefined &&
    (!Number.isInteger(expectedCellCount) ||
      expectedCellCount < 0 ||
      cellCount !== expectedCellCount)
  ) {
    throw new DomainValidationError(
      'invalid_signature',
      `Signature contains ${cellCount} cells; expected ${expectedCellCount}.`,
    );
  }

  const cells: number[] = [];
  for (let offset = 0; offset < signature.length; offset += cellWidth) {
    const symbolCode = Number.parseInt(
      signature.slice(offset, offset + cellWidth),
      10,
    );
    if (!Number.isSafeInteger(symbolCode) || symbolCode < 1) {
      throw new DomainValidationError(
        'invalid_signature',
        'Signature contains an invalid symbol code.',
      );
    }
    cells.push(symbolCode);
  }

  return cells;
}
