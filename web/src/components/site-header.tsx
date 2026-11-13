import { Suspense } from "react";

import { Wordmark } from "@/components/brand";
import { NavLinks, NavList } from "@/components/nav-links";
import { SearchForm } from "@/components/search-form";
import { SlashFocus } from "@/components/slash-focus";

/** One white bar: the wordmark, the player search (the product's front door) and the sections.
 * Below 1024 px the search keeps the bar and the sections move to tabs at the bottom. */
export function TopBar({ showSearch }: { showSearch: boolean }) {
  return (
    <>
      <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur-sm">
        <div className="mx-auto flex h-14 w-full max-w-[1240px] items-center gap-4 px-4 sm:gap-8 sm:px-8">
          <Wordmark />
          <div className="min-w-0 flex-1 sm:max-w-[520px]">
            {showSearch && <SearchForm compact />}
          </div>
          <div className="ml-auto hidden lg:block">
            <Suspense fallback={<NavList path={null} variant="bar" />}>
              <NavLinks variant="bar" />
            </Suspense>
          </div>
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
