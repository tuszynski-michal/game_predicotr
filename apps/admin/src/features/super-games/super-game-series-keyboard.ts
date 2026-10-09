/**
 * Keyboard shortcuts of the „Supergry” series view (TASK-0934). Digits pick a
 * super symbol from the list shown in the select (`1`–`9`, `0` for the
 * tenth), `Enter` saves, `Escape` cancels the candidate and ← / → move along
 * the carousel. Shortcuts stay inactive in text fields and with modifiers.
 */
import {
  EXTENDED_DIGIT_SHORTCUT_LIMIT,
  extendedDigitShortcutIndex,
  extendedDigitShortcutLabel,
  hasShortcutModifier,
  isTextEntryKeyboardTarget,
  type ShortcutKeyboardEvent,
} from '../../lib/keyboard-shortcuts.ts';

export const SUPER_GAME_SERIES_SHORTCUT_SYMBOL_LIMIT =
  EXTENDED_DIGIT_SHORTCUT_LIMIT;

export type SuperGameSeriesKeyboardCommand =
  | { readonly kind: 'save' }
  | { readonly kind: 'cancel' }
  | { readonly kind: 'previous' }
  | { readonly kind: 'next' }
  | { readonly kind: 'select_symbol'; readonly symbolId: string };

export interface SuperGameSeriesKeyboardEvent extends ShortcutKeyboardEvent {
  readonly shiftKey?: boolean;
}

export const superGameSeriesShortcutLabel = extendedDigitShortcutLabel;

/**
 * `symbols` is the list shown in the select (ordinary symbols only, catalog
 * order): the digit labels printed next to the options follow the same order.
 */
export function resolveSuperGameSeriesKeyboardCommand(
  event: SuperGameSeriesKeyboardEvent,
  symbols: readonly { readonly id: string }[],
): SuperGameSeriesKeyboardCommand | null {
  if (hasShortcutModifier(event) || event.shiftKey === true) return null;
  if (event.key === 'Enter') return { kind: 'save' };
  if (event.key === 'Escape') return { kind: 'cancel' };
  if (event.key === 'ArrowLeft') return { kind: 'previous' };
  if (event.key === 'ArrowRight') return { kind: 'next' };
  const index = extendedDigitShortcutIndex(event.key);
  const symbol = index === null ? undefined : symbols[index];
  return symbol === undefined
    ? null
    : { kind: 'select_symbol', symbolId: symbol.id };
}

export const isSuperGameSeriesTextEntryTarget = isTextEntryKeyboardTarget;

/**
 * A shortcut is ignored while the operator types or works in a select. A
 * focused button or link keeps its own `Enter` (activation), so that the
 * carousel buttons do not also save the symbol.
 */
export function isSuperGameSeriesShortcutBlocked(
  target: EventTarget | null,
  key: string,
): boolean {
  if (isTextEntryKeyboardTarget(target)) return true;
  if (
    key === 'Enter' &&
    typeof HTMLElement !== 'undefined' &&
    target instanceof HTMLElement
  ) {
    return target.tagName === 'BUTTON' || target.tagName === 'A';
  }
  return false;
}
