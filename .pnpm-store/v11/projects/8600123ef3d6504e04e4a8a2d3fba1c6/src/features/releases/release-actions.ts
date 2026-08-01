import type {
  AdminApiClient,
  JobResponse,
  MobileReleaseBuildResponse,
  MobileReleaseCreate,
  MobileReleaseResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import type { ReleaseGameSource } from './release-state.ts';

export type ReleasesClient = Pick<
  AdminApiClient,
  | 'buildMobileRelease'
  | 'createMobileRelease'
  | 'deleteMobileRelease'
  | 'downloadMobileReleaseApk'
  | 'getJob'
  | 'getMobileRelease'
  | 'listDatasetVersions'
  | 'listGames'
  | 'listMobileReleases'
  | 'listRulesVersions'
  | 'previewMobileReleaseDeletion'
  | 'previewGameLayoutDataReset'
  | 'resetGameLayoutData'
  | 'retryJob'
>;

export type LoadReleaseWorkspaceResult =
  | {
      readonly ok: true;
      readonly releases: readonly MobileReleaseResponse[];
      readonly sources: readonly ReleaseGameSource[];
    }
  | { readonly error: string; readonly ok: false };

export async function loadReleaseWorkspace(
  api: ReleasesClient,
): Promise<LoadReleaseWorkspaceResult> {
  try {
    const [gamesResult, releasesResult] = await Promise.all([
      api.listGames(),
      api.listMobileReleases(),
    ]);
    if (
      gamesResult.error !== undefined ||
      gamesResult.data === undefined ||
      releasesResult.error !== undefined ||
      releasesResult.data === undefined
    ) {
      return {
        error: apiErrorMessage(
          gamesResult.error ?? releasesResult.error,
          'Nie udało się pobrać konfiguracji wydań Android.',
        ),
        ok: false,
      };
    }

    const activeGames = gamesResult.data
      .filter((game) => game.status === 'active')
      .toSorted(
        (left, right) =>
          left.code.localeCompare(right.code) ||
          left.id.localeCompare(right.id),
      );
    const sourceResults = await Promise.all(
      activeGames.map(async (game) => {
        const [datasetsResult, rulesResult] = await Promise.all([
          api.listDatasetVersions(game.id),
          api.listRulesVersions(game.id),
        ]);
        if (
          datasetsResult.error !== undefined ||
          datasetsResult.data === undefined ||
          rulesResult.error !== undefined ||
          rulesResult.data === undefined
        ) {
          return {
            error: datasetsResult.error ?? rulesResult.error,
            game,
          } as const;
        }
        return {
          datasets: datasetsResult.data,
          game,
          rulesVersions: rulesResult.data,
        } as const;
      }),
    );
    const failed = sourceResults.find((result) => 'error' in result);
    if (failed !== undefined && 'error' in failed) {
      return {
        error: apiErrorMessage(
          failed.error,
          `Nie udało się pobrać źródeł gry ${failed.game.code}.`,
        ),
        ok: false,
      };
    }
    return {
      ok: true,
      releases: releasesResult.data,
      sources: sourceResults as readonly ReleaseGameSource[],
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type CreateReleaseResult =
  | { readonly ok: true; readonly release: MobileReleaseResponse }
  | { readonly error: string; readonly ok: false };

export async function createRelease(
  api: ReleasesClient,
  body: MobileReleaseCreate,
): Promise<CreateReleaseResult> {
  try {
    const result = await api.createMobileRelease(body);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć draftu wydania.',
        ),
        ok: false,
      };
    }
    return { ok: true, release: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type StartReleaseBuildResult =
  | { readonly build: MobileReleaseBuildResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function startReleaseBuild(
  api: ReleasesClient,
  releaseId: string,
): Promise<StartReleaseBuildResult> {
  try {
    const result = await api.buildMobileRelease(releaseId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się uruchomić kontrolowanego builda.',
        ),
        ok: false,
      };
    }
    return { build: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type CreateAndStartReleaseResult =
  | {
      readonly build: MobileReleaseBuildResponse;
      readonly ok: true;
      readonly release: MobileReleaseResponse;
    }
  | {
      readonly error: string;
      readonly ok: false;
      readonly release: MobileReleaseResponse | null;
    };

export async function createAndStartRelease(
  api: ReleasesClient,
  body: MobileReleaseCreate,
): Promise<CreateAndStartReleaseResult> {
  const created = await createRelease(api, body);
  if (!created.ok) {
    return { error: created.error, ok: false, release: null };
  }
  const started = await startReleaseBuild(api, created.release.id);
  if (!started.ok) {
    return {
      error: started.error,
      ok: false,
      release: created.release,
    };
  }
  return {
    build: started.build,
    ok: true,
    release: created.release,
  };
}

export type RefreshReleaseResult =
  | {
      readonly job: JobResponse | null;
      readonly ok: true;
      readonly release: MobileReleaseResponse;
    }
  | { readonly error: string; readonly ok: false };

export async function refreshRelease(
  api: ReleasesClient,
  releaseId: string,
): Promise<RefreshReleaseResult> {
  try {
    const releaseResult = await api.getMobileRelease(releaseId);
    if (releaseResult.error !== undefined || releaseResult.data === undefined) {
      return {
        error: apiErrorMessage(
          releaseResult.error,
          'Nie udało się odświeżyć wydania.',
        ),
        ok: false,
      };
    }
    const release = releaseResult.data;
    if (release.buildJobId === null) {
      return { job: null, ok: true, release };
    }
    const jobResult = await api.getJob(release.buildJobId);
    if (jobResult.error !== undefined || jobResult.data === undefined) {
      return {
        error: apiErrorMessage(
          jobResult.error,
          'Nie udało się pobrać powiązanego joba.',
        ),
        ok: false,
      };
    }
    return { job: jobResult.data, ok: true, release };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type RetryReleaseBuildResult =
  | { readonly job: JobResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function retryReleaseBuild(
  api: ReleasesClient,
  jobId: string,
): Promise<RetryReleaseBuildResult> {
  try {
    const result = await api.retryJob(jobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się wznowić workflow wydania.',
        ),
        ok: false,
      };
    }
    return { job: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type DownloadReleaseApkResult =
  | { readonly artifact: Blob | File; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function downloadReleaseApk(
  api: ReleasesClient,
  releaseId: string,
): Promise<DownloadReleaseApkResult> {
  try {
    const result = await api.downloadMobileReleaseApk(releaseId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać zweryfikowanego APK.',
        ),
        ok: false,
      };
    }
    return { artifact: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
