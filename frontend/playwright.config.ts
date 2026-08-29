import { defineConfig } from '@playwright/test'

const node = process.execPath

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    channel: 'chrome',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: '..\\.venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --app-dir .. --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        BOOKLINGO_DATA_DIR: '../data/e2e-test',
        BOOKLINGO_ENV: 'test',
        BOOKLINGO_TEST_TRANSLATION: '公司',
      },
    },
    {
      command: `"${node}" node_modules/vite/bin/vite.js --host 127.0.0.1`,
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
