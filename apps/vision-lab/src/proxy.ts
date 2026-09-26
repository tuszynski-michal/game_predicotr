import { NextResponse, type NextRequest } from 'next/server';
import { boundary } from './lib/boundary';

export function proxy(request: NextRequest) {
  return boundary(request) ?? NextResponse.next();
}
