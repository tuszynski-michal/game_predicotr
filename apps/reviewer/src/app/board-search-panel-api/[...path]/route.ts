import { proxyBoardSearchPanelRequest } from '@/security/board-search-panel-proxy';

async function proxy(request: Request): Promise<Response> {
  return proxyBoardSearchPanelRequest(request);
}
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
