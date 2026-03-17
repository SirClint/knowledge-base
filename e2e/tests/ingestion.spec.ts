import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8081/kms/api";

async function getToken(page: import("@playwright/test").Page): Promise<string> {
  return await page.evaluate(() => localStorage.getItem("token") ?? "");
}

test.describe("AI Ingestion", () => {
  test.beforeEach(async ({ page }) => {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await registerAndLogin(page, { role: "admin" });
    await page.click("text=+ New Doc");
    await page.waitForURL("**/kms/doc/new");
  });

  test("shows AI Ingestion and Manual tabs", async ({ page }) => {
    await expect(page.locator("button:has-text('AI Ingestion')")).toBeVisible();
    await expect(page.locator("button:has-text('Manual')")).toBeVisible();
  });

  test("AI tab is default and shows textarea", async ({ page }) => {
    await expect(page.locator("textarea")).toBeVisible();
    await expect(page.locator("button:has-text('Process with AI')")).toBeVisible();
  });

  test("switching to Manual tab shows title and folder inputs", async ({ page }) => {
    await page.click("button:has-text('Manual')");
    await expect(page.locator('input[placeholder="Document title"]')).toBeVisible();
    await expect(page.locator("select")).toBeVisible();
    await expect(page.locator("button:has-text('Create Document')")).toBeVisible();
    await expect(page.locator("textarea")).not.toBeVisible();
  });

  test("switching back to AI tab restores textarea", async ({ page }) => {
    await page.click("button:has-text('Manual')");
    await page.click("button:has-text('AI Ingestion')");
    await expect(page.locator("textarea")).toBeVisible();
    await expect(page.locator("button:has-text('Process with AI')")).toBeVisible();
    await expect(page.locator('input[placeholder="Document title"]')).not.toBeVisible();
  });

  test("Process with AI button disabled when textarea is empty", async ({ page }) => {
    await expect(page.locator("button:has-text('Process with AI')")).toBeDisabled();
    await page.fill("textarea", "some content");
    await expect(page.locator("button:has-text('Process with AI')")).toBeEnabled();
    await page.fill("textarea", "");
    await expect(page.locator("button:has-text('Process with AI')")).toBeDisabled();
  });

  test("spinner overlay appears while AI is processing", async ({ page }) => {
    const docPath = `personal/spinner-test-${Date.now()}.md`;

    // Intercept with a delay so we can catch the spinner
    await page.route("**/kms/api/ingest", async route => {
      await new Promise(r => setTimeout(r, 2500));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ action: "create", path: docPath, needs_review: false, message: "Created." }),
      });
    });
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ title: "Spinner Test", body: "Content", path: docPath }),
      });
    });

    await page.fill("textarea", "Test content for spinner");
    await page.click("button:has-text('Process with AI')");

    await expect(page.locator("text=AI is processing...")).toBeVisible();
    await expect(page.locator("text=This may take 10–30 seconds")).toBeVisible();
    await expect(page.locator("button:has-text('Processing...')")).toBeVisible();
  });

  test("shows detailed error message when AI returns 500", async ({ page }) => {
    await page.route("**/kms/api/ingest", async route => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "AI processing failed: AI returned invalid JSON" }),
      });
    });

    await page.fill("textarea", "Some content that will fail");
    await page.click("button:has-text('Process with AI')");

    await expect(page.locator("text=/server encountered an error/")).toBeVisible({ timeout: 10000 });
    await expect(page).toHaveURL(/\/kms\/doc\/new/);
    await expect(page.locator("textarea")).toBeEnabled();
    await expect(page.locator("button:has-text('Process with AI')")).toBeVisible();
  });

  test("AI ingestion creates doc and navigates to it", async ({ page }) => {
    const docPath = `personal/ingest-nav-${Date.now()}.md`;

    await page.route("**/kms/api/ingest", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ action: "create", path: docPath, needs_review: false, message: "Created." }),
      });
    });
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ title: "Ingested Doc", body: "## Heading\n\nLine one\nLine two", path: docPath }),
      });
    });

    await page.fill("textarea", "## Heading\n\nLine one\nLine two");
    await page.click("button:has-text('Process with AI')");
    await page.waitForURL(/\/kms\/doc\//, { timeout: 15000 });

    await expect(page.locator("text=Ingested Doc")).toBeVisible();
    await expect(page.locator("text=Line two")).toBeVisible();
  });

  test("manual create: Create Document button disabled until both title and folder set", async ({ page }) => {
    await page.click("button:has-text('Manual')");

    await expect(page.locator("button:has-text('Create Document')")).toBeDisabled();

    await page.fill('input[placeholder="Document title"]', "Some Title");
    await expect(page.locator("button:has-text('Create Document')")).toBeDisabled();

    await page.locator("select").selectOption({ index: 1 });
    await expect(page.locator("button:has-text('Create Document')")).toBeEnabled();
  });

  test("manual create: creates doc, navigates to it, and it is editable", async ({ page }) => {
    const title = `Manual Doc ${Date.now()}`;

    await page.click("button:has-text('Manual')");
    await page.fill('input[placeholder="Document title"]', title);
    await page.locator("select").selectOption({ index: 1 });
    await page.click("button:has-text('Create Document')");

    await page.waitForURL(/\/kms\/doc\//);
    await expect(page.locator(`text=${title}`)).toBeVisible({ timeout: 10000 });
    await expect(page.locator("button:has-text('Edit')")).toBeVisible();
  });

  test("AI offline warning shown when AI is unavailable", async ({ page }) => {
    // Mock health endpoint to return offline
    await page.route("**/kms/api/health/ai", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ai: "offline" }),
      });
    });

    await page.reload();
    await page.waitForURL("**/kms/doc/new");

    await expect(page.locator("text=AI is currently offline")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("button:has-text('Process with AI')")).toBeDisabled();
  });
});

