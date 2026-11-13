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
    <Link href="/" className="flex items-center gap-2.5">
      <Mark className="size-8 shrink-0" />
      <span
        translate="no"
        className="display text-[19px] leading-none font-semibold"
      >
        Badminton Scout
      </span>
    </Link>
  );
}

/** Desktop: a sidebar with identity, search, sections and live data freshness. */
export function Sidebar({ showSearch }: { showSearch: boolean }) {
  return (
    <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-r bg-background px-4 py-6 lg:flex">
      <div className="px-2">
        <Wordmark />
        <p className="mt-2 text-xs text-muted-foreground">
          Every match, traced.
        </p>
      </div>
      {showSearch && (
        <div className="mt-6">
          <SearchForm compact />
        </div>
      )}
      <div className="mt-6">
        <Suspense fallback={<NavList path={null} variant="sidebar" />}>
          <NavLinks variant="sidebar" />
        </Suspense>
      </div>
      <div className="mt-auto px-2">
        <Suspense fallback={null}>
          <Freshness />
        </Suspense>
      </div>
      <SlashFocus />
    </aside>
  );
}

/** Below 1024 px: a slim top bar, and the sections as bottom tabs. */
export function MobileBar({ showSearch }: { showSearch: boolean }) {
  return (
    <>
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur lg:hidden">
        <Wordmark />
        {showSearch && (
          <Link
            href="/"
            aria-label="Search players"
            className="flex size-11 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Search aria-hidden className="size-5" />
          </Link>
        )}
      </header>
      <div className="fixed inset-x-0 bottom-0 z-20 lg:hidden">
        <Suspense fallback={<NavList path={null} variant="tabs" />}>
          <NavLinks variant="tabs" />
        </Suspense>
      </div>
    </>
  );
}

async function Freshness() {
  const c = await api.coverage();
  return (
    <dl className="space-y-2 border-t pt-4 text-xs">
      <div>
        <dt className="label-quiet">Last sync</dt>
        <dd className="mt-0.5 text-foreground">
          {formatMoment(c.last_sync_at) ?? "Not yet run"}
        </dd>
      </div>
      <div>
        <dt className="label-quiet">Next sync</dt>
        <dd className="mt-0.5 text-muted-foreground">
          {formatNextSync(c.next_sync_at)}
        </dd>
      </div>
    </dl>
  );
}
