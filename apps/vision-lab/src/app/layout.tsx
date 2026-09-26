import type { ReactNode } from 'react';
import './style.css';
export const metadata = { title: 'Laboratorium wizji' };
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="pl">
      <body>{children}</body>
    </html>
  );
}
