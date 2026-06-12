// @ts-check
// Live E2E screenshot driver: opens the DeltaForge dashboard, runs an SPY
// analysis through the UI (which streams from the real backend / Wolfram
// kernel), waits for the dashboard to populate, and captures full-page
// screenshots. Uses the frontend's installed Playwright devDependency.
import { chromium } from "playwright";

const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const OUT_FULL = process.env.E2E_OUT_FULL ?? "C:\\Users\\rohan\\deltaforge\\e2e_dashboard.png";
const OUT_TOP = process.env.E2E_OUT_TOP ?? "C:\\Users\\rohan\\deltaforge\\e2e_dashboard_top.png";

/** @param {number} ms */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  page.on("console", (m) => console.log("[browser:" + m.type() + "]", m.text()));
  page.on("pageerror", (e) => console.log("[pageerror]", e.message));

  console.log("Navigating to", BASE_URL);
  await page.goto(BASE_URL, { waitUntil: "networkidle", timeout: 60000 });

  // Landing view: fill ticker + run analysis.
  const input = page.locator('input[type="text"]').first();
  await input.waitFor({ state: "visible", timeout: 30000 });
  await input.fill("SPY");
  console.log("Filled SPY; clicking RUN ANALYSIS");
  await page.getByRole("button", { name: /RUN ANALYSIS|ANALYZING/i }).first().click();

  // Wait for the dashboard shell to mount (portfolio rail slot appears once a
  // stream has started).
  await page.locator('[data-slot="portfolio-rail"], main').first().waitFor({ timeout: 30000 });

  // Give the SSE stream time to flow through market_data → greeks → hedge →
  // summary. The backend + kernel + LLM summary can take a while.
  console.log("Waiting for stream to populate the dashboard...");
  for (let i = 0; i < 60; i++) {
    const hasHud = await page.locator("text=/Risk Summary|IV|Delta|Gamma/i").count();
    if (hasHud > 0 && i > 6) break;
    await sleep(2000);
  }
  // Settle a little more for late panels (summary/hedge).
  await sleep(8000);

  await page.screenshot({ path: OUT_TOP, fullPage: false });
  console.log("Saved top screenshot ->", OUT_TOP);
  await page.screenshot({ path: OUT_FULL, fullPage: true });
  console.log("Saved full-page screenshot ->", OUT_FULL);

  await browser.close();
  console.log("DONE");
}

main().catch((e) => {
  console.error("E2E_SCREENSHOT_FAILED:", e);
  process.exit(1);
});
