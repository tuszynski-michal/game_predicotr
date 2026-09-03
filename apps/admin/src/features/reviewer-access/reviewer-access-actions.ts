import type {
  AdminApiClient,
  ReviewerWorkAssignmentResponse,
  ReviewerWorkOpenedResponse,
  ReviewerWorkOverviewResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type ReviewerAccessClient = Pick<
  AdminApiClient,
  | 'closeReviewerWorkAssignment'
  | 'heartbeatReviewerWorkAssignment'
  | 'listReviewerWorkAssignments'
  | 'openLocalReviewerWork'
  | 'openOnlineReviewerWork'
>;

export type ReviewerLauncherClient = ReviewerAccessClient &
  Pick<
    AdminApiClient,
    | 'listGames'
    | 'listImageGridReviews'
    | 'listJobs'
    | 'listPendingBoardCellGeometry'
    | 'listReadyBrowserImageSelections'
  >;

export type ReviewerWorkOverviewResult =
  | { readonly ok: true; readonly overview: ReviewerWorkOverviewResponse }
  | { readonly error: string; readonly ok: false };

export type OpenReviewerWorkResult =
  | { readonly ok: true; readonly opened: ReviewerWorkOpenedResponse }
  | { readonly error: string; readonly ok: false };

export type CloseReviewerWorkResult =
  | { readonly assignmentId: string; readonly ok: true }
  | { readonly error: string; readonly ok: false };

const actionCommand = { confirmed: true } as const;

export async function loadReviewerWork(
  api: ReviewerAccessClient,
  gameId: string,
): Promise<ReviewerWorkOverviewResult> {
  try {
    const result = await api.listReviewerWorkAssignments(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się odczytać aktywnych prac Reviewera.',
        ),
        ok: false,
      };
    }
    return { ok: true, overview: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function openLocalReviewer(
  api: ReviewerAccessClient,
  input: { readonly gameId: string; readonly importJobId: string },
): Promise<OpenReviewerWorkResult> {
  try {
    const result = await api.openLocalReviewerWork(
      input.gameId,
      input.importJobId,
      { lifetimeMinutes: 480 },
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się otworzyć lokalnej pracy Reviewera.',
        ),
        ok: false,
      };
    }
    if (
      result.data.assignment.assignmentType !== 'local' ||
      !isSafeLocalReviewUrl(result.data.assignment)
    ) {
      return {
        error: 'Lokalna praca Reviewera zwróciła nieprawidłowy adres.',
        ok: false,
      };
    }
    return { ok: true, opened: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function openOnlineReviewer(
  api: ReviewerAccessClient,
  input: { readonly gameId: string; readonly importJobId: string },
): Promise<OpenReviewerWorkResult> {
  try {
    const result = await api.openOnlineReviewerWork(
      input.gameId,
      input.importJobId,
      { lifetimeMinutes: 480 },
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć udostępnienia online.',
        ),
        ok: false,
      };
    }
    if (
      result.data.assignment.assignmentType !== 'online' ||
      !isSafeOnlineReviewUrl(result.data.assignment)
    ) {
      return {
        error: 'Udostępnienie online zwróciło nieprawidłowy adres.',
        ok: false,
      };
    }
    return { ok: true, opened: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function heartbeatReviewerWork(
  api: ReviewerAccessClient,
  assignmentId: string,
): Promise<boolean> {
  try {
    const result = await api.heartbeatReviewerWorkAssignment(
      assignmentId,
      actionCommand,
    );
    return result.error === undefined && result.data !== undefined;
  } catch {
    return false;
  }
}

export async function closeReviewerWork(
  api: ReviewerAccessClient,
  assignmentId: string,
): Promise<CloseReviewerWorkResult> {
  try {
    const result = await api.closeReviewerWorkAssignment(
      assignmentId,
      actionCommand,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zatrzymać wybranej pracy Reviewera.',
        ),
        ok: false,
      };
    }
    return { assignmentId: result.data.assignmentId, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

function isSafeLocalReviewUrl(
  assignment: ReviewerWorkAssignmentResponse,
): boolean {
  if (assignment.reviewUrl === null) return false;
  const target = new URL(assignment.reviewUrl);
  return (
    target.protocol === 'http:' &&
    target.hostname === '127.0.0.1' &&
    target.port === '3001' &&
    target.searchParams.get('mode') === 'local' &&
    target.searchParams.get('gameId') === assignment.gameId &&
    target.searchParams.get('importJobId') === assignment.importJobId
  );
}

function isSafeOnlineReviewUrl(
  assignment: ReviewerWorkAssignmentResponse,
): boolean {
  if (assignment.reviewUrl === null) return false;
  const target = new URL(assignment.reviewUrl);
  return (
    target.protocol === 'https:' &&
    target.hostname.endsWith('.trycloudflare.com') &&
    target.username === '' &&
    target.password === '' &&
    target.searchParams.has('session')
  );
}
