import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState, FormStrip, ResultBadge, Score } from "./bits";

describe("components", () => {
  it("result badges carry words, not just colour", () => {
    render(<ResultBadge status="not_played" result={null} />);
    expect(screen.getByText("Not played")).toBeInTheDocument();
    expect(screen.getByText(/Cancelled or not played/)).toBeInTheDocument();
  });
  it("a missing score shows a dash, not zeros", () => {
    render(<Score games={[]} />);
    expect(screen.getByText("–")).toBeInTheDocument();
  });
  it("the form strip summarises for screen readers", () => {
    render(<FormStrip results={["won", "lost", "won"]} />);
    expect(
      screen.getByRole("list", {
        name: "Last 3 decided matches, oldest first: 2 won",
      }),
    ).toBeInTheDocument();
  });
  it("renders nothing for no decided matches", () => {
    const { container } = render(<FormStrip results={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
  it("empty states explain", () => {
    render(<EmptyState title="No matches">Try another filter</EmptyState>);
    expect(screen.getByText("Try another filter")).toBeInTheDocument();
  });
});
