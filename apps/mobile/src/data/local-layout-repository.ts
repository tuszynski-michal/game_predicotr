import {
  decodeSignature,
  TARGET_SCAN_LIMIT_ENGINE_MIN,
  TARGET_SCAN_LIMIT_MAX,
  type GameConfig,
  type SequencePayout,
  type SymbolDefinition,
  validateFullBoard,
  validateGameConfig,
} from '@game-predictor/shared-ts';
import type { SQLiteBindParams } from 'expo-sqlite';

import { asLocalDataError, LocalDataError } from './local-data-error';

export const DEFAULT_DUPLICATE_DIAGNOSTIC_LIMIT = 20;

export interface LocalGameConfig extends GameConfig {
  readonly databaseId: number;
  readonly datasetVersion: number;
  readonly layoutCount: number;
  readonly rulesVersion: number;
}

export interface LayoutCandidate {
  readonly cells: readonly number[];
  readonly sequenceNumber: number;
  readonly signature: string;
}

export type PrefixLayoutSuggestion =
  | {
      readonly cells: readonly number[];
      readonly kind: 'unique';
      readonly occurrenceCount: 1;
      readonly sequenceNumber: number;
      readonly signature: string;
    }
  | {
      readonly cells: readonly number[];
      readonly kind: 'duplicate';
      readonly occurrenceCount: number;
      readonly sequenceNumber: null;
      readonly signature: string;
    };

export type ExactMatchResult =
  | {
      readonly status: 'not_found';
    }
  | {
      readonly status: 'unique';
      readonly candidate: LayoutCandidate;
    }
  | {
      readonly status: 'duplicate';
      readonly occurrenceCount: number;
      readonly sequenceNumbers: readonly number[] | null;
    };

export interface PrefixMatchResult {
  readonly candidateCount: number;
  readonly suggestion: PrefixLayoutSuggestion | null;
}

export interface LocalSnapshotDatabase {
  getAllAsync<T>(source: string, params?: SQLiteBindParams): Promise<T[]>;
  getFirstAsync<T>(
    source: string,
    params?: SQLiteBindParams,
  ): Promise<T | null>;
}

interface GameRow {
  code: string;
  columns: number;
  dataset_version: number;
  id: number;
  layout_count: number;
  name: string;
  rows: number;
  rules_version: number;
  signature_cell_width: number;
  spin_cost: number;
}

interface SymbolRow {
  code: string;
  display_order: number;
  game_id: number;
  image_asset_key: string | null;
  is_wildcard: number;
  mobile_code: number;
  name: string;
  name_en: string | null;
  name_pl: string | null;
}

interface CountRow {
  candidate_count: number;
}

interface LayoutRow {
  sequence_number: number;
  signature: string;
}

interface SignatureRow {
  signature: string;
}

interface SequenceNumberRow {
  sequence_number: number;
}

interface PayoutRow {
  cycle_segment: number;
  payout: number;
  sequence_number: number;
}

const GAME_QUERY = `
  SELECT
    id, code, name, rows, columns, spin_cost, signature_cell_width,
    layout_count, dataset_version, rules_version
  FROM games
  ORDER BY id
`;

const SYMBOL_QUERY = `
  SELECT
    game_id, mobile_code, code, name, name_pl, name_en, is_wildcard,
    display_order, image_asset_key
  FROM symbols
  ORDER BY game_id, display_order, mobile_code
`;

const PREFIX_COUNT_QUERY = `
  SELECT COUNT(*) AS candidate_count
  FROM layouts INDEXED BY idx_layouts_game_signature
  WHERE game_id = ? AND signature >= ? AND signature < ?
`;

const PREFIX_CANDIDATE_QUERY = `
  SELECT sequence_number, signature
  FROM layouts INDEXED BY idx_layouts_game_signature
  WHERE game_id = ? AND signature >= ? AND signature < ?
  ORDER BY signature, sequence_number
  LIMIT 1
`;

