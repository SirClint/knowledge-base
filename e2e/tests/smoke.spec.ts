import { test, expect } from "@playwright/test";
import { registerAndLogin } from "./helpers";

test.describe("Smoke", () => {
  test("AI status indicator resolves from checking state", async ({ page }) => {
    await registerAndLogin(page, { role: "reader" });
    // The NavBar polls /health/ai on mount — wait for it to resolve from "checking"
    await expect(
      page.locator("span", { hasText: /AI: (online|offline)/ })
    ).toBeVisible({ timeout: 10000 });

    const statusText = await page.locator("span", { hasText: /AI: (online|offline)/ }).textContent();
    if (statusText?.includes("offline")) {
      // Warn but don't fail — Ollama may not be configured in all environments
      console.warn(
        "\n⚠️  AI is offline. Ollama may not be reachable from Docker containers." +
        "\n   Fix: sudo ufw allow in on <docker-bridge-interface> to any port 11434" +
        "\n   Find interface: ip route | grep 172.18" +
        "\n   Ollama must also be started with OLLAMA_HOST=0.0.0.0\n"
      );
      test.skip(); // mark as skipped, not failed
    } else {
      expect(statusText).toContain("AI: online");
    }
  });
});
