/**
 * Keyboard shortcuts of the symbol review workspace. Digits map to the active
 * symbols in the catalog order used by "Zarządzanie grami" (displayOrder);
 * `0` selects the tenth one. The operator can pick a reassign target without
 * opening the select.
 */
import {
  EXTENDED_DIGIT_SHORTCUT_LIMIT,
  extendedDigitShortcutIndex,
  extendedDigitShortcutLabel,
  hasShortcutModifier,
  isTextEntryKeyboardTarget,
  type ShortcutKeyboardEvent,
} from '../../lib/keyboard-shortcuts.ts';

export const SYMBOL_REVIEW_SHORTCUT_SYMBOL_LIMIT =
  EXTENDED_DIGIT_SHORTCUT_LIMIT;

export type SymbolReviewKeyboardCommand =
  | { readonly kind: 'apply' }
  | { readonly kind: 'cancel' }
  | { readonly kind: 'select_target'; readonly symbolId: string };

export type SymbolReviewKeyboardEvent = ShortcutKeyboardEvent;

export const symbolReviewShortcutLabel = extendedDigitShortcutLabel;

export function resolveSymbolReviewKeyboardCommand(
  event: SymbolReviewKeyboardEvent,
  symbols: readonly { readonly id: string }[],
): SymbolReviewKeyboardCommand | null {
  if (hasShortcutModifier(event)) return null;
  if (event.key === 'Enter') return { kind: 'apply' };
  if (event.key === 'Escape') return { kind: 'cancel' };
  const index = extendedDigitShortcutIndex(event.key);
  const symbol = index === null ? undefined : symbols[index];
  return symbol === undefined
    ? null
    : { kind: 'select_target', symbolId: symbol.id };
}

export const isSymbolReviewTextEntryTarget = isTextEntryKeyboardTarget;
