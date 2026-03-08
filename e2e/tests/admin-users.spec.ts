import { test, expect } from "@playwright/test";
import { registerAndLogin, uniqueEmail } from "./helpers";

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

  // Confirm we are on the users page (not redirected to login)
  await expect(page).toHaveURL(/\/kms\/users/);

  await expect(page.locator(`text=${targetEmail}`)).toBeVisible({ timeout: 10000 });

  // Change role from reader to editor
  const row = page.locator(`tbody tr`, { hasText: targetEmail });
  await row.locator("select").selectOption("editor");

  // Wait for API to process the change before reloading
  await page.waitForTimeout(500);

  // Verify the change persisted (reload)
  await page.reload();
  await expect(page.locator(`tbody tr`, { hasText: targetEmail }).locator("select")).toHaveValue("editor");
});

test("admin can delete a user", async ({ page }) => {
  await registerAndLogin(page, { role: "admin" });

  const targetEmail = uniqueEmail();
  const res = await page.request.post("http://localhost:8080/kms/api/auth/register", {
    data: { email: targetEmail, password: "testpassword123", role: "reader" },
  });
  if (!res.ok()) throw new Error(`Register failed: ${res.status()} ${await res.text()}`);

  await page.goto("./users");

  // Confirm we are on the users page (not redirected to login)
  await expect(page).toHaveURL(/\/kms\/users/);

  await expect(page.locator(`text=${targetEmail}`)).toBeVisible({ timeout: 10000 });

  page.on("dialog", d => d.accept());
  const row = page.locator(`tbody tr`, { hasText: targetEmail });
  await row.locator("button:has-text('Delete')").click();

  // Verify the row is gone from the table (not just any text, since success message also contains email)
  await expect(row).not.toBeVisible();
});

test("non-admin redirected away from /users", async ({ page }) => {
  await registerAndLogin(page, { role: "reader" });
  await page.goto("./users");
  // UsersPage redirects non-admins to "/" via React Router navigate("/").
  // PrivateRoute may also redirect to /login if token is not yet in localStorage at load time.
  // Either way, the user should NOT remain on the /users page.
  await expect(page).not.toHaveURL(/\/kms\/users/);
});
