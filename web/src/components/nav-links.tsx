"use client";

import { Compass, Globe2, Trophy } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Discover", icon: Compass },
  { href: "/tournaments", label: "Tournaments", icon: Trophy },
  { href: "/coverage", label: "Coverage", icon: Globe2 },
];

type Variant = "sidebar" | "tabs";

/** Main navigation; the current section is marked for sighted and screen-reader users alike. */
export function NavLinks({ variant }: { variant: Variant }) {
  return <NavList path={usePathname()} variant={variant} />;
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
        variant === "sidebar"
          ? "flex flex-col gap-0.5"
          : "grid grid-cols-3 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      }
    >
      {NAV.map(({ href, label, icon: Icon }) => {
        const current =
          path !== null &&
          (href === "/" ? path === "/" : path.startsWith(href));
        return (
          <Link
            key={href}
            href={href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "transition-colors",
              variant === "sidebar"
                ? "flex h-10 items-center gap-3 rounded-lg px-3 text-[14px]"
                : "flex min-h-14 flex-col items-center justify-center gap-1 text-[11px] font-medium",
              current
                ? variant === "sidebar"
                  ? "bg-foreground text-background"
                  : "text-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon
              aria-hidden
              className={cn(
                "size-[18px]",
                variant === "tabs" && current && "text-accent-ink",
              )}
            />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
