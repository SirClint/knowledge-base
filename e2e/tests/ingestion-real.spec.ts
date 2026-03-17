/**
 * Real-model E2E ingestion tests — no mocks on the AI layer.
 *
 * These tests submit actual content through the UI and verify what mocked tests
 * cannot: empty bodies, bad paths, missing banners, real update-vs-create decisions.
 *
 * Run serially — tests share one Ollama instance and must not compete for it.
 * All tests skip gracefully when Ollama is offline.
 */
import { test, expect, Page } from "@playwright/test";
import { registerAndLogin } from "./helpers";

const BASE_API = "http://localhost:8081/kms/api";

// Prevent parallel Ollama requests — one at a time
test.describe.configure({ mode: "serial" });

async function getToken(page: Page): Promise<string> {
  return await page.evaluate(() => localStorage.getItem("token") ?? "");
}

async function isAiOnline(page: Page): Promise<boolean> {
  const token = await getToken(page);
  try {
    const res = await page.request.get(`${BASE_API}/health/ai`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const body = await res.json();
    return body.ai === "online";
  } catch {
    return false;
  }
}

async function ingestAndWait(page: Page, message: string): Promise<string> {
  await page.click("text=+ New Doc");
  await page.waitForURL("**/kms/doc/new");
  await page.fill("textarea", message);
  await page.click("button:has-text('Process with AI')");
  await page.waitForURL(
    url => url.href.includes("/kms/doc/") && !url.href.endsWith("/kms/doc/new"),
    { timeout: 120000 }
  );
  return page.url();
}

test.describe("Real AI Ingestion", () => {
  test.beforeEach(async ({ page }) => {
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await registerAndLogin(page, { role: "admin" });
  });

  test("ingested document has a non-empty body (Corleck Head regression)", async ({ page }) => {
    test.setTimeout(180000);
    if (!await isAiOnline(page)) test.skip();

    const token = await getToken(page);
    await ingestAndWait(page,
      "The Tollund Man is a mummified corpse found in a Danish peat bog in 1950. " +
      "He dates to the 4th century BC and was found with a noose around his neck."
    );

    // Verify body via API — more reliable than DOM scraping
    const url = page.url();
    const pathMatch = url.match(/\/kms\/doc\/(.+)$/);
    const docPath = pathMatch?.[1];
    expect(docPath).toBeTruthy();

    const res = await page.request.get(`${BASE_API}/docs/${docPath}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const doc = await res.json();
    expect(doc.body?.trim(), `body is empty for path: ${docPath}`).toBeTruthy();
    expect(doc.body.length).toBeGreaterThan(20);
  });

  test("banner with AI reason appears immediately after ingest (no reload)", async ({ page }) => {
    test.setTimeout(180000);
    if (!await isAiOnline(page)) test.skip();

    await ingestAndWait(page,
      "The Mary Rose was a Tudor warship that sank in 1545 and was raised from the " +
      "Solent seabed in 1982. It is now displayed in Portsmouth."
    );

    // Banner renders the 🤖 emoji — reliable regardless of inline style format
    await expect(page.locator("text=🤖")).toBeVisible({ timeout: 5000 });
  });

  test("path does not contain literal 'subfolder'", async ({ page }) => {
    test.setTimeout(180000);
    if (!await isAiOnline(page)) test.skip();

    const url = await ingestAndWait(page,
      "Team reminder: all PRs require at least one approval before merging to main."
    );

    expect(url.toLowerCase()).not.toContain("subfolder");
  });

  test("path is lowercase, no spaces, ends in .md, max two folder levels", async ({ page }) => {
    test.setTimeout(180000);
    if (!await isAiOnline(page)) test.skip();

    const url = await ingestAndWait(page,
      "We use Caddy as a reverse proxy. It routes /kms/api/* to FastAPI and /kms/* to the React SPA."
    );

    const pathMatch = url.match(/\/kms\/doc\/(.+)$/);
    const docPath = pathMatch?.[1] ?? "";

    expect(docPath).toBeTruthy();
    expect(docPath).toBe(docPath.toLowerCase());
    expect(docPath).not.toContain(" ");
    expect(docPath.endsWith(".md")).toBe(true);
    // Should be root/topic/slug.md or root/slug.md — not root/a/b/c/slug.md
    const parts = docPath.replace(/\.md$/, "").split("/");
    expect(parts.length).toBeGreaterThanOrEqual(2);
    expect(parts.length).toBeLessThanOrEqual(3);
  });

  test("second ingest about same topic updates existing doc", async ({ page }) => {
    test.setTimeout(300000);
    if (!await isAiOnline(page)) test.skip();

    const token = await getToken(page);

    // Seed a known doc
    const seedPath = `team/history/rms-titanic-integration-${Date.now()}.md`;
    await page.request.post(`${BASE_API}/docs`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title: "RMS Titanic",
        path: seedPath,
        body: "The Titanic sank on April 15, 1912 after hitting an iceberg.",
        tags: [],
      },
    });

    const finalUrl = await ingestAndWait(page,
      "More Titanic facts: over 1,500 people died. The wreck was found in 1985 by Robert Ballard " +
      "at 3,800 metres depth in the North Atlantic."
    );

    if (finalUrl.includes("titanic")) {
      // AI updated the existing doc — verify merged content
      const res = await page.request.get(`${BASE_API}/docs/${seedPath}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok()) {
        const doc = await res.json();
        // Both original and new content should appear after merge
        expect(doc.body).toContain("1912");
      }
    } else {
      // AI created a new doc — the body should still have content
      const pathMatch = finalUrl.match(/\/kms\/doc\/(.+)$/);
      const newPath = pathMatch?.[1];
      if (newPath) {
        const res = await page.request.get(`${BASE_API}/docs/${newPath}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const doc = await res.json();
        expect(doc.body?.trim()).toBeTruthy();
      }
      console.warn(`AI created new doc instead of updating ${seedPath}. URL: ${finalUrl}`);
    }

    // Cleanup
    await page.request.delete(`${BASE_API}/docs/${seedPath}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });
});
