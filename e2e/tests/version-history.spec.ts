import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8081/kms/api";

/** Extract the JWT token from localStorage */
async function getToken(page: import("@playwright/test").Page): Promise<string> {
  return await page.evaluate(() => localStorage.getItem("token") ?? "");
}

test.describe("Version History", () => {
  test("History button visible in view mode", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const token = await getToken(page);
    const docPath = `personal/ver-e2e-${Date.now()}.md`;
    const res = await page.request.post(`${BASE_API}/docs`, {
      data: { title: "Ver E2E Doc", path: docPath, body: "original body", tags: [] },
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok()) throw new Error(`Create failed: ${res.status()}`);

    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("button", { hasText: "History" })).toBeVisible();
  });

  test("History panel shows version after edit and save", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const token = await getToken(page);
    const docPath = `personal/ver-e2e-save-${Date.now()}.md`;
    const res = await page.request.post(`${BASE_API}/docs`, {
      data: { title: "Ver Save Doc", path: docPath, body: "v1 content", tags: [] },
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok()) throw new Error(`Create failed: ${res.status()}`);

    await page.goto(`./doc/${docPath}`);
    await page.click("button:has-text('Edit')");

    // Edit content in CodeMirror
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("v2 content");
    await page.click("button:has-text('Save')");

    // Open history and verify a version entry appeared
    await page.click("button:has-text('History')");
    await expect(page.locator("text=Version History")).toBeVisible();
    // A version row should contain "by" (author attribution)
    await expect(page.locator("text=by")).toBeVisible({ timeout: 5000 });
  });

  test("History panel can be closed", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const token = await getToken(page);
    const docPath = `personal/ver-close-${Date.now()}.md`;
    await page.request.post(`${BASE_API}/docs`, {
      data: { title: "Ver Close Doc", path: docPath, body: "body", tags: [] },
      headers: { Authorization: `Bearer ${token}` },
    });

    await page.goto(`./doc/${docPath}`);
    await page.click("button:has-text('History')");
    await expect(page.locator("text=Version History")).toBeVisible();

    await page.click("button:has-text('Close')");
    await expect(page.locator("text=Version History")).not.toBeVisible();
  });

  test("can restore a previous version", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const token = await getToken(page);
    const docPath = `personal/ver-restore-${Date.now()}.md`;
    await page.request.post(`${BASE_API}/docs`, {
      data: { title: "Restore Test", path: docPath, body: "v1 content", tags: [] },
      headers: { Authorization: `Bearer ${token}` },
    });

    // Edit to v2 to create a version snapshot
    await page.goto(`./doc/${docPath}`);
    await page.click("button:has-text('Edit')");
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("v2 content");
    await page.click("button:has-text('Save')");
    await expect(page.locator("text=v2 content")).toBeVisible();

    // Open history and restore v1
    await page.click("button:has-text('History')");
    await expect(page.locator("button:has-text('Restore')")).toBeVisible({ timeout: 5000 });

    page.on("dialog", d => d.accept());
    await page.locator("button:has-text('Restore')").first().click();

    // Content should be restored to v1
    await expect(page.locator("text=v1 content")).toBeVisible({ timeout: 10000 });
    await expect(page.locator("text=v2 content")).not.toBeVisible();
  });

  test("no versions shown message when doc has never been saved", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const token = await getToken(page);
    const docPath = `personal/ver-empty-${Date.now()}.md`;
    await page.request.post(`${BASE_API}/docs`, {
      data: { title: "No Versions Doc", path: docPath, body: "body", tags: [] },
      headers: { Authorization: `Bearer ${token}` },
    });

    await page.goto(`./doc/${docPath}`);
    await page.click("button:has-text('History')");
    await expect(page.locator("text=No saved versions yet")).toBeVisible({ timeout: 5000 });
  });
});
