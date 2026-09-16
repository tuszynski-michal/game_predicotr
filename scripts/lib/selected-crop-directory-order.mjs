export function selectedCropSourceDirectories(entries) {
  return entries
    .filter(
      (entry) =>
        entry.isDirectory() &&
        !entry.isSymbolicLink() &&
        !entry.name.endsWith(' cut') &&
        /^\s*\d+/.test(entry.name),
    )
    .sort(
      (left, right) =>
        parseInt(left.name) - parseInt(right.name) ||
        left.name.localeCompare(right.name),
    );
}
