import { createClient as createGeneratedClient } from './generated/client';
import {
  archiveGame as archiveGeneratedGame,
  archiveSymbol as archiveGeneratedSymbol,
  createGame as createGeneratedGame,
  createSymbol as createGeneratedSymbol,
  getGame as getGeneratedGame,
  getHealth as getGeneratedHealth,
  getSymbol as getGeneratedSymbol,
  listGames as listGeneratedGames,
  listSymbols as listGeneratedSymbols,
  updateGame as updateGeneratedGame,
  updateSymbol as updateGeneratedSymbol,
} from './generated/sdk.gen';
import type {
  GameCreate,
  GameUpdate,
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
