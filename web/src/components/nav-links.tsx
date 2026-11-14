"use client";

import { Scale, Search, Table2, Trophy } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Players", icon: Search },
  { href: "/compare", label: "Compare", icon: Scale },
  { href: "/tournaments", label: "Tournaments", icon: Trophy },
  { href: "/coverage", label: "Sources", icon: Table2 },
];

type Variant = "bar" | "tabs";

/** Main navigation; the current section is marked for sighted and screen-reader users alike. */
export function NavLinks({ variant }: { variant: Variant }) {
  return <NavList path={usePathname()} variant={variant} />;
}

function isCurrent(path: string | null, href: string) {
  if (path === null) return false;
  if (href === "/") return path === "/" || path.startsWith("/players");
  return path.startsWith(href);
}

/** The links themselves; `path` null renders none as current (the streaming fallback). */
export function NavList({
  path,
  variant,
}: {
  path: string | null;
  variant: Variant;
}) {
  return (
    <nav
      aria-label="Main"
      className={
        variant === "bar"
          ? "flex items-center gap-5"
          : "grid grid-cols-3 border-t bg-background pb-[env(safe-area-inset-bottom)]"
      }
    >
      {NAV.map(({ href, label, icon: Icon }) => {
        const current = isCurrent(path, href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "transition-colors",
              variant === "bar"
                ? "text-[14px]"
                : "flex min-h-14 flex-col items-center justify-center gap-0.5 text-[12px]",
              current
                ? "font-semibold text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {variant === "tabs" && (
              <Icon
                aria-hidden
                className={cn("size-5", current && "text-form")}
              />
            )}
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
