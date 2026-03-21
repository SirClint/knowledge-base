import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("Review Queue", () => {
  test.beforeEach(async ({ page }) => {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await registerAndLogin(page);
  });

  test("navigate to review queue page via nav link", async ({ page }) => {
    await page.click("text=Review Queue");
    await page.waitForURL("**/kms/review");
    await expect(page.locator("h1")).toBeVisible();
  });

  test("review queue loads without error", async ({ page }) => {
    await page.goto("./review");
    await expect(page.locator("text=error")).not.toBeVisible();
    await expect(page.locator("text=failed")).not.toBeVisible();
  });

  test("empty queue shows 'No docs need review' message", async ({ page }) => {
    await page.route("http://localhost:8081/kms/api/review/queue", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto("./review");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("text=No docs need review")).toBeVisible({ timeout: 10000 });
  });

  test("queue item shown and can be marked as reviewed", async ({ page }) => {
    await page.route("http://localhost:8081/kms/api/review/queue", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{
          id: 9999,
          path: "personal/stale-doc.md",
          title: "Stale Review Doc",
          last_reviewed: "never",
          reason: "Content may be outdated",
        }]),
      });
    });
    await page.route("http://localhost:8081/kms/api/review/9999/mark-reviewed", async route => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true }) });
    });

    await page.goto("./review");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("text=Stale Review Doc")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("text=Content may be outdated")).toBeVisible();

    await page.click("button:has-text('Mark reviewed')");

    await expect(page.locator("text=Stale Review Doc")).not.toBeVisible();
    await expect(page.locator("text=No docs need review")).toBeVisible();
  });

  test("clicking queue item title navigates to the doc", async ({ page }) => {
    await page.route("http://localhost:8081/kms/api/review/queue", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{
          id: 9998,
          path: "personal/review-link-doc.md",
          title: "Review Link Doc",
          last_reviewed: "never",
        }]),
      });
    });

    await page.goto("./review");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("text=Review Link Doc")).toBeVisible({ timeout: 10000 });

    await page.click("text=Review Link Doc");
    await expect(page).toHaveURL(/personal\/review-link-doc\.md/);
  });

  test("Back link returns to home", async ({ page }) => {
    await page.click("text=Review Queue");
    await page.waitForURL("**/kms/review");
    await expect(page.locator("a:has-text('← Back')")).toBeVisible({ timeout: 10000 });
    await page.click("a:has-text('← Back')");
    await expect(page.locator("text=+ Ingest")).toBeVisible({ timeout: 10000 });
  });
});
