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
  enqueueToast,
  tickToasts,
  type Toast,
  type ToastInput,
} from './toast-store';

const Context = createContext<(input: ToastInput) => void>(() => {});
const names = {
  success: 'Sukces',
  error: 'Błąd',
  warning: 'Ostrzeżenie',
  info: 'Informacja',
};
let serial = 0;
export const useToast = () => useContext(Context);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const notify = useCallback(
    (input: ToastInput) =>
      setItems((current) => enqueueToast(current, input, ++serial)),
    [],
  );
  useEffect(() => {
    let last = performance.now();
    const reset = () => {
      last = performance.now();
    };
    document.addEventListener('visibilitychange', reset);
    const timer = setInterval(() => {
      const now = performance.now();
      const elapsed = now - last;
      last = now;
      setItems((current) => tickToasts(current, elapsed, document.hidden));
    }, 250);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', reset);
    };
  }, []);
  const dismiss = (id: number) =>
    setItems((current) => current.filter((item) => item.id !== id));
  const pause = (id: number, value: boolean) =>
    setItems((current) =>
      current.map((item) =>
        item.id === id ? { ...item, paused: value } : item,
      ),
    );
  return (
    <Context.Provider value={notify}>
      {children}
      <aside className="shared-toast-stack" aria-label="Powiadomienia">
        {items.slice(0, 3).map((item) => (
          <div
            key={item.id}
            className={`shared-toast shared-toast-${item.kind}`}
            onMouseEnter={() => pause(item.id, true)}
            onMouseLeave={(event) =>
              pause(
                item.id,
                event.currentTarget.contains(document.activeElement),
              )
            }
            onFocus={() => pause(item.id, true)}
            onBlur={(event) =>
              pause(
                item.id,
                event.currentTarget.matches(':hover') ||
                  event.currentTarget.contains(event.relatedTarget),
              )
            }
            onClick={() => dismiss(item.id)}
          >
            <div
              role={
                item.kind === 'error' || item.kind === 'warning'
                  ? 'alert'
                  : 'status'
              }
            >
              <strong>
                {names[item.kind]}
                {item.count > 1 ? ` ×${item.count}` : ''}
              </strong>
              <p>{item.message}</p>
            </div>
            {item.action && (
              <button
                onClick={(event) => {
                  event.stopPropagation();
                  item.action?.run();
                }}
              >
                {item.action.label}
              </button>
            )}
            <button
              aria-label={`Zamknij: ${item.message}`}
              onClick={(event) => {
                event.stopPropagation();
                dismiss(item.id);
              }}
            >
              Zamknij
            </button>
          </div>
        ))}
        {items.length > 3 && (
          <span className="shared-toast-queue">
            W kolejce: {items.length - 3}
          </span>
        )}
      </aside>
    </Context.Provider>
  );
}
