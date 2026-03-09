import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8080/kms/api";

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
});
