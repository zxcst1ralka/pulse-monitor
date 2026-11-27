import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.PULSE_E2E_URL || 'http://localhost',
    trace: 'retain-on-failure',
  },
})
