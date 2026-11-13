import type { ReactNode } from "react";

import { SiteHeader } from "@/components/site-header";

export function Shell({
  children,
  showSearch = true,
}: {
  children: ReactNode;
  showSearch?: boolean;
}) {
  return (
    <>
      <SiteHeader showSearch={showSearch} />
      <main
        id="main"
        className="mx-auto w-full max-w-[1200px] flex-1 px-4 pt-10 pb-16 sm:px-6 sm:pt-14"
      >
        {children}
      </main>
      <footer className="border-t border-white/[0.05]">
        <div className="mx-auto max-w-[1200px] px-4 py-6 text-xs text-subtle sm:px-6">
          Results are shown as published by their source.
        </div>
      </footer>
    </>
  );
}
