import type { DictionaryEntry } from '../../../../packages/vision-lab-api-client/src/index';

/** A class receives its technical identity once, when the operator adds it. */
export function createSymbolDictionaryEntry(
  createUuid: () => string = () => crypto.randomUUID(),
): DictionaryEntry {
  const id = createUuid();
  return { id, code: `symbol_${id}`, display_name: '' };
}

/** Names are presentation text; identity always stays with the existing entry. */
export function normalizeSymbolDictionaryEntries(
  entries: readonly DictionaryEntry[],
): DictionaryEntry[] {
  return entries.map((entry) => ({
    ...entry,
    display_name: entry.display_name.trim(),
  }));
}

export function hasBlankSymbolDictionaryName(
  entries: readonly DictionaryEntry[],
): boolean {
  return entries.some((entry) => entry.display_name.length === 0);
}

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
