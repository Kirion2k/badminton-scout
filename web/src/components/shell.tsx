import type { ReactNode } from "react";
import { Suspense } from "react";

import { Freshness, TopBar } from "@/components/site-header";

/** Page frame. `hero` renders full-bleed under the top bar, before the main column. */
export function Shell({
  children,
  hero,
  showSearch = true,
}: {
  children?: ReactNode;
  hero?: ReactNode;
  showSearch?: boolean;
}) {
  return (
    <div className="flex min-h-dvh flex-col">
      <TopBar showSearch={showSearch} />
      <main id="main" className="flex-1">
        {hero}
        {children && <Container>{children}</Container>}
      </main>
      <footer className="border-t bg-card">
        <div className="mx-auto flex w-full max-w-[1240px] flex-wrap justify-between gap-x-6 gap-y-1 px-4 pt-5 pb-24 text-xs text-subtle sm:px-8 lg:pb-6">
          <p>Results are shown as published by their source.</p>
          <Suspense fallback={null}>
            <Freshness />
          </Suspense>
        </div>
      </footer>
    </div>
  );
}

/** The page column. */
export function Container({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-[1240px] px-4 pt-8 pb-28 sm:px-8 lg:pt-10 lg:pb-16">
      {children}
    </div>
  );
}

/** A full-bleed dark band with the court drawn in, and the page's width inside. */
export function Hero({
  tone = "night",
  children,
}: {
  tone?: "night" | "court";
  children: ReactNode;
}) {
  return (
    <section
      className={`on-dark court-lines relative overflow-hidden text-on-dark ${tone === "court" ? "bg-court" : "bg-night"}`}
    >
      <div className="relative mx-auto w-full max-w-[1240px] px-4 pt-8 sm:px-8 lg:pt-12">
        {children}
      </div>
    </section>
  );
}
