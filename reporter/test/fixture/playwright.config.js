// A tiny real Playwright project used by e2e.test.js. No browser is needed:
// none of the tests use the `page` fixture.
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests",
  retries: 1,
  workers: 1,
  projects: [{ name: "alpha" }, { name: "beta" }],
  reporter: [["line"], [require.resolve("../../src/index.js"), JSON.parse(process.env.TRACEABILITY_TEST_OPTIONS || "{}")]],
});
