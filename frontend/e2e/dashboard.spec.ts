import { test, expect } from "@playwright/test";

test("demo graph, simulation, analyst and reports are real API-backed flows", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "The internet beneath the surface." })).toBeVisible();
  await expect(page.getByText("EXPLORER DEMO", { exact: true })).toBeVisible();
  await expect(page.getByTestId("infrastructure-graph")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  if (testInfo.project.name === "desktop-chromium") {
    await page.screenshot({ path: "../docs/images/overview.png", fullPage: true });
  }
  await page.getByLabel("Provider to simulate").selectOption("cloudflare");
  await page.getByRole("button", { name: "Simulate outage exposure" }).click();
  await expect(page.getByText("potentially exposed assets", { exact: true })).toBeVisible();
  await expect(page.getByText("Observed concentration", { exact: true })).toBeVisible();
  if (testInfo.project.name === "desktop-chromium") {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: "../docs/images/blast-radius.png", fullPage: true });
  }
  await page.getByRole("button", { name: /Infrastructure analyst/ }).click();
  await page.getByLabel("YOUR QUESTION").fill("Which DNS provider is visible in the evidence?");
  await page.getByRole("button", { name: "Analyze evidence" }).click();
  await expect(page.getByText("EVIDENCE RETRIEVAL / NO LLM", { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  if (testInfo.project.name === "desktop-chromium") {
    await page.screenshot({ path: "../docs/images/analyst.png", fullPage: true });
  }
  if (testInfo.project.name === "mobile-chromium") {
    await page.screenshot({ path: "../docs/images/mobile.png", fullPage: true });
  }
  const file = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF", exact: true }).click();
  expect((await file).suggestedFilename()).toMatch(/shadow-.*\.pdf$/);
  expect(errors).toEqual([]);
});

test("requires authentication rather than simulating a live scan", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Domain to analyze").fill("github.com");
  await page.getByRole("button", { name: "Analyze domain" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Sign in with Clerk" })).toBeVisible();
});
