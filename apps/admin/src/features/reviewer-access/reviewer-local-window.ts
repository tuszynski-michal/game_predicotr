export type LocalReviewerWindow = {
  opener: unknown;
};

export type LocalReviewerWindowOpener = (
  url: string,
  target: string,
) => LocalReviewerWindow | null;

const LOCAL_REVIEWER_PORT = '3001';
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]']);

export function buildPreparedLocalReviewUrl(
  adminPageUrl: string,
  input: { readonly gameId: string; readonly importJobId: string },
): string | null {
  let url: URL;
  try {
    url = new URL(adminPageUrl);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' || !LOOPBACK_HOSTS.has(url.hostname)) {
    return null;
  }
  url.port = LOCAL_REVIEWER_PORT;
  url.pathname = '/';
  url.search = '';
  url.hash = '';
  url.searchParams.set('mode', 'local');
  url.searchParams.set('gameId', input.gameId);
  url.searchParams.set('importJobId', input.importJobId);
  return url.toString();
}

export function prepareLocalReviewerWindow(
  adminPageUrl: string,
  input: { readonly gameId: string; readonly importJobId: string },
  openWindow: LocalReviewerWindowOpener,
): LocalReviewerWindow | null {
  const reviewUrl = buildPreparedLocalReviewUrl(adminPageUrl, input);
  if (reviewUrl === null) return null;
  try {
    const reviewerWindow = openWindow(reviewUrl, '_blank');
    if (reviewerWindow === null) return null;
    try {
      reviewerWindow.opener = null;
    } catch {
      // Some browsers disallow changing opener after creating the new context.
      // This must never abort the API call or leave the tab on about:blank.
    }
    return reviewerWindow;
  } catch {
    return null;
  }
}
