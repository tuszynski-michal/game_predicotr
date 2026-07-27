import { createClient as createGeneratedClient } from './generated/client';
import {
  archiveGame as archiveGeneratedGame,
  archivePayline as archiveGeneratedPayline,
  archivePayoutRule as archiveGeneratedPayoutRule,
  archiveRulesVersion as archiveGeneratedRulesVersion,
  archiveSymbol as archiveGeneratedSymbol,
  createGame as createGeneratedGame,
  createPayline as createGeneratedPayline,
  createPayoutRule as createGeneratedPayoutRule,
  createRulesVersion as createGeneratedRulesVersion,
  createSymbol as createGeneratedSymbol,
  getGame as getGeneratedGame,
  getHealth as getGeneratedHealth,
  getPayline as getGeneratedPayline,
  getPayoutRule as getGeneratedPayoutRule,
  getRulesPublicationReadiness as getGeneratedRulesPublicationReadiness,
  getRulesVersion as getGeneratedRulesVersion,
  getSymbol as getGeneratedSymbol,
  listGames as listGeneratedGames,
  listPaylines as listGeneratedPaylines,
  listPayoutRules as listGeneratedPayoutRules,
  listRulesVersions as listGeneratedRulesVersions,
  listRulesVersionSymbols as listGeneratedRulesVersionSymbols,
  listSymbols as listGeneratedSymbols,
  publishRulesVersion as publishGeneratedRulesVersion,
  updateGame as updateGeneratedGame,
  updatePayline as updateGeneratedPayline,
  updatePayoutRule as updateGeneratedPayoutRule,
  updateRulesVersion as updateGeneratedRulesVersion,
  updateRulesVersionSymbol as updateGeneratedRulesVersionSymbol,
  updateSymbol as updateGeneratedSymbol,
} from './generated/sdk.gen';
import type {
  GameCreate,
  GameUpdate,
  PaylineCreate,
  PaylineUpdate,
  PayoutRuleCreate,
  PayoutRuleUpdate,
  RulesVersionCreate,
  RulesVersionSymbolUpdate,
  RulesVersionUpdate,
  SymbolCreate,
  SymbolUpdate,
} from './generated/types.gen';

export type {
  ErrorResponse,
  GameCreate,
  GameResponse,
  GameStatus,
  GameUpdate,
  HealthResponse,
  PaylineCreate,
  PaylineResponse,
  PaylineUpdate,
  PayoutRuleCreate,
  PayoutRuleResponse,
  PayoutRuleUpdate,
  RulesPublicationIssueResponse,
  RulesPublicationReadinessResponse,
  RulesVersionCreate,
  RulesVersionResponse,
  RulesVersionStatus,
  RulesVersionSymbolResponse,
  RulesVersionSymbolUpdate,
  RulesVersionUpdate,
  SymbolCreate,
  SymbolResponse,
  SymbolStatus,
  SymbolUpdate,
} from './generated/types.gen';

export interface AdminApiClientOptions {
  readonly baseUrl: string;
  readonly fetch?: typeof globalThis.fetch;
}

