import { fileURLToPath } from 'node:url';

import { createClient } from '@hey-api/openapi-ts';

export const schemaPath = fileURLToPath(
  new URL('../openapi/openapi.json', import.meta.url),
);
export const generatedDirectory = fileURLToPath(
  new URL('../src/generated/', import.meta.url),
);
const tsConfigPath = fileURLToPath(
  new URL('../tsconfig.json', import.meta.url),
);

export async function generateAdminApiClient(outputPath) {
  await createClient({
    input: schemaPath,
    output: {
      module: {
        extension: '.js',
      },
      path: outputPath,
      postProcess: ['prettier'],
      tsConfigPath,
    },
  });
}
