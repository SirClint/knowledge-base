import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("Smoke", () => {
  test("AI status shows online", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    // The NavBar polls /health/ai on mount — wait for it to resolve from "checking"
    await expect(
      page.locator("span", { hasText: /AI: (online|offline)/ })
    ).toBeVisible({ timeout: 10000 });

    const statusText = await page.locator("span", { hasText: /AI: (online|offline)/ }).textContent();
    if (statusText?.includes("offline")) {
      throw new Error(
        "AI is offline. Ollama may not be reachable from Docker containers.\n" +
        "Check: sudo ufw allow in on <docker-bridge-interface> to any port 11434\n" +
        "And: Ollama must be started with OLLAMA_HOST=0.0.0.0"
      );
    }
    expect(statusText).toContain("AI: online");
  });
});