const PREFIX_DISTINCT_SIGNATURES_QUERY = `
  SELECT signature
  FROM layouts INDEXED BY idx_layouts_game_signature
  WHERE game_id = ? AND signature >= ? AND signature < ?
  GROUP BY signature
  ORDER BY signature
  LIMIT 2
`;

const EXACT_COUNT_QUERY = `
  SELECT COUNT(*) AS candidate_count
  FROM layouts INDEXED BY idx_layouts_game_signature
  WHERE game_id = ? AND signature = ?
`;

const EXACT_CANDIDATE_QUERY = `
  SELECT sequence_number, signature
  FROM layouts INDEXED BY idx_layouts_game_signature
  WHERE game_id = ? AND signature = ?
  ORDER BY sequence_number
  LIMIT 1
`;

const DUPLICATE_SEQUENCE_QUERY = `
  SELECT sequence_number
  FROM layouts INDEXED BY idx_layouts_game_signature
  WHERE game_id = ? AND signature = ?
  ORDER BY sequence_number
  LIMIT ?
`;

const LAYOUT_BY_SEQUENCE_QUERY = `
  SELECT sequence_number, signature
  FROM layouts
  WHERE game_id = ? AND sequence_number = ?
  LIMIT 1
`;

const CYCLIC_PAYOUT_QUERY = `
  SELECT sequence_number, payout, cycle_segment
  FROM (
    SELECT sequence_number, payout, 0 AS cycle_segment
    FROM layouts
    WHERE game_id = ? AND sequence_number > ?

    UNION ALL

    SELECT sequence_number, payout, 1 AS cycle_segment
    FROM layouts
    WHERE game_id = ? AND sequence_number < ?
  )
  ORDER BY cycle_segment, sequence_number
  LIMIT ?
`;

function requireString(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new LocalDataError(`${label} must be a non-empty string.`);
  }
  return value;
}

function requireInteger(
  value: unknown,
  label: string,
  minimum: number,
): number {
  if (!Number.isSafeInteger(value) || (value as number) < minimum) {
    throw new LocalDataError(
      `${label} must be a safe integer greater than or equal to ${minimum}.`,
    );
  }
  return value as number;
}

function validateSelectedGame(game: LocalGameConfig): void {
  validateGameConfig(game);
  requireInteger(game.databaseId, 'Game database id', 1);
  requireInteger(game.datasetVersion, 'Game dataset version', 1);
  requireInteger(game.layoutCount, 'Game layout count', 1);
  requireInteger(game.rulesVersion, 'Game rules version', 1);
}

function decodeAndValidatePrefix(
  signaturePrefix: string,
  game: LocalGameConfig,
): readonly number[] {
  if (typeof signaturePrefix !== 'string') {
    throw new LocalDataError('Signature prefix must be a string.');
  }

  const cells = decodeSignature(signaturePrefix, game.signatureCellWidth);
  const expectedCellCount = game.rows * game.columns;
  if (cells.length > expectedCellCount) {
    throw new LocalDataError(
      `Signature prefix contains ${cells.length} cells; maximum is ${expectedCellCount}.`,
    );
  }

  const allowedCodes = new Set(game.symbols.map((symbol) => symbol.mobileCode));
  if (cells.some((cell) => !allowedCodes.has(cell))) {
    throw new LocalDataError(
      'Signature prefix contains a symbol outside the selected game.',
    );
  }
  return cells;
}

function readCandidate(
  row: LayoutRow | null,
  game: LocalGameConfig,
): LayoutCandidate {
  if (row === null) {
    throw new LocalDataError(
      'Candidate count and candidate row are inconsistent.',
    );
  }

  const sequenceNumber = requireInteger(
    row.sequence_number,
    'Layout sequence number',
    1,
  );
  if (sequenceNumber > game.layoutCount) {
    throw new LocalDataError(
      'Layout sequence number exceeds the game layout count.',
    );
  }

  const signature = requireString(row.signature, 'Layout signature');
  const cells = decodeSignature(
    signature,
    game.signatureCellWidth,
    game.rows * game.columns,
  );
  validateFullBoard(cells, game);

  return Object.freeze({
    cells: Object.freeze([...cells]),
    sequenceNumber,
    signature,
  });
}

