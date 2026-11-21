// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', 'android/*', 'ios/*', '.data/*', '.expo/*', 'node_modules/*'],
  },
  {
    // Node scripts (mock Pi, icon renderer) and tests run under Node, not React Native.
    files: ['mock-pi/**', 'scripts/**', '**/*.test.ts'],
    languageOptions: { globals: { process: 'readonly', __dirname: 'readonly', Buffer: 'readonly' } },
  },
]);
