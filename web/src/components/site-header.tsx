import { Search } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { Mark } from "@/components/brand";
import { NavLinks, NavList } from "@/components/nav-links";
import { SearchForm } from "@/components/search-form";
import { SlashFocus } from "@/components/slash-focus";
import { api } from "@/lib/api/client";
import { formatMoment, formatNextSync } from "@/lib/format";

function Wordmark() {
  return (
    <Link href="/" className="flex shrink-0 items-center gap-2.5">
      <Mark className="size-8 shrink-0 rounded-lg ring-1 ring-white/15" />
      <span
        translate="no"
        className="display text-[20px] leading-none tracking-[0.04em] text-on-dark uppercase"
      >
        Badminton <span className="text-lime">Scout</span>
      </span>
    </Link>
  );
}

/** The midnight top bar: identity, sections and search on desktop; tabs at the bottom below 1024 px. */
export function TopBar({ showSearch }: { showSearch: boolean }) {
  return (
    <>
      <header className="on-dark sticky top-0 z-30 bg-night">
        <div className="mx-auto flex h-14 w-full max-w-[1240px] items-center gap-8 px-4 sm:px-8 lg:h-16">
          <Wordmark />
          <div className="hidden h-full lg:block">
            <Suspense fallback={<NavList path={null} variant="bar" />}>
              <NavLinks variant="bar" />
            </Suspense>
          </div>
          {showSearch && (
            <>
              <div className="ml-auto hidden w-72 lg:block">
                <SearchForm compact />
              </div>
              <Link
                href="/"
                aria-label="Search players"
                className="ml-auto flex size-11 items-center justify-center rounded-lg text-on-dark-muted hover:text-on-dark lg:hidden"
              >
                <Search aria-hidden className="size-5" />
              </Link>
            </>
          )}
        </div>
        <SlashFocus />
      </header>
      <div className="fixed inset-x-0 bottom-0 z-20 lg:hidden">
        <Suspense fallback={<NavList path={null} variant="tabs" />}>
          <NavLinks variant="tabs" />
        </Suspense>
      </div>
    </>
  );
}

/** Data freshness, in the footer of every page. */
export async function Freshness() {
  const c = await api.coverage();
  return (
    <p className="num">
      Last sync {formatMoment(c.last_sync_at) ?? "not yet run"} · Next{" "}
      {formatNextSync(c.next_sync_at)}
    </p>
  );
}