function readLayoutContent(
  row: SignatureRow | null,
  game: LocalGameConfig,
): Pick<PrefixLayoutSuggestion, 'cells' | 'signature'> {
  if (row === null) {
    throw new LocalDataError(
      'Candidate count and distinct signature rows are inconsistent.',
    );
  }

  const signature = requireString(row.signature, 'Layout signature');
  const cells = decodeSignature(
    signature,
    game.signatureCellWidth,
    game.rows * game.columns,
  );
  validateFullBoard(cells, game);

  return Object.freeze({
    cells: Object.freeze([...cells]),
    signature,
  });
}

function readCandidateCount(row: CountRow | null): number {
  if (row === null) {
    throw new LocalDataError('Candidate count query returned no row.');
  }
  return requireInteger(row.candidate_count, 'Candidate count', 0);
}

export class LocalLayoutRepository {
  constructor(
    private readonly database: LocalSnapshotDatabase,
    private readonly duplicateDiagnosticLimit = DEFAULT_DUPLICATE_DIAGNOSTIC_LIMIT,
  ) {
    requireInteger(duplicateDiagnosticLimit, 'Duplicate diagnostic limit', 1);
  }

  async listGames(): Promise<readonly LocalGameConfig[]> {
    try {
      const [gameRows, symbolRows] = await Promise.all([
        this.database.getAllAsync<GameRow>(GAME_QUERY),
        this.database.getAllAsync<SymbolRow>(SYMBOL_QUERY),
      ]);
      const symbolsByGame = new Map<number, SymbolDefinition[]>();

      for (const row of symbolRows) {
        const gameId = requireInteger(row.game_id, 'Symbol game id', 1);
        const wildcard = requireInteger(
          row.is_wildcard,
          'Symbol wildcard flag',
          0,
        );
        if (wildcard > 1) {
          throw new LocalDataError('Symbol wildcard flag must be zero or one.');
        }

        const symbol: SymbolDefinition = {
          code: requireString(row.code, 'Symbol code'),
          displayOrder: requireInteger(
            row.display_order,
            'Symbol display order',
            0,
          ),
          isWildcard: wildcard === 1,
          mobileCode: requireInteger(row.mobile_code, 'Symbol mobile code', 1),
          name: requireString(row.name, 'Symbol name'),
          ...(row.name_pl === null || row.name_pl === undefined
            ? {}
            : { namePl: requireString(row.name_pl, 'Polish symbol name') }),
          ...(row.name_en === null || row.name_en === undefined
            ? {}
            : { nameEn: requireString(row.name_en, 'English symbol name') }),
          ...(row.image_asset_key === null || row.image_asset_key === undefined
            ? {}
            : {
                imageAssetKey: requireString(
                  row.image_asset_key,
                  'Symbol image asset key',
                ),
              }),
        };
        const symbols = symbolsByGame.get(gameId) ?? [];
        symbols.push(symbol);
        symbolsByGame.set(gameId, symbols);
      }

      const games = gameRows.map((row): LocalGameConfig => {
        const databaseId = requireInteger(row.id, 'Game database id', 1);
        const game: LocalGameConfig = {
          code: requireString(row.code, 'Game code'),
          columns: requireInteger(row.columns, 'Game column count', 1),
          databaseId,
          datasetVersion: requireInteger(
            row.dataset_version,
            'Game dataset version',
            1,
          ),
          id: requireString(row.code, 'Game id'),
          layoutCount: requireInteger(row.layout_count, 'Game layout count', 1),
          name: requireString(row.name, 'Game name'),
          rows: requireInteger(row.rows, 'Game row count', 1),
          rulesVersion: requireInteger(
            row.rules_version,
            'Game rules version',
            1,
          ),
          signatureCellWidth: requireInteger(
            row.signature_cell_width,
            'Signature cell width',
            1,
          ),
          spinCost: requireInteger(row.spin_cost, 'Game spin cost', 0),
          symbols: Object.freeze([...(symbolsByGame.get(databaseId) ?? [])]),
        };
        validateSelectedGame(game);
        return Object.freeze(game);
      });

      return Object.freeze(games);
    } catch (error: unknown) {
      throw asLocalDataError(error, 'Could not read local game catalog');
    }
  }

