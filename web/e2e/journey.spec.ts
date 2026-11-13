import { expect, test } from "@playwright/test";

import { ids } from "./fixture";

test("discover → search → profile → match → tournament → another player", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Find a player" }),
  ).toBeVisible();

  // a typo: "Tester" spelled "Testr"
  const search = page.getByRole("searchbox", {
    name: "Search players by name",
  });
  await search.fill("Alex Testr");
  await search.press("Enter");
  await expect(page).toHaveURL(/\?q=Alex\+Testr/);
  const hit = page.getByRole("link", { name: /Alex TESTER/ }).first();
  await expect(hit).toBeVisible();
  await hit.click();

  await expect(page).toHaveURL(new RegExp(`/players/${ids().alex}$`));
  await expect(
    page.getByRole("heading", { level: 1, name: "Alex TESTER" }),
  ).toBeVisible();
  // decided matches only: the cancelled match is neither won nor lost
  await expect(page.locator('dt:text-is("Record") + dd')).toHaveText("4–2");

  const history = page.getByRole("list", { name: "Matches, newest first" });
  await expect(
    history.getByTitle("Cancelled or not played: no result"),
  ).toBeVisible(); // not a loss
  await expect(history.getByText("W ret.")).toBeVisible(); // retirement keeps its W, marked
  await expect(history.getByText("W/O")).toBeVisible(); // walkover, marked
  await expect(history.getByText("21–15 · 21–18")).toBeVisible(); // score from Alex's side

  await history
    .getByRole("link", { name: "Synthetic Spring Open 2026" })
    .first()
    .click();
  await expect(page).toHaveURL(new RegExp(`/tournaments/${ids().spring}`));
  await expect(
    page.getByRole("heading", { level: 1, name: "Synthetic Spring Open 2026" }),
  ).toBeVisible();
  await expect(page.getByText("Testville")).toBeVisible();

  await page.getByRole("link", { name: "XD Open" }).click();
  await expect(page).toHaveURL(/event=XD\+Open|event=XD%20Open/);
  await page.getByRole("link", { name: "Kim SAMPLE" }).first().click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Kim SAMPLE" }),
  ).toBeVisible();
});

test("a merged player's old URL redirects to the canonical profile", async ({
  page,
}) => {
  const { jordan, jordanMergedFrom } = ids();
  await page.goto(`/players/${jordanMergedFrom}`);
  await expect(page).toHaveURL(new RegExp(`/players/${jordan}$`));
  await expect(
    page.getByRole("heading", { level: 1, name: "Jordan DUPLICATE" }),
  ).toBeVisible();
  // both identities' matches now belong to one profile
  await expect(
    page
      .getByRole("list", { name: "Matches, newest first" })
      .getByRole("listitem"),
  ).toHaveCount(2);
});

test("filters narrow the match history and can be cleared", async ({
  page,
}) => {
  await page.goto(`/players/${ids().alex}`);
  await page.getByLabel("Result").selectOption("lost");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/result=lost/);
  const rows = page
    .getByRole("list", { name: "Matches, newest first" })
    .getByRole("listitem");
  await expect(rows).toHaveCount(2);
  for (const row of await rows.all())
    await expect(row.getByTitle(/^Lost/)).toBeVisible();
  await page.getByRole("link", { name: "Clear" }).click();
  await expect(rows).toHaveCount(7);
});

test("tournament explorer searches and filters", async ({ page }) => {
  await page.goto("/tournaments");
  await expect(
    page.getByRole("link", { name: "Synthetic Spring Open 2026" }),
  ).toBeVisible();
  const name = page
    .getByRole("search", { name: "Filter tournaments" })
    .getByRole("searchbox");
  await name.fill("autumn");
  await name.press("Enter");
  await expect(
    page.getByRole("link", { name: /^Synthetic Autumn Classic 2026/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Synthetic Spring Open 2026" }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/tournaments$/);
  await expect(name).toHaveValue(""); // cleared, not left holding the old text
  // only the spring tournament has a mixed doubles event
  await page.getByRole("combobox", { name: "Discipline" }).selectOption("XD");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/discipline=XD/);
  await expect(
    page.getByRole("link", { name: "Synthetic Spring Open 2026" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: /^Synthetic Autumn Classic 2026/ }),
  ).toHaveCount(0);
  // a value the API would reject is ignored, not turned into an error page
  await page.goto("/tournaments?discipline=ZZ&year=1&source=bnz");
  await expect(
    page.getByRole("link", { name: "Synthetic Spring Open 2026" }),
  ).toBeVisible();
});

test("empty search says what was searched", async ({ page }) => {
  await page.goto("/?q=Zzyzx+Nobody");
  await expect(page.getByText("No players match “Zzyzx Nobody”")).toBeVisible();
});

test("coverage explains sources and freshness", async ({ page }) => {
  await page.goto("/coverage");
  await expect(
    page.getByRole("heading", { level: 1, name: "Data coverage" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 3, name: "Australia" }),
  ).toBeVisible();
  // the fixture's data is synthetic, so no provider has imported anything: statuses say so
  await expect(page.getByText("Partially validated").first()).toBeVisible();
  await expect(
    page.getByText("Pending technical access").first(),
  ).toBeVisible();
  // the fixture has never been synced: freshness says so instead of inventing a time
  await expect(page.locator("#main").getByText("No sync has run yet")).toBeVisible();
  await expect(page.locator("#main").getByText("No schedule configured")).toBeVisible();
});

test("out-of-range parameters degrade gracefully instead of erroring", async ({
  page,
}) => {
  const { alex } = ids();
  await page.goto(`/players/${alex}?year=1000&page=99999999999999999999`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Alex TESTER" }),
  ).toBeVisible();
  await page.goto(`/players/${alex}?page=50`);
  await expect(page.getByText("No more matches")).toBeVisible();
  await page.goto("/tournaments?page=999");
  await expect(page.getByText("No more tournaments")).toBeVisible();
});
