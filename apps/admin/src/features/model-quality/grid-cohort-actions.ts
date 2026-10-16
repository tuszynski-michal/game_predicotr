import type { createAdminApiClient } from '@game-predictor/admin-api-client';
import type { GridCohortCommand } from './grid-cohort-command-storage.ts';

export type GridCohortClient = Pick<
  ReturnType<typeof createAdminApiClient>,
  | 'listGridTrainingCohorts'
  | 'getGridTrainingCohort'
  | 'getGridTrainingCohortMembers'
  | 'getGridTrainingCohortEligibility'
  | 'prepareGridTrainingCohort'
  | 'prepareGridTrainingCohortPage'
  | 'materializeGridTrainingCohortPage'
  | 'freezeGridTrainingCohort'
  | 'cancelGridTrainingCohort'
  | 'completeGridSourceIdentities'
>;

export function sendGridCohortCommand(
  api: GridCohortClient,
  game: string,
  command: GridCohortCommand,
) {
  switch (command.kind) {
    case 'prepare':
      return api.prepareGridTrainingCohort(game, command.body);
    case 'prepare-page':
      return api.prepareGridTrainingCohortPage(
        game,
        command.cohortId,
        command.body,
      );
    case 'materialize-page':
      return api.materializeGridTrainingCohortPage(
        game,
        command.cohortId,
        command.body,
      );
    case 'freeze':
      return api.freezeGridTrainingCohort(game, command.cohortId, command.body);
    case 'cancel':
      return api.cancelGridTrainingCohort(game, command.cohortId, command.body);
    case 'complete':
      return api.completeGridSourceIdentities(game, command.body);
  }
}
