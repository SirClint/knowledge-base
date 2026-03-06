import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("Documents", () => {
  const docTitle = `Test Doc ${Date.now()}`;

  test.beforeEach(async ({ page }) => {
    await registerAndLogin(page, { role: "admin" });
  });

  test("create a new document", async ({ page }) => {
    await page.click("text=+ New Doc");
    await page.waitForURL("**/kms/doc/new");

    // Fill in title
    await page.fill('input[placeholder="Title"]', docTitle);

    // Select category
    await page.selectOption("select", "personal");

    // Type in the editor (CodeMirror)
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.type("This is a test document body.");

    // Save (may take a few seconds if Ollama timeout occurs)
    await page.click("text=Save");

    // Wait for navigation away from /doc/new (allow time for API + Ollama timeout)
    await page.waitForURL(/\/doc\/personal\//, { timeout: 15_000 });

    // Should show the doc content
    await expect(page.locator("text=This is a test document body")).toBeVisible();
  });

  test("search for a document by keyword", async ({ page }) => {
    // First create a doc
    const title = `Searchable ${Date.now()}`;
    await page.request.post("http://localhost:8080/kms/api/docs", {
      headers: { Authorization: `Bearer ${await getToken(page)}` },
      data: { title, path: `personal/${title.toLowerCase().replace(/\s+/g, "-")}.md`, body: "Unique searchable content here", tags: [] },
    });

    // Search from home page
    await page.goto("./");
    await page.fill('input[placeholder="Search docs..."]', title);
    await page.click('button:text("Search")');

    // Should find the doc
    await expect(page.locator(`text=${title}`)).toBeVisible();
  });

  test("click search result and view doc content", async ({ page }) => {
    // Create a doc with known content
    const title = `Viewable ${Date.now()}`;
    const body = "This content should be fully visible on the doc page.";
    const path = `personal/${title.toLowerCase().replace(/\s+/g, "-")}.md`;

    await page.request.post("http://localhost:8080/kms/api/docs", {
      headers: { Authorization: `Bearer ${await getToken(page)}` },
      data: { title, path, body, tags: [] },
    });

    // Search and click
    await page.goto("./");
    await page.fill('input[placeholder="Search docs..."]', title);
    await page.click('button:text("Search")');
    await page.click(`text=${title}`);

    // Should show full doc content
    await expect(page.locator(`text=${body}`)).toBeVisible();
  });

  test("click folder to browse documents", async ({ page }) => {
    // Create a doc in team/processes
    const title = `Process Doc ${Date.now()}`;
    const path = `team/processes/${title.toLowerCase().replace(/\s+/g, "-")}.md`;
    await page.request.post("http://localhost:8080/kms/api/docs", {
      headers: { Authorization: `Bearer ${await getToken(page)}` },
      data: { title, path, body: "Process content", tags: [] },
    });

    // Create a doc in personal (to confirm it's NOT shown)
    const otherTitle = `Personal Note ${Date.now()}`;
    await page.request.post("http://localhost:8080/kms/api/docs", {
      headers: { Authorization: `Bearer ${await getToken(page)}` },
      data: {
        title: otherTitle,
        path: `personal/${otherTitle.toLowerCase().replace(/\s+/g, "-")}.md`,
        body: "Personal content",
        tags: [],
      },
    });

    await page.goto("./");

    // Expand team folder by clicking the expand arrow
    await page.locator("text=▶").first().click({ timeout: 5000 });

    // Click processes subfolder
    await page.click("text=processes");

    // The team/processes doc should appear
    await expect(page.locator(`text=${title}`)).toBeVisible();

    // The personal doc should NOT appear
    await expect(page.locator(`text=${otherTitle}`)).not.toBeVisible();
  });

  test("edit an existing document", async ({ page }) => {
    // Create a doc
    const title = `Editable ${Date.now()}`;
    const path = `personal/${title.toLowerCase().replace(/\s+/g, "-")}.md`;

    await page.request.post("http://localhost:8080/kms/api/docs", {
      headers: { Authorization: `Bearer ${await getToken(page)}` },
      data: { title, path, body: "Original content", tags: [] },
    });

    // Navigate to it
    await page.goto(`./doc/${path}`);
    await expect(page.locator(`text=Original content`)).toBeVisible();

    // Click edit
    await page.click("text=Edit");

    // Modify content in editor
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("Control+a");
    await page.keyboard.type("Updated content");

    // Save
    await page.click("text=Save");

    // Should show updated content
    await expect(page.locator("text=Updated content")).toBeVisible();
  });
});

/** Extract the JWT token from localStorage */
async function getToken(page: import("@playwright/test").Page): Promise<string> {
  return await page.evaluate(() => localStorage.getItem("token") ?? "");
}
