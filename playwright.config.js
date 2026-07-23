const { defineConfig } = require('@playwright/test');

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8000';
const parsedBaseURL = new URL(baseURL);
if (
  parsedBaseURL.protocol !== 'http:' ||
  parsedBaseURL.hostname !== '127.0.0.1' ||
  !parsedBaseURL.port ||
  parsedBaseURL.username ||
  parsedBaseURL.password ||
  baseURL !== parsedBaseURL.origin
) {
  throw new Error(
    `PLAYWRIGHT_BASE_URL must be a canonical credential-free loopback origin with an explicit port, got ${baseURL}`,
  );
}
const port = parsedBaseURL.port;
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
  UV_CACHE_DIR: process.env.UV_CACHE_DIR || '.uv-cache',
  UV_PYTHON_INSTALL_DIR: process.env.UV_PYTHON_INSTALL_DIR || '.uv-python',
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
      // The committed baselines are generated on Windows, while required CI uses
      // the pinned Linux Playwright container. Keep visual regressions bounded
      // while allowing the observed cross-platform font rasterization delta.
      maxDiffPixels: 5000,
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
      name: 'chromium-desktop',
      use: { viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'chromium-mobile',
      use: { viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    command: `uv run python src/manage.py migrate --noinput && uv run python src/manage.py runserver 127.0.0.1:${port} --noreload`,
    env: serverEnvironment,
    url: `${baseURL}/healthz/`,
    reuseExistingServer: false,
  },
});
