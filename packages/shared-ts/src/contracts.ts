export interface SymbolDefinition {
  readonly mobileCode: number;
  readonly code: string;
  readonly name: string;
  readonly isWildcard: boolean;
  readonly displayOrder: number;
}

export interface GameConfig {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly rows: number;
  readonly columns: number;
  readonly spinCost: number;
  readonly signatureCellWidth: number;
  readonly symbols: readonly SymbolDefinition[];
}

export interface PaylineDefinition {
  readonly id: string;
  readonly rowPath: readonly number[];
}

export interface PayoutRuleDefinition {
  readonly symbolMobileCode: number;
  readonly matchLength: number;
  readonly payoutCredits: number;
}

export interface JokerInterpretation {
  readonly cellIndex: number;
  readonly asSymbolMobileCode: number;
}

export interface PayoutMatch {
  readonly symbolMobileCode: number;
  readonly paylineId: string;
  readonly startColumn: number;
  readonly matchedLength: number;
  readonly matchedCells: readonly number[];
  readonly jokerCells: readonly number[];
  readonly payoutCredits: number;
  readonly interpretation: readonly JokerInterpretation[];
}

export interface PayoutEvaluation {
  readonly totalPayout: number;
  readonly matches: readonly PayoutMatch[];
}

export interface SequencePayout {
  readonly sequenceNumber: number;
  readonly payoutCredits: number;
}

export interface ForecastPeak {
  readonly spinNumber: number;
  readonly sequenceNumber: number;
  readonly spinPayout: number;
  readonly cumulativePayout: number;
  readonly cumulativeCost: number;
  readonly net: number;
}

export interface ForecastResult {
  readonly evaluatedSpins: number;
  readonly finalCumulativePayout: number;
  readonly finalCumulativeCost: number;
  readonly finalNet: number;
  readonly positiveLocalPeaks: readonly ForecastPeak[];
}
