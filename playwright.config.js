const { defineConfig } = require('@playwright/test');

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8000';
const parsedBaseURL = new URL(baseURL);
if (parsedBaseURL.protocol !== 'http:' || parsedBaseURL.hostname !== '127.0.0.1') {
  throw new Error(`PLAYWRIGHT_BASE_URL must use http://127.0.0.1, got ${baseURL}`);
}
const port = parsedBaseURL.port || '80';
const serverEnvironment = {
  APP_ENV: 'test',
  DJANGO_DEBUG: 'true',
  POSTGRES_DB: process.env.POSTGRES_DB || 'marketplace',
  POSTGRES_USER: process.env.POSTGRES_USER || 'marketplace',
  POSTGRES_PASSWORD:
    process.env.POSTGRES_PASSWORD || 'development-only-database-password',
  POSTGRES_HOST: process.env.POSTGRES_HOST || '127.0.0.1',
  POSTGRES_PORT: process.env.POSTGRES_PORT || '55432',
  POSTGRES_SSLMODE: process.env.POSTGRES_SSLMODE || 'disable',
  REDIS_URL: process.env.REDIS_URL || 'redis://127.0.0.1:56379/0',
};

module.exports = defineConfig({
  testDir: './tests/e2e',
  snapshotPathTemplate: '{testDir}/snapshots/{testFilePath}/{arg}{ext}',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? 'line' : 'list',
  expect: {
    toHaveScreenshot: {
      animations: 'disabled',
    },
  },
  use: {
    baseURL,
    browserName: 'chromium',
    locale: 'ko-KR',
    timezoneId: 'UTC',
    reducedMotion: 'reduce',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium-mobile',
      use: { viewport: { width: 390, height: 844 } },
    },
    {
      name: 'chromium-desktop',
      use: { viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: `uv run python src/manage.py runserver 127.0.0.1:${port} --noreload`,
    env: serverEnvironment,
    url: `${baseURL}/healthz/`,
    reuseExistingServer: !process.env.CI,
  },
});
