import { describe, expect, it } from "vitest";

import { importFlag } from "@/lib/providers";

import {
  formatDate,
  formatDateRange,
  formatScore,
  positiveInt,
  resultLabel,
  validYear,
  formatNextSync,
} from "./format";

describe("resultLabel", () => {
  it("never shows a cancelled or unplayed match as a loss", () => {
    expect(resultLabel("not_played", null)).toMatchObject({
      text: "Not played",
      tone: "neutral",
    });
    expect(resultLabel("not_played", "lost").tone).toBe("neutral");
  });
  it("keeps a walkover's or retirement's result, marked", () => {
    expect(resultLabel("walkover", "won")).toMatchObject({
      text: "W/O",
      tone: "win",
    });
    expect(resultLabel("walkover", "lost")).toMatchObject({
      text: "L w/o",
      tone: "loss",
    });
    expect(resultLabel("retired", "won")).toMatchObject({
      text: "W ret.",
      tone: "win",
    });
  });
  it("labels plain results", () => {
    expect(resultLabel("completed", "won").text).toBe("W");
    expect(resultLabel("completed", "lost").text).toBe("L");
    expect(resultLabel("completed", null).tone).toBe("neutral");
  });
});

describe("formatting", () => {
  it("scores from the viewer's side", () => {
    expect(
      formatScore([
        [21, 15],
        [19, 21],
      ]),
    ).toBe("21–15 · 19–21");
    expect(formatScore([])).toBe("");
  });
  it("dates are timezone-stable and never invented", () => {
    expect(formatDate("2026-03-14")).toBe("14 Mar 2026");
    expect(formatDate(null)).toBe("Date not recorded");
    expect(formatDateRange("2026-03-14", "2026-03-14")).toBe("14 Mar 2026");
    expect(formatDateRange(null, null)).toBe("Dates not recorded");
  });
  it("page numbers fall back on junk and absurd values", () => {
    expect(positiveInt("3", 1)).toBe(3);
    expect(positiveInt("-2", 1)).toBe(1);
    expect(positiveInt("abc", 1)).toBe(1);
    expect(positiveInt("99999999999999999999", 1)).toBe(1);
  });
  it("years outside what the API accepts are dropped", () => {
    expect(validYear("2026")).toBe("2026");
    expect(validYear("1000")).toBeUndefined();
    expect(validYear("20x6")).toBeUndefined();
    expect(validYear(undefined)).toBeUndefined();
  });
});

describe("formatNextSync", () => {
  const now = new Date("2026-11-13T12:00:00Z");
  it("says when no schedule exists", () => {
    expect(formatNextSync(null, now)).toBe("No schedule configured");
  });
  it("shows a planned run in UTC", () => {
    expect(formatNextSync("2026-11-14T00:30:00Z", now)).toBe(
      "14 Nov 2026, 00:30 UTC",
    );
  });
  it("flags a planned run that has passed", () => {
    expect(formatNextSync("2026-11-12T00:30:00Z", now)).toBe(
      "Overdue: was due 12 Nov 2026, 00:30 UTC",
    );
  });
});

describe("importFlag", () => {
  const base = { unimported_matches: 0, note: "" };
  it("says nothing for a complete import", () => {
    expect(importFlag({ ...base, status: "complete" })).toBeNull();
    expect(importFlag(null)).toBeNull();
  });
  it("never lets a partial import pass as complete", () => {
    expect(importFlag({ ...base, status: "partial" })).toBe("Partial results");
    expect(importFlag({ ...base, status: "in_progress" })).toBe("In progress");
    expect(
      importFlag({
        ...base,
        status: "complete_with_gaps",
        unimported_matches: 3,
      }),
    ).toBe("3 matches missing");
  });
});
