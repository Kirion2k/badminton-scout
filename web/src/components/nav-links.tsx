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

type Variant = "bar" | "tabs";

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
        variant === "bar"
          ? "flex h-full items-stretch gap-1"
          : "grid grid-cols-3 border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      }
    >
      {NAV.map(({ href, label, icon: Icon }) => {
        const current =
          path !== null &&
          (href === "/" ? path === "/" : path.startsWith(href));
        return variant === "bar" ? (
          <Link
            key={href}
            href={href}
            aria-current={current ? "page" : undefined}
            className={cn(
              // the lime underline grows in from the centre when a section becomes current
              "relative flex items-center px-3.5 font-display text-[16px] font-semibold tracking-[0.06em] uppercase transition-colors after:absolute after:inset-x-3 after:bottom-0 after:h-[3px] after:origin-center after:rounded-t-sm after:bg-lime after:transition-transform after:duration-200",
              current
                ? "text-on-dark after:scale-x-100"
                : "text-on-dark-muted after:scale-x-0 hover:text-on-dark",
            )}
          >
            {label}
          </Link>
        ) : (
          <Link
            key={href}
            href={href}
            aria-current={current ? "page" : undefined}
            className={cn(
              "flex min-h-14 flex-col items-center justify-center gap-1 font-display text-[12px] font-semibold tracking-[0.08em] uppercase transition-colors",
              current ? "text-foreground" : "text-muted-foreground",
            )}
          >
            <span
              className={cn(
                "flex h-7 w-12 items-center justify-center rounded-full transition-colors duration-200",
                current && "bg-night text-lime",
              )}
            >
              <Icon aria-hidden className="size-[18px]" />
            </span>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
