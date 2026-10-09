import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export const LOST_CONNECTION =
  'Połączenie z lokalnym Admin API zostało przerwane.';

/** The part of a generated-client result that decides the outcome. */
export interface MutationResultLike {
  readonly data?: unknown;
  readonly error?: unknown;
  readonly response?: { readonly status: number };
}

/**
 * The generated client never throws on transport errors: it returns
 * `{error, response}` with `response` undefined. Only a 4xx response carrying
 * an API error `code` is a definite refusal; a 5xx may follow a commit, so it
 * stays an unknown outcome and the idempotent retry resolves it.
 */
export function isDefiniteRefusal(result: MutationResultLike | null): boolean {
  if (result === null || result.response === undefined) return false;
  const { status } = result.response;
  if (status < 400 || status >= 500) return false;
  const error = result.error;
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string'
  );
}

export type MutationOutcome<T> =
  | { readonly data: T; readonly kind: 'done' }
  | {
      readonly code: string | null;
      readonly kind: 'refused';
      readonly message: string;
    }
  | { readonly kind: 'unknown'; readonly message: string };

export const MUTATION_TIMEOUT_MS = 15_000;

class MutationTimeoutError extends Error {}

/**
 * Runs one mutating request and classifies it for a retrying dialog: `done`
 * (applied), `refused` (the server answered 4xx with a code: nothing changed)
 * or `unknown` (thrown fetch, timeout, 5xx, unparseable body: the server may
 * have committed, so the caller keeps its key and body and replays them).
 */
export async function runMutation<T>(
  request: () => Promise<MutationResultLike | null | undefined>,
  fallback: string,
  timeoutMs: number = MUTATION_TIMEOUT_MS,
): Promise<MutationOutcome<T>> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let result: MutationResultLike | null;
  try {
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new MutationTimeoutError()), timeoutMs);
    });
    result = (await Promise.race([request(), timeout])) ?? null;
  } catch {
    result = null;
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
  if (
    result !== null &&
    result.error === undefined &&
    result.data !== undefined
  ) {
    return { data: result.data as T, kind: 'done' };
  }
  if (result !== null && isDefiniteRefusal(result)) {
    const error = result.error as { readonly code: string };
    return {
      code: error.code,
      kind: 'refused',
      message: apiErrorMessage(result.error, fallback),
    };
  }
  return {
    kind: 'unknown',
    message: `${LOST_CONNECTION} Wynik operacji jest nieznany.`,
  };
}
