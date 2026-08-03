function normalizeLineEndings(content) {
  return content.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
}

function firstDifferenceIndex(current, expected) {
  const length = Math.max(current.length, expected.length);
  for (let index = 0; index < length; index += 1) {
    if (current[index] !== expected[index]) {
      return index;
    }
  }
  return -1;
}

export function assertSameGeneratedEntries(current, expected) {
  const currentKeys = [...current.keys()].sort();
  const expectedKeys = [...expected.keys()].sort();

  if (JSON.stringify(currentKeys) !== JSON.stringify(expectedKeys)) {
    throw new Error(
      'Generated Admin API file set is stale. Run: npm run openapi:generate',
    );
  }

  for (const path of expectedKeys) {
    const currentContent = normalizeLineEndings(current.get(path) ?? '');
    const expectedContent = normalizeLineEndings(expected.get(path) ?? '');
    if (currentContent !== expectedContent) {
      const firstDifference = firstDifferenceIndex(
        currentContent,
        expectedContent,
      );
      throw new Error(
        `Generated Admin API file is stale: ${path} at character ${firstDifference}. ` +
          'Run: npm run openapi:generate',
      );
    }
  }
}
