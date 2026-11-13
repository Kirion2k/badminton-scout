import Link from "next/link";
import type { ReactNode } from "react";

import { TopBar } from "@/components/site-header";

/** Page frame: the bar, one main column, and a footer that points at the sources. */
export function Shell({
  children,
  showSearch = true,
}: {
  children: ReactNode;
  showSearch?: boolean;
}) {
  return (
    <div className="flex min-h-dvh flex-col">
      <TopBar showSearch={showSearch} />
      <main id="main" className="flex-1">
        <div className="mx-auto w-full max-w-[1240px] px-4 pt-6 pb-28 sm:px-8 lg:pt-8 lg:pb-16">
          {children}
        </div>
      </main>
      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-[1240px] flex-wrap justify-between gap-x-6 gap-y-1 px-4 pt-4 pb-24 text-xs text-subtle sm:px-8 lg:pb-5">
          <p>
            Mynton shows results as each federation published them. Absent data
            is marked, never filled in.
          </p>
          <Link href="/coverage" className="underline">
            Sources and freshness
          </Link>
        </div>
      </footer>
    </div>
  );
}
