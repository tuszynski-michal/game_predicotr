import {
  resolveManualSelectionShortcut,
  type ManualSelectionKeyboardInput,
} from '@game-predictor/manual-image-selection-core';

export function resolveDesktopShortcut(input: ManualSelectionKeyboardInput) {
  const action = resolveManualSelectionShortcut({ ...input, repeat: false });
  const repeatedDecision =
    input.repeat === true &&
    (action === 'accept' || action === 'skip' || action === 'undo');
  return {
    action: repeatedDecision ? null : action,
    preventDefault: action !== null,
  };
}
