import type {
  AdminApiClient,
  ReviewerIngressStatusResponse,
  ReviewerSessionCreate,
  ReviewerSessionCreatedResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type ReviewerAccessClient = Pick<
  AdminApiClient,
  | 'createReviewerSession'
  | 'getReviewerIngressStatus'
  | 'revokeReviewerSession'
  | 'startReviewerIngress'
  | 'stopReviewerIngress'
>;

export type IngressResult =
  | { readonly ingress: ReviewerIngressStatusResponse; readonly ok: true }
  | {
      readonly error: string;
      readonly ingress?: ReviewerIngressStatusResponse;
      readonly ok: false;
    };

export type PublishedReviewerSessionResult =
  | {
      readonly ingress: ReviewerIngressStatusResponse;
      readonly ok: true;
      readonly session: ReviewerSessionCreatedResponse;
    }
  | { readonly error: string; readonly ok: false };

const ingressCommand = {
  confirmed: true,
  target: 'remote-reviewer',
} as const;

export async function loadReviewerIngress(
  api: ReviewerAccessClient,
): Promise<IngressResult> {
  try {
    const result = await api.getReviewerIngressStatus();
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się odczytać stanu udostępniania.',
        ),
        ok: false,
      };
    }
    return { ingress: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function publishReviewerSession(
  api: ReviewerAccessClient,
  input: ReviewerSessionCreate,
): Promise<PublishedReviewerSessionResult> {
  try {
    const ingressResult = await api.startReviewerIngress(ingressCommand);
    if (ingressResult.error !== undefined || ingressResult.data === undefined) {
      return {
        error: apiErrorMessage(
          ingressResult.error,
          'Nie udało się wystawić aplikacji Reviewer online.',
        ),
        ok: false,
      };
    }
    if (
      ingressResult.data.state !== 'running' ||
      ingressResult.data.publicOrigin === null
    ) {
      return {
        error: 'Tunel nie osiągnął gotowego stanu online.',
        ok: false,
      };
    }

    const sessionResult = await api.createReviewerSession(input);
    if (sessionResult.error !== undefined || sessionResult.data === undefined) {
      return {
        error: apiErrorMessage(
          sessionResult.error,
          'Nie udało się utworzyć sesji recenzenta.',
        ),
        ok: false,
      };
    }
    return {
      ingress: ingressResult.data,
      ok: true,
      session: sessionResult.data,
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function stopReviewerPublishing(
  api: ReviewerAccessClient,
  sessionId: string | null,
): Promise<IngressResult> {
  try {
    let revokeError = '';
    if (sessionId !== null) {
      const revokeResult = await api.revokeReviewerSession(sessionId);
      if (revokeResult.error !== undefined || revokeResult.data === undefined) {
        revokeError = apiErrorMessage(
          revokeResult.error,
          'Nie udało się unieważnić bieżącej sesji.',
        );
      }
    }

    const stopResult = await api.stopReviewerIngress(ingressCommand);
    if (stopResult.error !== undefined || stopResult.data === undefined) {
      return {
        error: apiErrorMessage(
          stopResult.error,
          'Nie udało się zatrzymać publicznego tunelu.',
        ),
        ok: false,
      };
    }
    if (revokeError !== '') {
      return {
        error: `${revokeError} Publiczny tunel został jednak zatrzymany.`,
        ingress: stopResult.data,
        ok: false,
      };
    }
    return { ingress: stopResult.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
