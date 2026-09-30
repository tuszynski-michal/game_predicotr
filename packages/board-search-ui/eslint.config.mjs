import { defineConfig, globalIgnores } from 'eslint/config';
import nextVitals from 'eslint-config-next/core-web-vitals';
import nextTypeScript from 'eslint-config-next/typescript';

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  {
    // A component library: it has no Next pages directory of its own.
    rules: { '@next/next/no-html-link-for-pages': 'off' },
  },
  globalIgnores(['coverage/**']),
]);