test.describe("AI Ingestion Banner", () => {
  test.beforeEach(async ({ page }) => {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await registerAndLogin(page, { role: "admin" });
    await page.click("text=+ New Doc");
    await page.waitForURL("**/kms/doc/new");
  });

  test("banner appears immediately after ingest without page reload", async ({ page }) => {
    const docPath = `personal/banner-immediate-${Date.now()}.md`;
    const reason = "Created new personal note about the topic.";

    await page.route("**/kms/api/ingest", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ action: "create", path: docPath, needs_review: false, reason, message: "Created." }),
      });
    });
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ title: "Banner Test Doc", body: "Body content.", path: docPath }),
      });
    });

    await page.fill("textarea", "Some content to ingest");
    await page.click("button:has-text('Process with AI')");

    // Must appear on the navigated-to doc page WITHOUT any reload
    await page.waitForURL(/\/kms\/doc\//, { timeout: 15000 });
    await expect(page.locator(`text=${reason}`)).toBeVisible({ timeout: 5000 });
  });

  test("banner shows exact reason returned by the API", async ({ page }) => {
    const docPath = `personal/banner-reason-${Date.now()}.md`;
    const reason = "Updated existing document: merged new details into prior content.";

    await page.route("**/kms/api/ingest", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ action: "update", path: docPath, needs_review: false, reason, message: "Updated." }),
      });
    });
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ title: "Existing Doc", body: "Merged body.", path: docPath }),
      });
    });

    await page.fill("textarea", "New information about existing topic");
    await page.click("button:has-text('Process with AI')");
    await page.waitForURL(/\/kms\/doc\//, { timeout: 15000 });

    await expect(page.locator(`text=${reason}`)).toBeVisible();
  });

  test("banner can be dismissed with X button", async ({ page }) => {
    const docPath = `personal/banner-dismiss-${Date.now()}.md`;
    const reason = "Created a new document.";

    await page.route("**/kms/api/ingest", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ action: "create", path: docPath, needs_review: false, reason, message: "Created." }),
      });
    });
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ title: "Dismiss Test", body: "Content.", path: docPath }),
      });
    });

    await page.fill("textarea", "Content to dismiss");
    await page.click("button:has-text('Process with AI')");
    await page.waitForURL(/\/kms\/doc\//, { timeout: 15000 });
    await expect(page.locator(`text=${reason}`)).toBeVisible();

    // Find and click the dismiss button (×)
    await page.locator("button", { hasText: "×" }).click();
    await expect(page.locator(`text=${reason}`)).not.toBeVisible();
  });

  test("banner does not appear when navigating to a doc directly", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await page.evaluate(() => localStorage.getItem("token") ?? "");
    const docPath = `personal/no-banner-${Date.now()}.md`;

    await page.request.post(`${BASE_API}/docs`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { title: "No Banner Doc", path: docPath, body: "body", tags: [] },
    });

    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("text=No Banner Doc")).toBeVisible();
    // No banner should be present at all
    await expect(page.locator("[style*='background: #eff6ff'], [style*='background:#eff6ff']")).not.toBeVisible();
  });

  test("banner shows for update action as well as create", async ({ page }) => {
    const docPath = `personal/banner-update-${Date.now()}.md`;
    const reason = "Found matching topic; updated existing document.";

    await page.route("**/kms/api/ingest", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ action: "update", path: docPath, needs_review: true, reason, message: "Updated." }),
      });
    });
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ title: "Updated Doc", body: "Updated body.", path: docPath }),
      });
    });

    await page.fill("textarea", "Update info for existing topic");
    await page.click("button:has-text('Process with AI')");
    await page.waitForURL(/\/kms\/doc\//, { timeout: 15000 });
    await expect(page.locator(`text=${reason}`)).toBeVisible();
  });

  test("banner does not persist after navigating to a different doc", async ({ page }) => {
    const docPath = `personal/banner-nav-${Date.now()}.md`;
    const reason = "Created fresh document.";
    const otherPath = `personal/other-doc-${Date.now()}.md`;

    // Create the other doc for real via API
    const token = await page.evaluate(() => localStorage.getItem("token") ?? "");
    await page.request.post(`${BASE_API}/docs`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { title: "Other Doc", path: otherPath, body: "other body", tags: [] },
    });

    await page.route("**/kms/api/ingest", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ action: "create", path: docPath, needs_review: false, reason, message: "Created." }),
      });
    });
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ title: "Ingest Doc", body: "Ingest body.", path: docPath }),
      });
    });

    await page.fill("textarea", "Content for banner persistence check");
    await page.click("button:has-text('Process with AI')");
    await page.waitForURL(/\/kms\/doc\//, { timeout: 15000 });
    await expect(page.locator(`text=${reason}`)).toBeVisible();

    // Navigate to a completely different doc
    await page.goto(`./doc/${otherPath}`);
    await expect(page.locator("text=Other Doc")).toBeVisible();
    // Banner reason from previous ingest should NOT carry over
    await expect(page.locator(`text=${reason}`)).not.toBeVisible();
  });
});
