import { test, expect } from "@playwright/test";
import { uniqueEmail, registerAndLogin, login } from "./helpers";

test.describe("Authentication", () => {
  test("register a new account via UI", async ({ page }) => {
    const email = uniqueEmail();
    await page.goto("./register");

    await page.fill('input[type="email"]', email);
    await page.fill('input[placeholder="Password"]', "testpassword123");
    await page.fill('input[placeholder="Confirm password"]', "testpassword123");
    await page.selectOption("select", "editor");
    await page.click('button[type="submit"]');

    // Should redirect to login page after successful registration
    await page.waitForURL("**/kms/login");
    await expect(page.locator("h1")).toContainText("Knowledge Base");
  });

  test("login with valid credentials", async ({ page }) => {
    const { email } = await registerAndLogin(page);
    // Should be on home page
    await expect(page.locator("h1")).toContainText("Knowledge Base");
    await expect(page.locator("text=+ New Doc")).toBeVisible();
  });

  test("login with invalid credentials shows error", async ({ page }) => {
    await page.goto("./login");
    await page.fill('input[type="email"]', "nobody@fake.test");
    await page.fill('input[type="password"]', "wrongpassword");
    await page.click('button[type="submit"]');

    // Should stay on login page and show error
    // UI shows either "Invalid credentials" or "Login failed"
    await expect(page.locator("text=/Invalid credentials|Login failed/")).toBeVisible();
  });

  test("logout clears session and redirects to login", async ({ page }) => {
    await registerAndLogin(page);

    await page.click("text=Log out");
    await page.waitForURL("**/kms/login");
    await expect(page.locator('button[type="submit"]')).toContainText("Log in");
  });

  test("unauthenticated users are redirected to login", async ({ page }) => {
    await page.goto("./");
    await page.waitForURL("**/kms/login");
  });
});