  async findByPrefix(
    game: LocalGameConfig,
    signaturePrefix: string,
  ): Promise<PrefixMatchResult> {
    try {
      validateSelectedGame(game);
      decodeAndValidatePrefix(signaturePrefix, game);
      const upperBound = `${signaturePrefix}:`;
      const params: SQLiteBindParams = [
        game.databaseId,
        signaturePrefix,
        upperBound,
      ];
      const count = readCandidateCount(
        await this.database.getFirstAsync<CountRow>(PREFIX_COUNT_QUERY, params),
      );
      if (count === 0) {
        return Object.freeze({ candidateCount: 0, suggestion: null });
      }

      if (count === 1) {
        const candidate = readCandidate(
          await this.database.getFirstAsync<LayoutRow>(
            PREFIX_CANDIDATE_QUERY,
            params,
          ),
          game,
        );
        if (!candidate.signature.startsWith(signaturePrefix)) {
          throw new LocalDataError(
            'Prefix query returned a candidate outside the requested range.',
          );
        }
        return Object.freeze({
          candidateCount: 1,
          suggestion: Object.freeze({
            ...candidate,
            kind: 'unique',
            occurrenceCount: 1,
          }),
        });
      }

      const distinctSignatures = await this.database.getAllAsync<SignatureRow>(
        PREFIX_DISTINCT_SIGNATURES_QUERY,
        params,
      );
      if (distinctSignatures.length === 0) {
        throw new LocalDataError(
          'Candidate count and distinct signature rows are inconsistent.',
        );
      }
      if (distinctSignatures.length > 1) {
        return Object.freeze({ candidateCount: count, suggestion: null });
      }

      const layout = readLayoutContent(distinctSignatures[0] ?? null, game);
      if (!layout.signature.startsWith(signaturePrefix)) {
        throw new LocalDataError(
          'Prefix query returned a signature outside the requested range.',
        );
      }
      return Object.freeze({
        candidateCount: count,
        suggestion: Object.freeze({
          ...layout,
          kind: 'duplicate',
          occurrenceCount: count,
          sequenceNumber: null,
        }),
      });
    } catch (error: unknown) {
      throw asLocalDataError(error, 'Could not match layout prefix');
    }
  }

  async findExact(
    game: LocalGameConfig,
    signature: string,
  ): Promise<ExactMatchResult> {
    try {
      validateSelectedGame(game);
      const cells = decodeSignature(
        signature,
        game.signatureCellWidth,
        game.rows * game.columns,
      );
      validateFullBoard(cells, game);
      const params: SQLiteBindParams = [game.databaseId, signature];
      const count = readCandidateCount(
        await this.database.getFirstAsync<CountRow>(EXACT_COUNT_QUERY, params),
      );

      if (count === 0) {
        return Object.freeze({ status: 'not_found' });
      }
      if (count === 1) {
        const candidate = readCandidate(
          await this.database.getFirstAsync<LayoutRow>(
            EXACT_CANDIDATE_QUERY,
            params,
          ),
          game,
        );
        if (candidate.signature !== signature) {
          throw new LocalDataError(
            'Exact query returned a different signature.',
          );
        }
        return Object.freeze({ candidate, status: 'unique' });
      }

      const sequenceRows = await this.database.getAllAsync<SequenceNumberRow>(
        DUPLICATE_SEQUENCE_QUERY,
        [game.databaseId, signature, this.duplicateDiagnosticLimit],
      );
      let previousSequenceNumber = 0;
      const sequenceNumbers = sequenceRows.map((row) => {
        const sequenceNumber = requireInteger(
          row.sequence_number,
          'Duplicate sequence number',
          1,
        );
        if (
          sequenceNumber > game.layoutCount ||
          sequenceNumber <= previousSequenceNumber
        ) {
          throw new LocalDataError(
            'Duplicate sequence diagnostics are outside deterministic order.',
          );
        }
        previousSequenceNumber = sequenceNumber;
        return sequenceNumber;
      });
      const expectedDiagnosticCount = Math.min(
        count,
        this.duplicateDiagnosticLimit,
      );
      if (sequenceNumbers.length !== expectedDiagnosticCount) {
        throw new LocalDataError(
          'Duplicate count and diagnostic rows are inconsistent.',
        );
      }

      return Object.freeze({
        occurrenceCount: count,
        sequenceNumbers:
          count <= this.duplicateDiagnosticLimit
            ? Object.freeze(sequenceNumbers)
            : null,
        status: 'duplicate',
      });
    } catch (error: unknown) {
      throw asLocalDataError(error, 'Could not match exact layout');
    }
  }

