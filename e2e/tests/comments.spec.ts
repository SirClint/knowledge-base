import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8080/kms/api";

/** Extract the JWT token from localStorage */
async function getToken(page: import("@playwright/test").Page): Promise<string> {
  return await page.evaluate(() => localStorage.getItem("token") ?? "");
}

test.describe("Comments", () => {
  test("Comments section visible in view mode", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const token = await getToken(page);
    const docPath = `personal/comment-e2e-${Date.now()}.md`;
    const res = await page.request.post(`${BASE_API}/docs`, {
      data: { title: "Comment E2E Doc", path: docPath, body: "body", tags: [] },
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok()) throw new Error(`Create failed: ${res.status()}`);

    await page.goto(`./doc/${docPath}`);
    await expect(page.locator("text=Comments")).toBeVisible();
    await expect(page.locator('textarea[placeholder="Add a comment..."]')).toBeVisible();
  });

  test("Can add a comment and it appears in the list", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const token = await getToken(page);
    const docPath = `personal/comment-add-${Date.now()}.md`;
    const res = await page.request.post(`${BASE_API}/docs`, {
      data: { title: "Comment Add Doc", path: docPath, body: "body", tags: [] },
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok()) throw new Error(`Create failed: ${res.status()}`);

    await page.goto(`./doc/${docPath}`);
    await page.fill('textarea[placeholder="Add a comment..."]', "This is my test comment");
    await page.click("text=Add Comment");
    await expect(page.locator("text=This is my test comment")).toBeVisible();
  });

  test("Comment author can delete their own comment", async ({ page }) => {
    await registerAndLogin(page, { role: "editor" });

    const token = await getToken(page);
    const docPath = `personal/comment-del-${Date.now()}.md`;
    const res = await page.request.post(`${BASE_API}/docs`, {
      data: { title: "Comment Del Doc", path: docPath, body: "body", tags: [] },
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok()) throw new Error(`Create failed: ${res.status()}`);

    await page.goto(`./doc/${docPath}`);
    await page.fill('textarea[placeholder="Add a comment..."]', "delete this comment");
    await page.click("text=Add Comment");
    await expect(page.locator("text=delete this comment")).toBeVisible();

    // Delete the comment
    await page.locator("button:has-text('Delete')").last().click();
    await expect(page.locator("text=delete this comment")).not.toBeVisible();
  });
});
