import { Search } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { NavLinks, NavList } from "@/components/nav-links";
import { SearchForm } from "@/components/search-form";
import { SlashFocus } from "@/components/slash-focus";

export function SiteHeader({ showSearch = true }: { showSearch?: boolean }) {
  return (
    <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-background/80 backdrop-blur-xl backdrop-saturate-150">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-2 px-4 sm:gap-6 sm:px-6">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2.5 text-[15px] font-semibold tracking-[-0.01em]"
        >
          <span
            aria-hidden
            className="relative flex size-5 items-center justify-center"
          >
            <span className="absolute size-5 rounded-full bg-primary/15" />
            <span className="size-2 rounded-full bg-primary" />
          </span>
          <span>
            Badminton <span className="text-muted-foreground">Scout</span>
          </span>
        </Link>
        {showSearch ? (
          <div className="hidden max-w-[22rem] flex-1 md:block">
            <SearchForm compact />
          </div>
        ) : (
          <div className="flex-1" />
        )}
        {showSearch && (
          <Link
            href="/"
            className="ml-auto rounded-lg p-2 text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground md:hidden"
            aria-label="Search players"
          >
            <Search aria-hidden className="size-4" />
          </Link>
        )}
        <Suspense fallback={<NavList path={null} />}>
          <NavLinks />
        </Suspense>
      </div>
      <SlashFocus />
    </header>
  );
}