  async readLayoutBySequence(
    game: LocalGameConfig,
    sequenceNumber: number,
  ): Promise<LayoutCandidate> {
    try {
      validateSelectedGame(game);
      requireInteger(sequenceNumber, 'Layout sequence number', 1);
      if (sequenceNumber > game.layoutCount) {
        throw new LocalDataError(
          'Layout sequence number exceeds the game layout count.',
        );
      }

      const candidate = readCandidate(
        await this.database.getFirstAsync<LayoutRow>(LAYOUT_BY_SEQUENCE_QUERY, [
          game.databaseId,
          sequenceNumber,
        ]),
        game,
      );
      if (candidate.sequenceNumber !== sequenceNumber) {
        throw new LocalDataError(
          'Sequence query returned a different layout position.',
        );
      }
      return candidate;
    } catch (error: unknown) {
      throw asLocalDataError(error, 'Could not read layout by sequence');
    }
  }

  async readCyclicPayouts(
    game: LocalGameConfig,
    startSequenceNumber: number,
    targetScanLimit: number,
  ): Promise<readonly SequencePayout[]> {
    try {
      validateSelectedGame(game);
      requireInteger(startSequenceNumber, 'Start sequence number', 1);
      if (startSequenceNumber > game.layoutCount) {
        throw new LocalDataError(
          'Start sequence number exceeds the game layout count.',
        );
      }
      requireInteger(
        targetScanLimit,
        'Target scan limit',
        TARGET_SCAN_LIMIT_ENGINE_MIN,
      );
      if (targetScanLimit > TARGET_SCAN_LIMIT_MAX) {
        throw new LocalDataError('Target scan limit must not exceed 500000.');
      }
      const expectedLength = Math.min(targetScanLimit, game.layoutCount - 1);

      const rows = await this.database.getAllAsync<PayoutRow>(
        CYCLIC_PAYOUT_QUERY,
        [
          game.databaseId,
          startSequenceNumber,
          game.databaseId,
          startSequenceNumber,
          expectedLength,
        ],
      );
      if (rows.length !== expectedLength) {
        throw new LocalDataError(
          `Cyclic payout stream contains ${rows.length} rows; expected ${expectedLength}.`,
        );
      }

      const payouts = rows.map((row, index): SequencePayout => {
        const sequenceNumber = requireInteger(
          row.sequence_number,
          'Payout sequence number',
          1,
        );
        const payoutCredits = requireInteger(row.payout, 'Layout payout', 0);
        const cycleSegment = requireInteger(
          row.cycle_segment,
          'Cycle segment',
          0,
        );
        const expectedSequenceNumber =
          ((startSequenceNumber + index) % game.layoutCount) + 1;
        const expectedSegment =
          expectedSequenceNumber > startSequenceNumber ? 0 : 1;

        if (
          sequenceNumber !== expectedSequenceNumber ||
          cycleSegment !== expectedSegment
        ) {
          throw new LocalDataError(
            'Cyclic payout stream is not in deterministic sequence order.',
          );
        }
        return Object.freeze({ payoutCredits, sequenceNumber });
      });

      return Object.freeze(payouts);
    } catch (error: unknown) {
      throw asLocalDataError(error, 'Could not read cyclic payout stream');
    }
  }
}
