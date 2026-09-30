import type { ErrorResponse } from '@game-predictor/admin-api-client';

export function apiErrorMessage(error: unknown, fallback: string): string {
  return isErrorResponse(error) ? `${error.message} (${error.code})` : fallback;
}

function isErrorResponse(error: unknown): error is ErrorResponse {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    'message' in error &&
    typeof error.message === 'string'
  );
}
