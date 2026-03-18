/**
 * Real (non-mocked) AI ingestion E2E tests.
 *
 * These tests hit the actual Ollama endpoint so they catch:
 *  - The full navigate→banner flow in the UI (the React state bug class)
 *  - AI response parsing and body formatting regressions
 *  - Folder-name quality issues (e.g. AI returning "subfolder")
 *
 * All tests skip gracefully when Ollama is offline.
 */
import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8081/kms/api";
const AI_TIMEOUT = 90_000; // Ollama can be slow on cold start

async function isAiOnline(page: import("@playwright/test").Page): Promise<boolean> {
  try {
    const res = await page.request.get(`${BASE_API}/health/ai`);
    const body = await res.json();
    return body.ai === "online";
  } catch {
    return false;
  }
}

async function deleteDoc(page: import("@playwright/test").Page, docPath: string) {
  const token = await page.evaluate(() => localStorage.getItem("token") ?? "");
  await page.request.delete(`${BASE_API}/docs/${docPath}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

test.describe("Real AI Ingestion (requires Ollama)", () => {
  let createdPath: string | null = null;

  test.beforeEach(async ({ page }) => {
    createdPath = null;
    await registerAndLogin(page, { role: "admin" });
  });

  test.afterEach(async ({ page }) => {
    if (createdPath) {
      await deleteDoc(page, createdPath).catch(() => {});
    }
  });

  test("blue banner shows immediately after ingest (no refresh needed)", async ({ page }) => {
    test.setTimeout(AI_TIMEOUT);

    if (!(await isAiOnline(page))) {
      test.skip(true, "Ollama is offline — skipping real AI test");
      return;
    }

    await page.goto("./doc/new");
    await page.waitForURL("**/kms/doc/new");

    await page.fill(
      "textarea",
      "Team meeting notes from Q1 planning session. " +
      "Discussed budget allocation of $50,000 for engineering. " +
      "Key decisions: hire 2 engineers, upgrade laptops, migrate to new CI system."
    );
    await page.click("button:has-text('Process with AI')");

    // Wait for navigation away from /doc/new — AI processing can take a while
    await page.waitForURL(/\/kms\/doc\/(?!new)/, { timeout: AI_TIMEOUT });

    // Extract path from URL for cleanup
    const url = new URL(page.url());
    createdPath = url.pathname.replace(/^\/kms\/doc\//, "");

    // Banner must be visible immediately — no page refresh required
    const banner = page.locator("text=🤖").first();
    await expect(banner).toBeVisible({ timeout: 5000 });

    // Banner must contain a non-trivial reason (not empty)
    const bannerText = await banner.textContent();
    expect(bannerText?.length).toBeGreaterThan(10);
  });

  test("AI reason explains the folder/action choice", async ({ page }) => {
    test.setTimeout(AI_TIMEOUT);

    if (!(await isAiOnline(page))) {
      test.skip(true, "Ollama is offline — skipping real AI test");
      return;
    }

    await page.goto("./doc/new");
    await page.fill(
      "textarea",
      "Deployment runbook for the KMS API service. " +
      "Steps: 1. Run backup.sh. 2. Merge PR to main. 3. Run deploy.sh. 4. Verify health endpoint."
    );
    await page.click("button:has-text('Process with AI')");

    await page.waitForURL(/\/kms\/doc\/(?!new)/, { timeout: AI_TIMEOUT });
    const url = new URL(page.url());
    createdPath = url.pathname.replace(/^\/kms\/doc\//, "");

    // Path should not contain generic folder names
    expect(createdPath).not.toMatch(/\/subfolder\//);
    expect(createdPath).not.toMatch(/\/misc\//);
    expect(createdPath).not.toMatch(/\/new\//);

    // Banner must show and mention folder/action (reason should be informative)
    const banner = page.locator("text=🤖").first();
    await expect(banner).toBeVisible({ timeout: 5000 });
    const bannerText = await banner.textContent() ?? "";
    // Reason should reference either "created" / "updated" and a folder name
    expect(bannerText.toLowerCase()).toMatch(/creat|updat/);
  });

  test("banner dismiss button hides banner", async ({ page }) => {
    test.setTimeout(AI_TIMEOUT);

    if (!(await isAiOnline(page))) {
      test.skip(true, "Ollama is offline — skipping real AI test");
      return;
    }

    await page.goto("./doc/new");
    await page.fill("textarea", "Pasta recipe: boil water, add pasta, cook 10 minutes, drain, add sauce.");
    await page.click("button:has-text('Process with AI')");

    await page.waitForURL(/\/kms\/doc\/(?!new)/, { timeout: AI_TIMEOUT });
    const url = new URL(page.url());
    createdPath = url.pathname.replace(/^\/kms\/doc\//, "");

    const banner = page.locator("text=🤖").first();
    await expect(banner).toBeVisible({ timeout: 5000 });

    // Click × to dismiss
    await page.click('button[aria-label="Dismiss"]');
    await expect(banner).not.toBeVisible();
  });

  test("AI-generated body has markdown structure (headings or bold)", async ({ page }) => {
    test.setTimeout(AI_TIMEOUT);

    if (!(await isAiOnline(page))) {
      test.skip(true, "Ollama is offline — skipping real AI test");
      return;
    }

    await page.goto("./doc/new");
    await page.fill(
      "textarea",
      "Security checklist for production deployments:\n" +
      "- Always run backup before deploying\n" +
      "- Verify health endpoint responds after restart\n" +
      "- Check logs for errors in first 5 minutes\n" +
      "- Confirm rollback plan is ready"
    );
    await page.click("button:has-text('Process with AI')");

    await page.waitForURL(/\/kms\/doc\/(?!new)/, { timeout: AI_TIMEOUT });
    const url = new URL(page.url());
    createdPath = url.pathname.replace(/^\/kms\/doc\//, "");

    // Fetch the doc body via API and check for markdown structure
    const token = await page.evaluate(() => localStorage.getItem("token") ?? "");
    const res = await page.request.get(`${BASE_API}/docs/${createdPath}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const doc = await res.json();

    // Body should contain at least one markdown heading or bold text
    const hasHeading = /^#{1,3} /m.test(doc.body);
    const hasBold = /\*\*.+\*\*/.test(doc.body);
    expect(hasHeading || hasBold).toBe(true);
  });
});
