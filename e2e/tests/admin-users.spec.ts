import { test, expect } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

test.describe("Admin User Management", () => {
  test("admin can see Users link in nav", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await expect(page.locator("a", { hasText: "Users" })).toBeVisible();
  });

  test("reader cannot see Users link in nav", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    await expect(page.locator("a", { hasText: "Users" })).not.toBeVisible();
  });

  test("admin can list users and change role", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });

    // Create a target user via API
    const targetEmail = uniqueEmail();
    const res = await page.request.post("http://localhost:8080/kms/api/auth/register", {
      data: { email: targetEmail, password: "testpassword123", role: "reader" },
    });
    if (!res.ok()) throw new Error(`Register failed: ${res.status()} ${await res.text()}`);

    await page.goto("./users");
    await expect(page).toHaveURL(/\/kms\/users/);
    await expect(page.locator(`text=${targetEmail}`)).toBeVisible({ timeout: 10000 });

    // Change role from reader to editor
    const row = page.locator("tbody tr", { hasText: targetEmail });
    await row.locator("select").selectOption("editor");

    // Wait for the API confirmation message before reloading
    await expect(page.locator("text=Role updated.")).toBeVisible();

    // Verify the change persisted (reload)
    await page.reload();
    await expect(page.locator("tbody tr", { hasText: targetEmail }).locator("select")).toHaveValue("editor");
  });

  test("admin can delete a user", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });

    const targetEmail = uniqueEmail();
    const res = await page.request.post("http://localhost:8080/kms/api/auth/register", {
      data: { email: targetEmail, password: "testpassword123", role: "reader" },
    });
    if (!res.ok()) throw new Error(`Register failed: ${res.status()} ${await res.text()}`);

    await page.goto("./users");
    await expect(page).toHaveURL(/\/kms\/users/);
    await expect(page.locator(`text=${targetEmail}`)).toBeVisible({ timeout: 10000 });

    page.on("dialog", d => d.accept());
    const row = page.locator("tbody tr", { hasText: targetEmail });
    await row.locator("button:has-text('Delete')").click();

    // Verify the row is gone (not just the text, since success message also contains email)
    await expect(row).not.toBeVisible();
  });

  test("non-admin redirected away from /users", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    await page.goto("./users");
    // Non-admins are redirected to "/" (home) or "/login" — either way, not /users
    await expect(page).toHaveURL(/\/kms\/(login)?$/);
  });
});