export function createAdminApiClient(options: AdminApiClientOptions) {
  const client = createGeneratedClient({
    baseUrl: options.baseUrl,
    ...(options.fetch === undefined ? {} : { fetch: options.fetch }),
  });

  return {
    getHealth: () => getGeneratedHealth({ client }),
    listGames: () => listGeneratedGames({ client }),
    createGame: (body: GameCreate) => createGeneratedGame({ body, client }),
    getGame: (gameId: string) =>
      getGeneratedGame({ client, path: { game_id: gameId } }),
    updateGame: (gameId: string, body: GameUpdate) =>
      updateGeneratedGame({ body, client, path: { game_id: gameId } }),
    archiveGame: (gameId: string) =>
      archiveGeneratedGame({ client, path: { game_id: gameId } }),
    listRulesVersions: (gameId: string) =>
      listGeneratedRulesVersions({ client, path: { game_id: gameId } }),
    createRulesVersion: (gameId: string, body: RulesVersionCreate) =>
      createGeneratedRulesVersion({
        body,
        client,
        path: { game_id: gameId },
      }),
    getRulesVersion: (rulesVersionId: string) =>
      getGeneratedRulesVersion({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    updateRulesVersion: (rulesVersionId: string, body: RulesVersionUpdate) =>
      updateGeneratedRulesVersion({
        body,
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    getRulesPublicationReadiness: (rulesVersionId: string) =>
      getGeneratedRulesPublicationReadiness({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    publishRulesVersion: (rulesVersionId: string) =>
      publishGeneratedRulesVersion({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    archiveRulesVersion: (rulesVersionId: string) =>
      archiveGeneratedRulesVersion({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    listPaylines: (rulesVersionId: string) =>
      listGeneratedPaylines({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    createPayline: (rulesVersionId: string, body: PaylineCreate) =>
      createGeneratedPayline({
        body,
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    getPayline: (rulesVersionId: string, paylineId: string) =>
      getGeneratedPayline({
        client,
        path: {
          payline_id: paylineId,
          rules_version_id: rulesVersionId,
        },
      }),
    updatePayline: (
      rulesVersionId: string,
      paylineId: string,
      body: PaylineUpdate,
    ) =>
      updateGeneratedPayline({
        body,
        client,
        path: {
          payline_id: paylineId,
          rules_version_id: rulesVersionId,
        },
      }),
    archivePayline: (rulesVersionId: string, paylineId: string) =>
      archiveGeneratedPayline({
        client,
        path: {
          payline_id: paylineId,
          rules_version_id: rulesVersionId,
        },
      }),
    listRulesVersionSymbols: (rulesVersionId: string) =>
      listGeneratedRulesVersionSymbols({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    updateRulesVersionSymbol: (
      rulesVersionId: string,
      symbolId: string,
      body: RulesVersionSymbolUpdate,
    ) =>
      updateGeneratedRulesVersionSymbol({
        body,
        client,
        path: {
          rules_version_id: rulesVersionId,
          symbol_id: symbolId,
        },
      }),
    listPayoutRules: (rulesVersionId: string) =>
      listGeneratedPayoutRules({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    createPayoutRule: (rulesVersionId: string, body: PayoutRuleCreate) =>
      createGeneratedPayoutRule({
        body,
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    getPayoutRule: (rulesVersionId: string, payoutRuleId: string) =>
      getGeneratedPayoutRule({
        client,
        path: {
          payout_rule_id: payoutRuleId,
          rules_version_id: rulesVersionId,
        },
      }),
    updatePayoutRule: (
      rulesVersionId: string,
      payoutRuleId: string,
      body: PayoutRuleUpdate,
    ) =>
      updateGeneratedPayoutRule({
        body,
        client,
        path: {
          payout_rule_id: payoutRuleId,
          rules_version_id: rulesVersionId,
        },
      }),
    archivePayoutRule: (rulesVersionId: string, payoutRuleId: string) =>
      archiveGeneratedPayoutRule({
        client,
        path: {
          payout_rule_id: payoutRuleId,
          rules_version_id: rulesVersionId,
        },
      }),
    listSymbols: (gameId: string) =>
      listGeneratedSymbols({ client, path: { game_id: gameId } }),
    createSymbol: (gameId: string, body: SymbolCreate) =>
      createGeneratedSymbol({
        body,
        client,
        path: { game_id: gameId },
      }),
    getSymbol: (gameId: string, symbolId: string) =>
      getGeneratedSymbol({
        client,
        path: { game_id: gameId, symbol_id: symbolId },
      }),
    updateSymbol: (gameId: string, symbolId: string, body: SymbolUpdate) =>
      updateGeneratedSymbol({
        body,
        client,
        path: { game_id: gameId, symbol_id: symbolId },
      }),
    archiveSymbol: (gameId: string, symbolId: string) =>
      archiveGeneratedSymbol({
        client,
        path: { game_id: gameId, symbol_id: symbolId },
      }),
  } as const;
}

export type AdminApiClient = ReturnType<typeof createAdminApiClient>;
