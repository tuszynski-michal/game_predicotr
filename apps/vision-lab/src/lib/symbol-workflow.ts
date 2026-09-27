/** A lost response retains the exact request; selection changes never save. */
export function symbolWriteSession<T>(write: (request: T) => Promise<unknown>) {
  let pending: T | null = null;
  let busy = false;
  return {
    get pending() {
      return pending;
    },
    get busy() {
      return busy;
    },
    get navigationAllowed() {
      return !busy && pending === null;
    },
    reload() {
      if (busy) throw new Error('SYMBOL_WRITE_PENDING');
      pending = null;
    },
    async submit(request: T) {
      if (busy) throw new Error('SYMBOL_WRITE_PENDING');
      if (pending !== null && pending !== request)
        throw new Error('SYMBOL_RETRY_REQUIRED');
      pending = request;
      busy = true;
      try {
        await write(request);
        pending = null;
      } finally {
        busy = false;
      }
    },
  };
}

export function canMutateSymbolRow(origin: string): boolean {
  return origin === 'lab_human_approved';
}
