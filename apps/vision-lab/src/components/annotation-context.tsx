'use client';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import {
  readAnnotations,
  type AnnotationState,
} from '../../../../packages/vision-lab-api-client/src/index';
import { useToast } from '../../../../packages/ui/src/toasts';
const Context = createContext<{
  state: AnnotationState | null;
  accept: (state: AnnotationState) => void;
  refresh: () => Promise<AnnotationState>;
} | null>(null);
export function AnnotationProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AnnotationState | null>(null);
  const notify = useToast();
  const accept = useCallback(
    (next: AnnotationState) =>
      setState((current) =>
        !current || next.revision >= current.revision ? next : current,
      ),
    [],
  );
  const refresh = useCallback(async () => {
    const next = await readAnnotations();
    accept(next);
    return next;
  }, [accept]);
  useEffect(() => {
    void readAnnotations()
      .then(accept)
      .catch(() =>
        notify({
          kind: 'error',
          message:
            'Nie można wczytać anotacji. Sprawdź konfigurację API i ponów odczyt.',
        }),
      );
  }, [accept, notify]);
  return (
    <Context.Provider value={{ state, accept, refresh }}>
      {children}
    </Context.Provider>
  );
}
export function useAnnotations() {
  const value = useContext(Context);
  if (!value) throw new Error('AnnotationProvider missing');
  return value;
}
