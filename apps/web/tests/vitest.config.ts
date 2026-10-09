// Reuse the repo's installed test runner without adding web dependencies.
export default {
  resolve: {
    alias: {
      vitest: new URL('../../../workers/api/node_modules/vitest/dist/index.js', import.meta.url)
        .pathname,
    },
  },
  test: { environment: 'node', include: ['tests/**/*.test.ts'] },
};
