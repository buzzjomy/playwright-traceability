import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  retries: 1,
  reporter: [['json', { outputFile: 'report.json' }], ['list']],
  use: {
    baseURL: 'https://www.google.com',
    locale: 'en-US',
  },
  projects: [{ name: 'chromium' }],
});
