import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8081/kms/api";

test.describe("Smoke", () => {
  test("app loads and home page is accessible", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    await expect(page.locator("text=+ New Doc")).toBeVisible();
    await expect(page.locator('input[placeholder="Search docs..."]')).toBeVisible();
  });

  test("AI health endpoint responds", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    const token = await page.evaluate(() => localStorage.getItem("token") ?? "");
    const res = await page.request.get(`${BASE_API}/health/ai`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBe(true);
    const body = await res.json();
    expect(["online", "offline"]).toContain(body.ai);
    if (body.ai === "offline") {
      console.warn("\n⚠️  AI is offline. Ollama may not be reachable from Docker containers.\n");
    }
  });

  test("AI offline warning shown on new doc page when Ollama unreachable", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.route("**/kms/api/health/ai", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ai: "offline" }),
      });
    });
    await page.click("text=+ New Doc");
    await page.waitForURL("**/kms/doc/new");
    await expect(page.locator("text=AI is currently offline")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("button:has-text('Process with AI')")).toBeDisabled();
  });
});
