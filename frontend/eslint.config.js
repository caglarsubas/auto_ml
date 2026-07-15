// @ts-check
const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');
const angular = require('angular-eslint');

module.exports = tseslint.config(
  {
    files: ['**/*.ts'],
    ignores: ['e2e/**', 'dist/**', 'coverage/**', '.angular/**'],
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
      ...angular.configs.tsRecommended,
    ],
    processor: angular.processInlineTemplates,
    rules: {
      '@angular-eslint/directive-selector': [
        'warn',
        { type: 'attribute', prefix: 'app', style: 'camelCase' },
      ],
      '@angular-eslint/component-selector': [
        'warn',
        { type: 'element', prefix: 'app', style: 'kebab-case' },
      ],
      // Adoption baseline on a legacy codebase: keep the linter green while
      // still surfacing issues. Tighten these to 'error' as the code is cleaned.
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'warn',
      '@typescript-eslint/no-inferrable-types': 'off',
      'no-empty': 'warn',
      'no-case-declarations': 'off',
      'no-prototype-builtins': 'off',
      'no-useless-assignment': 'warn',
    },
  },
  {
    files: ['**/*.html'],
    ignores: ['e2e/**', 'dist/**', 'coverage/**'],
    extends: [
      ...angular.configs.templateRecommended,
    ],
    rules: {
      '@angular-eslint/template/eqeqeq': 'warn',
    },
  },
);
