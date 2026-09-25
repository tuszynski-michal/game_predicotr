/**
 * Keyboard shortcuts of the symbol review workspace. Digits map to the active
 * symbols in the catalog order used by "Zarządzanie grami" (displayOrder), so
 * the operator can pick a reassign target without opening the select.
 */
export const SYMBOL_REVIEW_SHORTCUT_SYMBOL_LIMIT = 9;

export type SymbolReviewKeyboardCommand =
  | { readonly kind: 'apply' }
  | { readonly kind: 'cancel' }
  | { readonly kind: 'select_target'; readonly symbolId: string };

export interface SymbolReviewKeyboardEvent {
  readonly altKey: boolean;
  readonly ctrlKey: boolean;
  readonly key: string;
  readonly metaKey: boolean;
}

export function symbolReviewShortcutLabel(index: number): string | null {
  return index >= 0 && index < SYMBOL_REVIEW_SHORTCUT_SYMBOL_LIMIT
    ? String(index + 1)
    : null;
}

export function resolveSymbolReviewKeyboardCommand(
  event: SymbolReviewKeyboardEvent,
  symbols: readonly { readonly id: string }[],
): SymbolReviewKeyboardCommand | null {
  if (event.altKey || event.ctrlKey || event.metaKey) return null;
  if (event.key === 'Enter') return { kind: 'apply' };
  if (event.key === 'Escape') return { kind: 'cancel' };
  if (!/^[1-9]$/.test(event.key)) return null;
  const symbol = symbols[Number(event.key) - 1];
  return symbol === undefined
    ? null
    : { kind: 'select_target', symbolId: symbol.id };
}

/** Typing into filters, the page-number field or a select keeps native keys. */
export function isSymbolReviewTextEntryTarget(
  target: EventTarget | null,
): boolean {
  if (typeof HTMLElement === 'undefined' || !(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) return true;
  const tagName = target.tagName;
  if (tagName === 'INPUT') {
    const type = (target as HTMLInputElement).type;
    return type !== 'checkbox' && type !== 'radio' && type !== 'button';
  }
  return tagName === 'SELECT' || tagName === 'TEXTAREA';
}
