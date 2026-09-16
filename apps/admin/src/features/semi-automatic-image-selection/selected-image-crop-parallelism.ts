export const SELECTED_IMAGE_CROP_ANALYSIS_BATCH_SIZE = 4 as const;

export function selectedImageCropWorkerConcurrency(
  hardwareConcurrency: number | null | undefined,
): number {
  if (
    !Number.isFinite(hardwareConcurrency) ||
    hardwareConcurrency === undefined
  )
    return 2;
  const processors = Math.max(1, Math.floor(hardwareConcurrency ?? 1));
  if (processors >= 12) return 4;
  if (processors >= 8) return 3;
  if (processors >= 4) return 2;
  return 1;
}

export async function mapSelectedImageCropBatch<T, R>(
  items: readonly T[],
  concurrency: number,
  analyze: (item: T, index: number) => Promise<R>,
): Promise<readonly PromiseSettledResult<R>[]> {
  const results = new Array<PromiseSettledResult<R>>(items.length);
  let nextIndex = 0;
  const workerCount = Math.min(
    items.length,
    Math.max(1, Math.floor(concurrency)),
  );
  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (true) {
        const index = nextIndex;
        nextIndex += 1;
        if (index >= items.length) return;
        try {
          results[index] = {
            status: 'fulfilled',
            value: await analyze(items[index]!, index),
          };
        } catch (reason) {
          results[index] = { status: 'rejected', reason };
        }
      }
    }),
  );
  return results;
}
