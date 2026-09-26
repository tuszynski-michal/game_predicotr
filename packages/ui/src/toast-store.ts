export type ToastKind = 'success' | 'error' | 'warning' | 'info';
export type ToastInput = {
  message: string;
  kind: ToastKind;
  operation?: string;
  action?: { label: string; run: () => void };
};
export type Toast = ToastInput & {
  id: number;
  count: number;
  remaining: number;
  paused: boolean;
};
export const toastDuration = () => 4000;
export function enqueueToast(
  items: Toast[],
  input: ToastInput,
  id: number,
): Toast[] {
  const same = items.find(
    (item) => item.message === input.message && item.kind === input.kind,
  );
  if (same)
    return items
      .filter(
        (item) =>
          item.id === same.id ||
          !input.operation ||
          item.operation !== input.operation ||
          item.kind !== 'info',
      )
      .map((item) =>
        item.id === same.id
          ? {
              ...item,
              count: item.count + 1,
              remaining: toastDuration(),
            }
          : item,
      );
  const next = {
    ...input,
    id,
    count: 1,
    remaining: toastDuration(),
    paused: false,
  };
  // Only replace progress from the same operation; unread outcomes stay queued.
  const progress =
    input.operation &&
    items.find(
      (item) => item.operation === input.operation && item.kind === 'info',
    );
  return progress
    ? items.map((item) => (item.id === progress.id ? next : item))
    : [...items, next];
}
export function tickToasts(
  items: Toast[],
  elapsed: number,
  hidden: boolean,
  visible = 3,
): Toast[] {
  if (hidden) return items;
  return items
    .map((item, index) =>
      index < visible && !item.paused
        ? { ...item, remaining: item.remaining - elapsed }
        : item,
    )
    .filter((item) => item.remaining > 0);
}
