"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const NAV = [
  // the wordmark already leads to Discover, so on phones the link makes room
  { href: "/", label: "Discover", className: "hidden sm:inline-flex" },
  { href: "/tournaments", label: "Tournaments", className: "" },
  { href: "/coverage", label: "Coverage", className: "" },
];

/** Main navigation; the current section is marked for sighted and screen-reader users alike. */
export function NavLinks() {
  return <NavList path={usePathname()} />;
}

/** The links themselves; `path` null renders none as current (the streaming fallback). */
export function NavList({ path }: { path: string | null }) {
  return (
    <nav
      aria-label="Main"
      className="flex shrink-0 items-center gap-0.5 text-sm md:ml-auto"
    >
      {NAV.map((item) => {
        const current =
          path !== null &&
          (item.href === "/" ? path === "/" : path.startsWith(item.href));
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "relative h-9 items-center rounded-lg px-2 transition-colors sm:px-3",
              item.className || "inline-flex",
              current
                ? "text-foreground after:absolute after:inset-x-2 after:-bottom-[13px] sm:after:inset-x-3 after:h-px after:bg-primary"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
