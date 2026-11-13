import { expect, test } from "@playwright/test";

import { RESTRICTED_NAMES, ids } from "./fixture";

// ADR-0010 end to end: the owner publishes junior and para events too, so the records ADR-0009
// used to hide are now reachable like any other. (The hiding path is covered by the backend
// tests that switch `PUBLISH_RESTRICTED_EVENTS` off.)

test("junior and para players can be found by search", async ({ page }) => {
  for (const name of RESTRICTED_NAMES) {
    await page.goto(`/?q=${encodeURIComponent(name)}`);
    await expect(
      page.getByRole("link", { name: new RegExp(name) }).first(),
    ).toBeVisible();
  }
});

test("junior and para records open like any other", async ({ page }) => {
  const { junior, para, juniorTournament } = ids();
  await page.goto(`/players/${junior}`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Junior PERSON" }),
  ).toBeVisible();
  await page.goto(`/players/${para}`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Para ATHLETE" }),
  ).toBeVisible();
  await page.goto(`/tournaments/${juniorTournament}`);
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Synthetic Junior Championships",
    }),
  ).toBeVisible();
});

test("a para match now counts in the opponent's history", async ({ page }) => {
  // Sam played Para ATHLETE in a para event: 4 adult matches plus that one
  await page.goto(`/players/${ids().sam}`);
  const items = page
    .getByRole("region", { name: "Matches, newest first" })
    .getByRole("listitem");
  await expect(items).toHaveCount(5);
});

test("coverage no longer claims anything is withheld", async ({ page }) => {
  await page.goto("/coverage");
  await expect(
    page.getByRole("heading", { level: 1, name: "Data coverage" }),
  ).toBeVisible();
  await expect(page.getByText("Deliberately not published")).toHaveCount(0);
  await expect(page.getByText(/not published here/)).toHaveCount(0);
});
