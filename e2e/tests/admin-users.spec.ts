import { test, expect } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

test.describe("Admin User Management", () => {
  test("admin can see Users link in nav", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await expect(page.locator("a", { hasText: "Admin" })).toBeVisible();
  });

  test("reader cannot see Users link in nav", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    await expect(page.locator("a", { hasText: "Admin" })).not.toBeVisible();
  });

  test("admin can list users and change role", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });

    const targetEmail = uniqueEmail();
    const res = await page.request.post("http://localhost:8081/kms/api/auth/register", {
      data: { email: targetEmail, password: "testpassword123", role: "reader" },
    });
    if (!res.ok()) throw new Error(`Register failed: ${res.status()} ${await res.text()}`);

    await page.goto("./admin");
    await expect(page).toHaveURL(/\/kms\/admin/);
    await expect(page.locator(`text=${targetEmail}`)).toBeVisible({ timeout: 10000 });

    const row = page.locator("tbody tr", { hasText: targetEmail });
    await row.locator("select").selectOption("editor");
    await expect(page.locator("text=Role updated.")).toBeVisible();

    await page.reload();
    await expect(page.locator("tbody tr", { hasText: targetEmail }).locator("select")).toHaveValue("editor");
  });

  test("admin can delete a user", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });

    const targetEmail = uniqueEmail();
    const res = await page.request.post("http://localhost:8081/kms/api/auth/register", {
      data: { email: targetEmail, password: "testpassword123", role: "reader" },
    });
    if (!res.ok()) throw new Error(`Register failed: ${res.status()} ${await res.text()}`);

    await page.goto("./admin");
    await expect(page).toHaveURL(/\/kms\/admin/);
    await expect(page.locator(`text=${targetEmail}`)).toBeVisible({ timeout: 10000 });

    page.once("dialog", d => d.accept());
    const row = page.locator("tbody tr", { hasText: targetEmail });
    await row.locator("button:has-text('Delete')").click();

    await expect(row).not.toBeVisible();
  });

  test("non-admin redirected away from /users", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    await page.goto("./admin");
    // Non-admins are redirected to home — either way, not the /users page
    await expect(page).not.toHaveURL(/\/kms\/admin/);
  });

  test("admin can reset a user's password", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });

    const targetEmail = uniqueEmail();
    const res = await page.request.post("http://localhost:8081/kms/api/auth/register", {
      data: { email: targetEmail, password: "testpassword123", role: "reader" },
    });
    if (!res.ok()) throw new Error(`Register failed: ${res.status()} ${await res.text()}`);

    await page.goto("./admin");
    await expect(page.locator(`text=${targetEmail}`)).toBeVisible({ timeout: 10000 });

    page.once("dialog", async d => {
      if (d.type() === "prompt") await d.accept("newpassword456");
      else await d.accept();
    });

    const row = page.locator("tbody tr", { hasText: targetEmail });
    await row.locator("button:has-text('Reset Password')").click();

    await expect(page.locator(`text=/Password reset for/`)).toBeVisible({ timeout: 5000 });
  });

  test("admin cannot change their own role (select disabled)", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    // Navigate via link to avoid full-page reload issues
    await page.locator("a:has-text('Admin')").click();
    await page.waitForURL("**/kms/admin");
    await expect(page.locator("text=(you)")).toBeVisible({ timeout: 10000 });

    const selfRow = page.locator("tbody tr", { hasText: "(you)" });
    await expect(selfRow.locator("select")).toBeDisabled();
  });

  test("admin cannot delete themselves (button disabled)", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    // Navigate via link to avoid full-page reload issues
    await page.locator("a:has-text('Admin')").click();
    await page.waitForURL("**/kms/admin");
    await expect(page.locator("text=(you)")).toBeVisible({ timeout: 10000 });

    const selfRow = page.locator("tbody tr", { hasText: "(you)" });
    await expect(selfRow.locator("button:has-text('Delete')")).toBeDisabled();
  });
});
