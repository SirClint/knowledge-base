import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("About popup", () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page);
  });

  test("About popup shows feature list", async ({ page }) => {
    await page.click("text=About");
    await expect(page.locator("[data-testid='about-feature-list']")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("[data-testid='about-feature-list']")).toContainText("AI-powered ingestion");
    await expect(page.locator("[data-testid='about-feature-list']")).toContainText("Review queue");
  });

  test("About popup Full details link navigates to user guide", async ({ page }) => {
    await page.route("**/kms/api/docs/docs/user-guide.md", route => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 99, title: "User Guide", path: "docs/user-guide.md", body: "# User Guide\n...",
        tags: "[]", owner: "admin", status: "current",
        created_at: null, created_by: null, updated_at: null, updated_by: null,
      }),
    }));
    await page.route("**/kms/api/comments/docs/user-guide.md", route => route.fulfill({
      status: 200, contentType: "application/json", body: "[]",
    }));
    await page.click("text=About");
    await page.click("text=Full details →");
    await expect(page).toHaveURL(/docs\/user-guide\.md/, { timeout: 10000 });
  });

  test("About popup closes on backdrop click", async ({ page }) => {
    await page.click("text=About");
    await expect(page.locator("h2:has-text('Knowledge Base')")).toBeVisible({ timeout: 10000 });
    await page.locator("[data-testid='about-backdrop']").click({ position: { x: 10, y: 400 }, force: true });
    await expect(page.locator("h2:has-text('Knowledge Base')")).not.toBeVisible({ timeout: 5000 });
  });
});
