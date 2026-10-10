import type { AdminApiClient } from '@game-predictor/admin-api-client';
import {
  createSemiAutomaticReviewSourceFile,
  type SemiAutomaticReviewSourceFile,
} from './semi-automatic-selection-actions.ts';

type SourceClient = Pick<
  AdminApiClient,
  | 'listSemiAutomaticImageSelectionSources'
  | 'getSemiAutomaticImageSelectionSourceAsset'
>;

/** Preserve canonical indexes; request only the photo the viewer opens. */
export function createV7ReviewSourceFiles(
  api: SourceClient,
  runId: string,
  sourceCount: number,
): readonly SemiAutomaticReviewSourceFile[] {
  if (!Number.isSafeInteger(sourceCount) || sourceCount < 0) {
    throw new Error('Nieprawidłowa liczba zdjęć źródłowych.');
  }
  return Array.from({ length: sourceCount }, (_, sourceIndex) => ({
    relativePath: `Zdjęcie ${sourceIndex + 1}`,
    handle: {
      kind: 'file',
      async getFile(): Promise<File> {
        const result = await api.listSemiAutomaticImageSelectionSources(
          runId,
          sourceIndex === 0 ? undefined : sourceIndex - 1,
          1,
        );
        const source = result.data?.items[0];
        if (
          result.error !== undefined ||
          source?.sourceIndex !== sourceIndex ||
          !/^[a-f0-9]{64}$/.test(source.checksumSha256)
        ) {
          throw new Error(
            'Nie udało się odczytać metadanych zdjęcia źródłowego.',
          );
        }
        return createSemiAutomaticReviewSourceFile(
          api,
          runId,
          source,
        ).handle.getFile();
      },
    } as unknown as FileSystemFileHandle,
  }));
}
