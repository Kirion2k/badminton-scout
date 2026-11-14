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
  const search = page.getByRole("combobox", {
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

  const history = page.getByRole("region", { name: "Matches, newest first" });
  await expect(
    history.getByTitle("Cancelled or not played: no result"),
  ).toBeVisible(); // not a loss
  await expect(history.getByText("W ret.")).toBeVisible(); // retirement keeps its W, marked
  await expect(history.getByText("W/O")).toBeVisible(); // walkover, marked
  await expect(history.getByTitle("21–15 · 21–18")).toBeVisible(); // score from Alex's side

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
      .getByRole("region", { name: "Matches, newest first" })
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
    .getByRole("region", { name: "Matches, newest first" })
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
  await expect(
    page.locator("#main").getByText("No sync has run yet"),
  ).toBeVisible();
  await expect(
    page.locator("#main").getByText("No schedule configured"),
  ).toBeVisible();
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

test("a result row opens to its scoresheet and closes again", async ({
  page,
}) => {
  await page.goto(`/tournaments/${ids().spring}`);
  const toggle = page.getByRole("button", { name: "Scoresheet: 21–15 21–18" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const panel = page.locator(`#${await toggle.getAttribute("aria-controls")}`);
  await expect(panel.getByTitle("21–15 · 21–18")).toBeVisible();
  await toggle.press("Enter");
  await expect(panel).toBeHidden();
});

test("compare two players, open a shared match's tournament, come back", async ({
  page,
}) => {
  await page.goto(`/players/${ids().alex}`);
  await page.getByRole("link", { name: /^Compare with Sam EXAMPLE$/ }).click();
  await expect(page).toHaveURL(/\/players\/\d+\/vs\/\d+$/);
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: /Alex TESTER\s*v\s*Sam EXAMPLE/,
    }),
  ).toBeVisible();
  const meetings = page.getByRole("region", { name: "Meetings, newest first" });
  await expect(meetings.getByRole("listitem").first()).toBeVisible();
  const compareUrl = page.url();
  await meetings
    .getByRole("link", { name: "Synthetic Spring Open 2026" })
    .first()
    .click();
  await expect(page).toHaveURL(new RegExp(`/tournaments/${ids().spring}`));
  await page.goBack();
  await expect(page).toHaveURL(compareUrl); // back lands on the same comparison
  // the other way round, from the comparison's own link
  await page.getByRole("link", { name: /See it from Sam EXAMPLE/ }).click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: /Sam EXAMPLE\s*v\s*Alex TESTER/,
    }),
  ).toBeVisible();
});

test("pick any player to compare with by name", async ({ page }) => {
  await page.goto(`/players/${ids().alex}`);
  const form = page.getByRole("search", {
    name: "Compare with another player",
  });
  await form.getByRole("searchbox").fill("kim sample");
  await form.getByRole("button", { name: "Find" }).click();
  await expect(page).toHaveURL(/\/vs\?q=kim\+sample/);
  await page
    .getByRole("link", { name: /Kim SAMPLE/ })
    .first()
    .click();
  await expect(page).toHaveURL(/\/players\/\d+\/vs\/\d+$/);
  await expect(page.getByText(/meeting/).first()).toBeVisible();
});

test("suggestions as you type: pick one with the keyboard", async ({
  page,
}) => {
  await page.goto("/");
  const search = page.getByRole("combobox", {
    name: "Search players by name",
  });
  // focused once the streamed form has replaced the first-paint one and React is running;
  // typing earlier goes into the placeholder form and is lost (shortcut: see the home page)
  await expect(search).toBeFocused();
  await search.pressSequentially("alex tes", { delay: 30 });
  const option = page.getByRole("option", { name: /Alex TESTER/ });
  await expect(option).toBeVisible();
  await expect(search).toHaveAttribute("aria-expanded", "true");
  await search.press("ArrowDown");
  await expect(option).toHaveAttribute("aria-selected", "true");
  await search.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/players/${ids().alex}$`));

  // Escape closes the list and Enter then searches as before
  await search.fill("");
  await search.pressSequentially("alex tes", { delay: 30 });
  await expect(option).toBeVisible();
  await search.press("Escape");
  await expect(option).toBeHidden();
  await search.press("Enter");
  await expect(page).toHaveURL(/\/\?q=alex\+tes/);
});

test("matchup: pick two players, compare results, never a percentage", async ({
  page,
}) => {
  await page.goto("/compare");
  const first = page.getByRole("search", { name: "Find the first player" });
  await first.getByRole("searchbox").fill("alex tester");
  await first.getByRole("button", { name: "Search" }).click();
  await page
    .getByRole("link", { name: /Alex TESTER/ })
    .first()
    .click();
  const second = page.getByRole("search", { name: "Find the second player" });
  await second.getByRole("searchbox").fill("sam example");
  await second.getByRole("button", { name: "Search" }).click();
  await page
    .getByRole("link", { name: /Sam EXAMPLE/ })
    .first()
    .click();

  await expect(page).toHaveURL(/\/compare\?.*a=\d+.*b=\d+/);
  const matchup = page.locator("section", {
    has: page.getByRole("heading", { name: "Matchup" }),
  });
  await expect(matchup.getByText("Historical comparison")).toBeVisible();
  await expect(matchup.getByText(/no validated rating/)).toBeVisible();
  await expect(matchup).not.toContainText("%"); // probabilities are off (ADR-0013)
  await expect(page.getByRole("heading", { name: "Meetings" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /Recent results: Alex TESTER/ }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Women's singles" }).click();
  await expect(
    matchup.getByText("Not enough results to compare"),
  ).toBeVisible();
});

test("matchup: a merged player's old id stays on the matchup page", async ({
  page,
}) => {
  const { jordanMergedFrom, jordan, alex } = ids();
  await page.goto(`/compare?a=${jordanMergedFrom}&discipline=WS`);
  await expect(page).toHaveURL(
    new RegExp(`/compare\\?discipline=WS&a=${jordan}$`),
  );
  await page.goto(`/compare?a=${jordanMergedFrom}&b=${alex}&discipline=MS`);
  await expect(page).toHaveURL(
    new RegExp(`/compare\\?a=${jordan}&b=${alex}&discipline=MS$`),
  );
});
