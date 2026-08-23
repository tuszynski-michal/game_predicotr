import { proxyRemoteSelectionRequest } from '@/security/remote-selection-proxy';

async function proxy(request: Request): Promise<Response> {
  return proxyRemoteSelectionRequest(request);
}

export const GET = proxy;
export const POST = proxy;
