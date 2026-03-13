import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  globalSetup: "./globalSetup",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:8081/kms/",
    headless: true,
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
  ],
});
