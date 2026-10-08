/**
 * Shared helpers for workspace-level keyboard shortcuts. Digit shortcuts map to
 * the active symbols of a game in catalog order (displayOrder), the same order
 * shown in "Zarządzanie grami → Symbole".
 */
export const DIGIT_SHORTCUT_LIMIT = 9;
/** Symbol review also maps `0` to the tenth symbol. */
export const EXTENDED_DIGIT_SHORTCUT_LIMIT = 10;

export interface ShortcutKeyboardEvent {
  readonly altKey: boolean;
  readonly ctrlKey: boolean;
  readonly key: string;
  readonly metaKey: boolean;
}

export function hasShortcutModifier(event: ShortcutKeyboardEvent): boolean {
  return event.altKey || event.ctrlKey || event.metaKey;
}

/** `'1'`–`'9'` → 0–8; every other key → null. */
export function digitShortcutIndex(key: string): number | null {
  return /^[1-9]$/.test(key) ? Number(key) - 1 : null;
}

export function digitShortcutLabel(index: number): string | null {
  return index >= 0 && index < DIGIT_SHORTCUT_LIMIT ? String(index + 1) : null;
}

/** `'1'`–`'9'` → 0–8, `'0'` → 9; every other key → null. */
export function extendedDigitShortcutIndex(key: string): number | null {
  if (key === '0') return 9;
  return digitShortcutIndex(key);
}

/** 0–8 → `'1'`–`'9'`, 9 → `'0'`; every other index → null. */
export function extendedDigitShortcutLabel(index: number): string | null {
  if (!Number.isInteger(index) || index < 0) return null;
  if (index === 9) return '0';
  return digitShortcutLabel(index);
}

/** Typing into text fields or a select keeps native keys. */
export function isTextEntryKeyboardTarget(target: EventTarget | null): boolean {
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
