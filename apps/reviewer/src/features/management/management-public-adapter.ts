import {
  createManagementPublicApiClient,
  type ManagementSessionContext,
  type BoardSearchResponse,
  type SymbolResponse,
} from '@game-predictor/admin-api-client';
import type {
  ManagementClient,
  ManagementGameClient,
} from '@game-predictor/board-search-ui/management';

export const MANAGEMENT_API_BASE = '/management-api';
const INERT_IMAGE =
  'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=';

/** Generated transport plus a live fence shared by every closure and asset getter. */
export function createManagementPublicAdapter(options: {
  sessionId: string;
  fetchImplementation?: typeof fetch;
  now?: () => number;
  onEnded?: () => void;
}) {
  const now = options.now ?? Date.now;
  const fetchImplementation = options.fetchImplementation ?? globalThis.fetch;
  let context: ManagementSessionContext | null = null;
  let ended = false;
  const end = () => {
    if (ended) return;
    ended = true;
    options.onEnded?.();
  };
  const active = () => {
    if (context && Date.parse(context.expiresAt) <= now()) end();
    return context !== null && !ended;
  };
  const guardedFetch: typeof fetch = async (input, init) => {
    const request = new Request(input, init);
    const path = new URL(request.url).pathname;
    const gateRequest =
      path.endsWith('/context') ||
      path.endsWith(`/sessions/${options.sessionId}/unlock`);
    if (ended || (!gateRequest && !active()))
      throw new Error(
        'Dostęp do panelu został zakończony. Zachowano szkic i oczekujący zapis.',
      );
    if (request.headers.get('X-Management-Session') !== options.sessionId)
      throw new Error('Nieprawidłowa tożsamość sesji panelu.');
    const response = await fetchImplementation(request);
    if (!gateRequest && response.status === 401) end();
    // Wait for the complete JSON body before handing any receipt to the UI.
    // Ending a capability during response download retains the uncertain UUID.
    const body = await response.text();
    if (!gateRequest && response.status >= 400) {
      try {
        const error: unknown = JSON.parse(body);
        if (
          error &&
          typeof error === 'object' &&
          'code' in error &&
          [
            'MANAGEMENT_TOKEN_INVALID',
            'MANAGEMENT_SHARE_DISABLED',
            'MANAGEMENT_PROXY_REQUIRED',
          ].includes(String(error.code))
        )
          end();
      } catch {
        /* Preserve transport errors without guessing capability status. */
      }
    }
    if (!gateRequest && !active())
      throw new Error(
        'Dostęp zakończony podczas żądania. Zachowano oczekujący zapis.',
      );
    return new Response(body || null, {
      status: response.status,
      headers: response.headers,
    });
  };
  const api = createManagementPublicApiClient({
    baseUrl:
      typeof window === 'undefined'
        ? `http://localhost${MANAGEMENT_API_BASE}`
        : `${window.location.origin}${MANAGEMENT_API_BASE}`,
    sessionId: options.sessionId,
    fetch: guardedFetch,
  });
  function accept(value: ManagementSessionContext) {
    if (
      value.sessionId !== options.sessionId ||
      !Number.isFinite(Date.parse(value.expiresAt)) ||
      Date.parse(value.expiresAt) <= now()
    )
      throw new Error('Serwer zwrócił dostęp do innego lub wygasłego linku.');
    context = value;
    return value;
  }
  const client: ManagementClient = {
    getManagementSnapshot: api.getManagementSnapshot,
    createManagementPoint: api.createManagementPoint,
    updateManagementPoint: api.updateManagementPoint,
    createManagementMachine: api.createManagementMachine,
    updateManagementMachine: api.updateManagementMachine,
    updateManagementAssignments: api.updateManagementAssignments,
  };
  const machines = new Map<string, ManagementGameClient>();
  function forMachine(machineId: string): ManagementGameClient {
    const previous = machines.get(machineId);
    if (previous) return previous;
    const imageRevisions = new Map<string, string>();
    const gameClient: ManagementGameClient = {
      listManagementStakes: api.listManagementStakes,
      getManagementStake: api.getManagementStake,
      getManagementResult: api.getManagementResult,
      saveManagementStake: api.saveManagementStake,
      clearManagementStake: api.clearManagementStake,
      refreshManagementStake: api.refreshManagementStake,
      listManagementJournal: api.listManagementJournal,
      getManagementBoardDetail: api.getManagementBoardDetail,
      correctManagementBoardCell: api.correctManagementBoardCell,
      getManagementApproximateWin: api.getManagementApproximateWin,
      searchManagementBoards: async (machine, game, body, signal) => {
        const response = await api.searchManagementBoards(
          machine,
          game,
          body,
          signal,
        );
        if (!response.data) return { ...response, data: undefined };
        const search: BoardSearchResponse = {
          gameId: game,
          queryCellCount: response.data.search.queryCellCount,
          scope: response.data.search.scope,
          results: response.data.search.results.map((row) => ({
            ...row,
            assetMode: 'operational_review',
            importJobId: null,
            recognizedBoardId: null,
            reviewItemId: null,
          })),
        };
        return {
          ...response,
          data: { searchContextId: response.data.searchContextId, search },
        };
      },
      listSymbols: async (gameId) => {
        const response = await api.listPublicSymbols(machineId, gameId);
        if (!response.data) return { ...response, data: undefined };
        const symbols: SymbolResponse[] = response.data.map((symbol) => {
          if (symbol.imageRevision)
            imageRevisions.set(`${gameId}:${symbol.id}`, symbol.imageRevision);
          return {
            id: symbol.id,
            gameId,
            code: symbol.code,
            displayOrder: symbol.displayOrder,
            name: symbol.name,
            nameEn: symbol.nameEn,
            namePl: symbol.namePl,
            isWildcard: symbol.isWildcard,
            mobileCode: symbol.mobileCode,
            status: symbol.status === 'archived' ? 'archived' : 'active',
            imagePath: symbol.imageRevision ? 'public' : null,
            // Public symbols carry no catalog roles (D-535).
            superGameTriggerCount: null,
          };
        });
        return { ...response, data: symbols };
      },
      symbolImageAssetUrl: (gameId, symbolId) =>
        active()
          ? api.symbolImageUrl(
              machineId,
              gameId,
              symbolId,
              imageRevisions.get(`${gameId}:${symbolId}`) ?? '',
            )
          : INERT_IMAGE,
      boardSearchBoardViewUrl: (gameId, sequence, checksum, revision) =>
        active()
          ? api.boardImageUrl(machineId, gameId, sequence, checksum, revision)
          : INERT_IMAGE,
    };
    machines.set(machineId, gameClient);
    return gameClient;
  }
  return {
    client,
    forMachine,
    end,
    active,
    context: async () => {
      const result = await api.getManagementSessionContext();
      return result.data ? { ...result, data: accept(result.data) } : result;
    },
    unlock: async (code: string) => {
      const result = await api.unlockManagementSession(code);
      return result.data ? { ...result, data: accept(result.data) } : result;
    },
  };
}
export type ManagementPublicAdapter = ReturnType<
  typeof createManagementPublicAdapter
>;
