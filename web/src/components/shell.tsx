import type { ReactNode } from "react";

import { MobileBar, Sidebar } from "@/components/site-header";

export function Shell({
  children,
  showSearch = true,
}: {
  children: ReactNode;
  showSearch?: boolean;
}) {
  return (
    <div className="flex min-h-dvh">
      <Sidebar showSearch={showSearch} />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileBar showSearch={showSearch} />
        <main
          id="main"
          className="mx-auto w-full max-w-[1160px] flex-1 px-4 pt-8 pb-28 sm:px-8 lg:px-12 lg:pt-14 lg:pb-16"
        >
          {children}
        </main>
        <footer className="mx-auto w-full max-w-[1160px] px-4 pb-24 text-xs text-subtle sm:px-8 lg:px-12 lg:pb-8">
          Results are shown as published by their source.
        </footer>
      </div>
    </div>
  );
}
