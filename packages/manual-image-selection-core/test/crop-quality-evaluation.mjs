// Test-only oracle. Never imported by the detector: references must not become
// a filename lookup or a source of algorithm coordinates.
export function evaluateCrop(reference, crop) {
  const issues = [];
  const tolerance = reference.annotationUncertaintyPx;
  if (
    crop.width !== reference.width ||
    crop.height !== reference.height ||
    !Number.isInteger(crop.topY) ||
    !Number.isInteger(crop.bottomY) ||
    crop.topY < 0 ||
    crop.bottomY > reference.height ||
    crop.topY >= crop.bottomY
  ) {
    return ['invalid_crop'];
  }
  const protectedRegions = [...reference.boards, ...reference.labels];
  if (
    protectedRegions.some(
      (box) =>
        crop.topY > box[1] + tolerance || crop.bottomY < box[3] - tolerance,
    )
  ) {
    issues.push('content_removed');
  }
  if (crop.topY < reference.topInterval[0] - tolerance)
    issues.push('excess_top');
  if (crop.topY > reference.topInterval[1] + tolerance)
    issues.push('top_too_tight');
  if (crop.bottomY < reference.bottomInterval[0] - tolerance)
    issues.push('bottom_too_tight');
  if (crop.bottomY > reference.bottomInterval[1] + tolerance)
    issues.push('excess_bottom');
  return issues;
}

export function validateReferences(references) {
  if (!references.length || references.length > 120)
    throw new Error('CORPUS_SIZE');
  const hashes = new Set();
  const directories = new Map();
  for (const ref of references) {
    if (!/^[a-f0-9]{64}$/.test(ref.sha256) || hashes.has(ref.sha256))
      throw new Error('CORPUS_HASH');
    hashes.add(ref.sha256);
    if (!['development', 'holdout'].includes(ref.split))
      throw new Error('CORPUS_SPLIT');
    if (
      directories.has(ref.directory) &&
      directories.get(ref.directory) !== ref.split
    )
      throw new Error('CORPUS_LEAKAGE');
    directories.set(ref.directory, ref.split);
    if (
      !Number.isFinite(ref.annotationUncertaintyPx) ||
      ref.annotationUncertaintyPx < 0
    )
      throw new Error('CORPUS_UNCERTAINTY');
    if (ref.boards.length !== 9 || ref.labels.length !== 9)
      throw new Error('CORPUS_REGIONS');
    for (const [left, top, right, bottom] of [...ref.boards, ...ref.labels]) {
      if (
        ![left, top, right, bottom].every(Number.isFinite) ||
        left < 0 ||
        top < 0 ||
        right > ref.width ||
        bottom > ref.height ||
        left >= right ||
        top >= bottom
      )
        throw new Error('CORPUS_BOX');
    }
    for (const interval of [ref.topInterval, ref.bottomInterval]) {
      if (
        interval.length !== 2 ||
        !interval.every(Number.isInteger) ||
        interval[0] > interval[1]
      )
        throw new Error('CORPUS_INTERVAL');
    }
    // Even the tightest allowed band must contain every annotated region.
    if (
      evaluateCrop(ref, {
        width: ref.width,
        height: ref.height,
        topY: ref.topInterval[1],
        bottomY: ref.bottomInterval[0],
      }).length
    )
      throw new Error('CORPUS_UNSAFE_INTERVAL');
  }
}
