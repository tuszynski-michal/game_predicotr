const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

function localOrigin(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' &&
      LOOPBACK_HOSTS.has(url.hostname) &&
      url.username === '' &&
      url.password === '' &&
      url.pathname === '/' &&
      url.search === '' &&
      url.hash === ''
      ? url
      : null;
  } catch {
    return null;
  }
}

/** Navigate to the local pilot without transferring main database identities. */
export function localV7PilotHref(
  currentOrigin: string,
  configuredPilotOrigin?: string,
): string | null {
  const current = localOrigin(currentOrigin);
  if (current === null) return null;
  if (
    configuredPilotOrigin !== undefined &&
    configuredPilotOrigin.trim() === ''
  ) {
    return null;
  }
  const pilot =
    configuredPilotOrigin === undefined
      ? new URL(current.origin)
      : localOrigin(configuredPilotOrigin);
  if (pilot === null) return null;
  if (configuredPilotOrigin === undefined) pilot.port = '3020';
  if (pilot.origin === current.origin) return null;
  pilot.searchParams.set('workspace', 'semi-automatic-image-selection');
  return pilot.href;
}
