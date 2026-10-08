import { proxyManagementRequest } from '@/security/management-proxy';

async function proxy(request: Request): Promise<Response> {
  return proxyManagementRequest(request);
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
