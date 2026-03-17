import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8081/kms/api";

async function getToken(page: import("@playwright/test").Page): Promise<string> {
  return await page.evaluate(() => localStorage.getItem("token") ?? "");
}

async function createDoc(
  page: import("@playwright/test").Page,
  token: string,
  opts: { title: string; path: string; body?: string }
) {
  const res = await page.request.post(`${BASE_API}/docs`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title: opts.title, path: opts.path, body: opts.body ?? "", tags: [] },
  });
  if (!res.ok()) throw new Error(`Create doc failed: ${res.status()}`);
}

test.describe("Document Lifecycle", () => {
  test("create via AI (mocked) → view content → navigate back to home", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const docPath = `personal/lifecycle-ai-${Date.now()}.md`;

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
        body: JSON.stringify({ title: "AI Lifecycle Doc", body: "Full content here\nLine two\nLine three", path: docPath }),
      });
    });

    await page.click("text=+ New Doc");
    await page.fill("textarea", "Full content here\nLine two\nLine three");
    await page.click("button:has-text('Process with AI')");
    await page.waitForURL(/\/kms\/doc\//, { timeout: 15000 });

    await expect(page.locator("text=AI Lifecycle Doc")).toBeVisible();
    await expect(page.locator("text=Line three")).toBeVisible();

    await page.click("button:has-text('← Back')");
    await page.waitForURL("**/kms");
    await expect(page.locator("text=+ New Doc")).toBeVisible();
  });

  test("create via manual → view → edit → save → verify content", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const title = `Lifecycle Manual ${Date.now()}`;

    await page.click("text=+ New Doc");
    await page.click("button:has-text('Manual')");
    await page.fill('input[placeholder="Document title"]', title);
    await page.locator("select").selectOption({ index: 1 });
    await page.click("button:has-text('Create Document')");
    await page.waitForURL(/\/kms\/doc\//);

    await expect(page.locator(`text=${title}`)).toBeVisible();
    await page.click("button:has-text('Edit')");

    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("Manually typed content");
    await page.click("button:has-text('Save')");

    await expect(page.locator("text=Manually typed content")).toBeVisible();
    await expect(page.locator("button:has-text('Edit')")).toBeVisible();
  });

  test("create → delete → redirected to home → doc is gone", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/delete-test-${Date.now()}.md`;

    await createDoc(page, token, { title: "Delete Me", path: docPath, body: "bye bye" });
    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("text=bye bye")).toBeVisible();

    page.once("dialog", d => d.accept());
    await page.click("button:has-text('Delete')");
    await page.waitForURL("**/kms");
    await expect(page.locator("text=+ New Doc")).toBeVisible();

    // Doc should return 404 now
    const res = await page.request.get(`${BASE_API}/docs/${docPath}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status()).toBe(404);
  });

  test("delete → recreate same path → new content visible", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/recreate-${Date.now()}.md`;

    await createDoc(page, token, { title: "First Version", path: docPath, body: "First content" });
    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("text=First content")).toBeVisible();

    page.once("dialog", d => d.accept());
    await page.click("button:has-text('Delete')");
    await page.waitForURL("**/kms");

    await createDoc(page, token, { title: "Second Version", path: docPath, body: "Second content" });
    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("text=Second content")).toBeVisible();
    await expect(page.locator("text=First content")).not.toBeVisible();
  });

  test("create via AI → delete → create again via manual (full cycle)", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/full-cycle-${Date.now()}.md`;

    // Step 1: Create via mocked AI
    await page.route("**/kms/api/ingest", async route => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ action: "create", path: docPath, needs_review: false, message: "Created." }),
      });
    });
    await page.route(`**/kms/api/docs/${docPath}`, async route => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ title: "AI Version", body: "AI content", path: docPath }),
        });
      } else {
        await route.continue();
      }
    });

    await page.click("text=+ New Doc");
    await page.fill("textarea", "AI content");
    await page.click("button:has-text('Process with AI')");
    await page.waitForURL(/\/kms\/doc\//, { timeout: 15000 });
    await page.unrouteAll();

    // Step 2: Create the doc for real so we can delete it
    await createDoc(page, token, { title: "AI Version", path: docPath, body: "AI content" });
    await page.goto(`./doc/${docPath}`);

    page.once("dialog", d => d.accept());
    await page.click("button:has-text('Delete')");
    await page.waitForURL("**/kms");

    // Step 3: Recreate via manual tab
    const newTitle = `Recreated Manual ${Date.now()}`;
    await page.click("text=+ New Doc");
    await page.click("button:has-text('Manual')");
    await page.fill('input[placeholder="Document title"]', newTitle);
    await page.locator("select").selectOption({ index: 1 });
    await page.click("button:has-text('Create Document')");
    await page.waitForURL(/\/kms\/doc\//);
    await expect(page.locator(`text=${newTitle}`)).toBeVisible();
  });

  test("cancel delete keeps doc intact", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/cancel-del-${Date.now()}.md`;

    await createDoc(page, token, { title: "Keep Me", path: docPath, body: "stays alive" });
    await page.goto(`./doc/${docPath}`);

    page.once("dialog", d => d.dismiss());
    await page.click("button:has-text('Delete')");

    await expect(page).toHaveURL(new RegExp(docPath.replace("/", "\\/")));
    await expect(page.locator("text=stays alive")).toBeVisible();
  });

  test("Delete button only visible for admin", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/role-delete-${Date.now()}.md`;

    await createDoc(page, token, { title: "Role Delete Test", path: docPath, body: "body" });

    // Admin sees delete
    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("button:has-text('Delete')")).toBeVisible();

    // Reader does not see delete
    await registerAndLogin(page, { role: "reader" });
    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("button:has-text('Delete')")).not.toBeVisible();
  });

  test("Edit button not visible for reader", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/reader-edit-${Date.now()}.md`;

    await createDoc(page, token, { title: "Reader Edit Test", path: docPath, body: "body" });

    await registerAndLogin(page, { role: "reader" });
    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("button:has-text('Edit')")).not.toBeVisible();
  });

  test("editor can edit but cannot delete", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/editor-perms-${Date.now()}.md`;

    await createDoc(page, token, { title: "Editor Perms Test", path: docPath, body: "original" });
    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("text=Editor Perms Test")).toBeVisible({ timeout: 10000 });

    // Simulate editor view by changing the stored role (token is still valid for API calls)
    await page.evaluate(() => localStorage.setItem("role", "editor"));
    await page.reload();
    await expect(page.locator("text=Editor Perms Test")).toBeVisible({ timeout: 10000 });

    await expect(page.locator("button:has-text('Edit')")).toBeVisible();
    await expect(page.locator("button:has-text('Delete')")).not.toBeVisible();
  });

  test("edit and cancel reverts to original content", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/cancel-edit-${Date.now()}.md`;

    await createDoc(page, token, { title: "Cancel Edit", path: docPath, body: "original content" });
    await page.evaluate(url => { window.location.href = url; }, `http://localhost:8081/kms/doc/${docPath}`);
    await expect(page.locator("text=original content")).toBeVisible({ timeout: 10000 });

    await page.click("button:has-text('Edit')");
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("discarded content");

    await page.click("button:has-text('Cancel')");

    // Should show original content again
    await expect(page.locator("text=original content")).toBeVisible();
    await expect(page.locator("text=discarded content")).not.toBeVisible();
  });

  test("Back button from new doc page goes to home", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    await page.click("text=+ New Doc");
    await page.waitForURL("**/kms/doc/new");
    await page.click("button:has-text('← Back')");
    await page.waitForURL("**/kms");
    await expect(page.locator("text=+ New Doc")).toBeVisible();
  });
});

  test("editor wraps long lines — no horizontal scrollbar", async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
    const token = await getToken(page);
    const docPath = `personal/wrap-test-${Date.now()}.md`;
    const longLine = "A ".repeat(200).trim(); // 400-char single line

    await createDoc(page, token, { title: "Wrap Test", path: docPath, body: longLine });
    await page.goto(`./doc/${docPath}`);
    await page.click("button:has-text('Edit')");

    const editor = page.locator(".cm-editor");
    await expect(editor).toBeVisible();

    // If line-wrapping is enabled the scroll width should not exceed the visible width
    const { scrollWidth, clientWidth } = await editor.evaluate(el => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 5); // 5px tolerance
  });
