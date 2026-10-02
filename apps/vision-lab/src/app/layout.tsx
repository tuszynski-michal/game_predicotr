import type { ReactNode } from 'react';
import './style.css';
import '../../../../packages/ui/src/toasts.css';
import { ToastProvider } from '../../../../packages/ui/src/toasts';
import { AnnotationProvider } from '../components/annotation-context';
export const metadata = { title: 'Laboratorium wizji' };
export default function Layout({ children }: { children: ReactNode }) {
  return (
    <html lang="pl">
      <body>
        <ToastProvider>
          <AnnotationProvider>{children}</AnnotationProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
