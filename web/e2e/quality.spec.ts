import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { ids } from "./fixture";

const pages = () => {
  const { alex, spring, jordan, sam } = ids();
  return [
    "/",
    "/?q=tester",
    "/tournaments",
    `/tournaments/${spring}`,
    `/players/${alex}`,
    `/players/${alex}/vs/${jordan}`, // a comparison (no meetings: the empty state)
    `/players/${alex}/vs?q=sam`,
    `/compare?a=${alex}&b=${sam}&discipline=MS`, // a matchup: results only, no number
    "/compare?qa=tester",
    "/coverage",
  ];
};

test("no serious or critical accessibility violations", async ({ page }) => {
  for (const path of pages()) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    const serious = violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious.map((v) => `${path}: ${v.id} – ${v.help}`)).toEqual([]);
  }
});

test("no horizontal scrolling at the current viewport", async ({ page }) => {
  for (const path of pages()) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    // mobile emulation widens innerWidth to fit overflowing content, hiding the very bug we test for
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        Math.min(window.innerWidth, window.screen.width),
    );
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});

test("keyboard: skip link, slash to search, enter to submit", async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, "keyboard shortcuts are a desktop affordance");
  await page.goto("/tournaments");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to content" }),
  ).toBeFocused();
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("/");
  const search = page.getByRole("combobox", {
    name: "Search players by name",
  });
  await expect(search).toBeFocused();
  await page.keyboard.type("sam exampel");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("link", { name: /Sam EXAMPLE/ }).first(),
  ).toBeVisible();
});
