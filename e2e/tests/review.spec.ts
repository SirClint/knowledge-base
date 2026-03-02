import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("Review Queue", () => {
  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page);
  });

  test("navigate to review queue page", async ({ page }) => {
    await page.click("text=Review Queue");
    await page.waitForURL("**/kms/review");
    // Page should load without errors
    await expect(page.locator("h1")).toBeVisible();
  });

  test("review queue loads without error", async ({ page }) => {
    await page.goto("./review");
    // Should not show any error messages
    await expect(page.locator("text=error")).not.toBeVisible();
    await expect(page.locator("text=failed")).not.toBeVisible();
  });
});
