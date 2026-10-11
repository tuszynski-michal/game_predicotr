import tseslint from 'typescript-eslint';
export default tseslint.config(
  { ignores: ['dist/**', 'out/**'] },
  ...tseslint.configs.recommended,
  {
    files: ['**/*.mjs'],
    languageOptions: {
      globals: {
        console: 'readonly',
        process: 'readonly',
        setTimeout: 'readonly',
      },
    },
  },
);
