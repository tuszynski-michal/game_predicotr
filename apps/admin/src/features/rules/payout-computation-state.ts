import type {
  DatasetVersionResponse,
  JobResponse,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';

export const PAYOUT_ALGORITHM_VERSION = 'payout-v2';

export type PayoutReadiness =
  | { readonly ready: true; readonly dataset: DatasetVersionResponse }
  | { readonly ready: false; readonly reason: string };

export function selectPayoutDataset(
  datasets: readonly DatasetVersionResponse[],
  rules: RulesVersionResponse,
): DatasetVersionResponse | null {
  return (
    datasets
      .filter(
        (dataset) =>
          dataset.status === 'published' &&
          dataset.gameId === rules.gameId &&
          dataset.rows === rules.rows &&
          dataset.columns === rules.columns,
      )
      .sort(
        (left, right) =>
          right.version - left.version || left.id.localeCompare(right.id),
      )[0] ?? null
  );
}

export function assessPayoutReadiness(
  rules: RulesVersionResponse,
  datasets: readonly DatasetVersionResponse[],
): PayoutReadiness {
  if (rules.status !== 'published') {
    return {
      ready: false,
      reason: 'Najpierw opublikuj bieżące reguły.',
    };
  }
  const dataset = selectPayoutDataset(datasets, rules);
  if (dataset === null) {
    const hasPublishedDataset = datasets.some(
      (item) => item.status === 'published',
    );
    return {
      ready: false,
      reason: hasPublishedDataset
        ? 'Brak opublikowanego datasetu o wymiarach zgodnych z regułami.'
        : 'Najpierw opublikuj kompletny dataset tej gry.',
    };
  }
  if (dataset.layoutCount === 0) {
    return { ready: false, reason: 'Opublikowany dataset jest pusty.' };
  }
  if (dataset.layoutCount !== dataset.expectedLayoutCount) {
    return {
      ready: false,
      reason: `Dataset jest niekompletny: ${dataset.layoutCount.toLocaleString('pl-PL')} z ${dataset.expectedLayoutCount.toLocaleString('pl-PL')} layoutów.`,
    };
  }
  return { dataset, ready: true };
}

export function selectPayoutJob(
  jobs: readonly JobResponse[],
  datasetVersionId: string,
  rulesVersionId: string,
): JobResponse | null {
  return (
    jobs
      .filter((job) => {
        const payload = job.inputPayload;
        return (
          job.jobType === 'payout' &&
          'datasetVersionId' in payload &&
          'rulesVersionId' in payload &&
          'algorithmVersion' in payload &&
          payload.datasetVersionId === datasetVersionId &&
          payload.rulesVersionId === rulesVersionId &&
          payload.algorithmVersion === PAYOUT_ALGORITHM_VERSION
        );
      })
      .sort(
        (left, right) =>
          Date.parse(right.createdAt) - Date.parse(left.createdAt) ||
          left.id.localeCompare(right.id),
      )[0] ?? null
  );
}

export function isPayoutJobActive(job: JobResponse | null): boolean {
  return job?.status === 'created' || job?.status === 'processing';
}

export function payoutProgressPercent(job: JobResponse): number | null {
  const { current, total } = job.progress;
  if (total === null || total <= 0) return null;
  return Math.min(100, Math.max(0, (current / total) * 100));
}
