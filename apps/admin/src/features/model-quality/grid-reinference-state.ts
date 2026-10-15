import type {
  AdminApiClient,
  GridReinferenceSelector,
} from '@game-predictor/admin-api-client';
import type { GridCommand } from './grid-reinference-command';

export const gridReinferenceStateLabels: Readonly<Record<string, string>> = {
  preparing: 'Przygotowywanie zakresu',
  prepared: 'Zakres gotowy',
  frozen: 'Zakres zamrożony',
  queued: 'Oczekuje na rozpoznanie',
  running: 'Rozpoznawanie w toku',
  cancel_requested: 'Oczekuje na anulowanie',
  cancelled: 'Anulowano',
  failed: 'Błąd',
  completed: 'Ukończono',
};

export type GridReinferenceClient = Pick<
  AdminApiClient,
  | 'listGridReinferenceOperations'
  | 'getGridReinference'
  | 'getGridReinferenceTargets'
  | 'prepareGridReinference'
  | 'freezeGridReinference'
  | 'acknowledgeGridReinferencePilot'
  | 'startGridReinference'
  | 'resumeGridReinference'
  | 'cancelGridReinference'
>;

export const defaultGridSelector = (): GridReinferenceSelector => ({
  categories: ['grid_issue', 'deferred'],
  importJobIds: [],
  sequenceStart: null,
  sequenceEnd: null,
});

export function sendGridCommand(
  api: GridReinferenceClient,
  game: string,
  command: GridCommand,
) {
  switch (command.kind) {
    case 'prepare':
      return api.prepareGridReinference(game, command.body);
    case 'freeze':
      return api.freezeGridReinference(game, command.operationId, command.body);
    case 'ack':
      return api.acknowledgeGridReinferencePilot(
        game,
        command.operationId,
        command.body,
      );
    case 'start':
      return api.startGridReinference(game, command.operationId, command.body);
    case 'resume':
      return api.resumeGridReinference(game, command.operationId, command.body);
    case 'cancel':
      return api.cancelGridReinference(game, command.operationId, command.body);
  }
}
