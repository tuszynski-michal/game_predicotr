import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { relative } from 'node:path';

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
const prettierPath = fileURLToPath(
  new URL('../../../node_modules/prettier/bin/prettier.cjs', import.meta.url),
);
const generatedPrettierIgnorePath = fileURLToPath(
  new URL('./prettier-generated.ignore', import.meta.url),
);
const execFileAsync = promisify(execFile);

export async function generateAdminApiClient(outputPath) {
  await createClient({
    input: schemaPath,
    output: {
      path: outputPath,
      tsConfigPath,
    },
  });
  await execFileAsync(process.execPath, [
    prettierPath,
    '--write',
    '--ignore-path',
    generatedPrettierIgnorePath,
    `${relative(process.cwd(), outputPath).replaceAll('\\', '/')}/**/*.ts`,
  ]);
}
