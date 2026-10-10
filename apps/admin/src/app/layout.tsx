import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import './globals.css';
import '@game-predictor/board-search-ui/management.css';
import '@game-predictor/board-search-ui/board-search.css';

export const metadata: Metadata = {
  title: 'Game Predictor Admin',
  description: 'Lokalny panel konfiguracji Game Predictor',
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="pl">
      <body>{children}</body>
    </html>
  );
}
