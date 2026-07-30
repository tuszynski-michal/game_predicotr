import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import '../../../admin/src/app/globals.css';
import './reviewer.css';

export const metadata: Metadata = {
  title: 'Game Predictor Reviewer',
  description: 'Lokalne stanowisko zatwierdzania plansz',
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
