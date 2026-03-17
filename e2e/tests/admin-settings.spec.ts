import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8081/kms/api";

test.describe("Admin Settings", () => {
  test("admin can navigate to /admin via nav link", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.locator("a:has-text('Admin')").click();
    await page.waitForURL("**/kms/admin");
    await expect(page).toHaveURL(/\/kms\/admin/);
  });

  test("admin page shows Settings section and User Management section", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.goto("./admin");
    await expect(page.locator("text=Semantic Match Threshold")).toBeVisible();
    await expect(page.locator("text=User Management")).toBeVisible();
  });

  test("threshold input is present with a numeric default", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.goto("./admin");
    const input = page.locator('input[type="number"]');
    await expect(input).toBeVisible();
    const value = await input.inputValue();
    expect(parseFloat(value)).toBeGreaterThanOrEqual(0);
    expect(parseFloat(value)).toBeLessThanOrEqual(1);
  });

  test("can save a new threshold value and see confirmation", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.goto("./admin");

    const input = page.locator('input[type="number"]');
    await input.fill("0.70");
    await page.click("button:has-text('Save')");

    await expect(page.locator("text=Saved.")).toBeVisible({ timeout: 5000 });
  });

  test("saved threshold is persisted to the API", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.goto("./admin");

    const input = page.locator('input[type="number"]');
    await input.fill("0.65");
    await page.click("button:has-text('Save')");
    await expect(page.locator("text=Saved.")).toBeVisible({ timeout: 5000 });

    // Verify the value was saved in the API (avoids DB interference from parallel tests)
    const token = await page.evaluate(() => localStorage.getItem("token") ?? "");
    const res = await page.request.get(`${BASE_API}/admin/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.ok()).toBe(true);
    const data = await res.json();
    expect(data.semantic_threshold).toBe("0.65");
  });

  test("invalid threshold above 1.0 shows validation error", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.goto("./admin");

    // Use "2" — clearly above max but typed as a digit; number inputs allow it
    // (the browser only blocks form submission, not keyboard entry)
    const input = page.locator('input[type="number"]');
    await input.click();
    await page.keyboard.press("Control+a");
    await input.pressSequentially("2");
    await page.click("button:has-text('Save')");

    await expect(page.locator("text=/between 0/")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=Saved.")).not.toBeVisible();
  });

  test("invalid threshold below 0.0 shows validation error", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.goto("./admin");

    const input = page.locator('input[type="number"]');
    await input.click();
    await page.keyboard.press("Control+a");
    await input.pressSequentially("-0.1");
    await page.click("button:has-text('Save')");

    await expect(page.locator("text=/between 0/")).toBeVisible({ timeout: 5000 });
  });

  test("non-numeric threshold shows validation error", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.goto("./admin");

    // Type a non-numeric string by setting value directly to bypass number input sanitization
    await page.locator('input[type="number"]').fill("");
    await page.locator('input[type="number"]').evaluate((el: HTMLInputElement) => { el.value = "abc"; });
    await page.click("button:has-text('Save')");

    await expect(page.locator("text=/between 0/")).toBeVisible({ timeout: 5000 });
  });

  test("reader does not see Admin link in nav", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    await expect(page.locator("a:has-text('Admin')")).not.toBeVisible();
  });

  test("reader is redirected away from /admin", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    await page.goto("./admin");
    await expect(page).not.toHaveURL(/\/kms\/admin/);
  });

  test("user management table is visible on admin page", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.goto("./admin");
    await expect(page.locator("text=(you)")).toBeVisible({ timeout: 10000 });
  });
});
