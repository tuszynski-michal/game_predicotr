import { proxyBoardSearchShareRequest } from '@/security/board-search-share-proxy';

async function proxy(request: Request): Promise<Response> {
  return proxyBoardSearchShareRequest(request);
}

export const GET = proxy;
export const POST = proxy;
