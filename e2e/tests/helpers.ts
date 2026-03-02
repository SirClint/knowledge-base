import { Page } from "@playwright/test";

/** Generate a unique email for test isolation */
export function uniqueEmail(): string {
  return `test-${Date.now()}-${Math.random().toString(36).slice(2, 6)}@example.com`;
}

const TEST_PASSWORD = "testpassword123";

/** Register a new user via API and log in via the UI */
export async function registerAndLogin(
  page: Page,
  options: { role?: string } = {}
) {
  const email = uniqueEmail();
  const role = options.role ?? "admin";

  // Register via API (faster and more reliable than UI)
  const res = await page.request.post("http://localhost:8080/kms/api/auth/register", {
    data: { email, password: TEST_PASSWORD, role },
  });
  if (!res.ok()) {
    throw new Error(`Registration failed: ${res.status()} ${await res.text()}`);
  }

  // Login via UI
  await page.goto("./login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', TEST_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL("**/kms");

  return { email, password: TEST_PASSWORD, role };
}

/** Login an existing user via the UI */
export async function login(page: Page, email: string) {
  await page.goto("./login");
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', TEST_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL("**/kms");
}
