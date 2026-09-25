/**
 * Keyboard shortcuts of the board-search pattern editor: digits place the
 * active symbol with that number (catalog order), `0`/`?` places the unknown
 * marker, Backspace undoes and Enter runs the search.
 */
import {
  digitShortcutIndex,
  hasShortcutModifier,
  type ShortcutKeyboardEvent,
} from '../../lib/keyboard-shortcuts.ts';

export const BOARD_SEARCH_UNKNOWN_SHORTCUT = '0';

export type BoardSearchKeyboardCommand =
  | { readonly kind: 'place_symbol'; readonly symbolCode: string }
  | { readonly kind: 'place_unknown' }
  | { readonly kind: 'search' }
  | { readonly kind: 'undo' };

export function resolveBoardSearchKeyboardCommand(
  event: ShortcutKeyboardEvent,
  symbols: readonly { readonly code: string }[],
): BoardSearchKeyboardCommand | null {
  if (hasShortcutModifier(event)) return null;
  if (event.key === 'Enter') return { kind: 'search' };
  if (event.key === 'Backspace') return { kind: 'undo' };
  if (event.key === BOARD_SEARCH_UNKNOWN_SHORTCUT || event.key === '?') {
    return { kind: 'place_unknown' };
  }
  const index = digitShortcutIndex(event.key);
  const symbol = index === null ? undefined : symbols[index];
  return symbol === undefined
    ? null
    : { kind: 'place_symbol', symbolCode: symbol.code };
}
