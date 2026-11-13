import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Player search. A plain GET form: works before JavaScript loads, and the URL is the state. */
export function SearchForm({
  defaultValue,
  autoFocus = false,
  compact = false,
}: {
  defaultValue?: string;
  autoFocus?: boolean;
  compact?: boolean;
}) {
  return (
    <form
      action="/"
      method="get"
      role="search"
      className="flex w-full items-center gap-2"
    >
      <label htmlFor={compact ? "q-compact" : "q"} className="sr-only">
        Search players by name
      </label>
      <div className="relative flex-1">
        <Search
          aria-hidden
          className={`pointer-events-none absolute top-1/2 -translate-y-1/2 ${compact ? "left-3 size-4 text-on-dark-muted" : "left-4 size-5 text-subtle"}`}
        />
        <Input
          id={compact ? "q-compact" : "q"}
          name="q"
          data-player-search
          type="search"
          defaultValue={defaultValue}
          autoFocus={autoFocus}
          minLength={2}
          maxLength={100}
          required
          autoComplete="off"
          spellCheck={false}
          placeholder={
            compact ? "Search players…" : "Player name, e.g. a surname…"
          }
          className={
            compact
              ? "h-10 rounded-lg border-white/10 bg-night-2 pr-10 pl-9 text-on-dark placeholder:text-on-dark-muted [&::-webkit-search-cancel-button]:hidden"
              : "h-14 rounded-xl border-0 bg-card pl-12 text-[17px] shadow-[0_8px_24px_-12px_rgb(0_0_0/0.5)]"
          }
        />
        {compact && (
          <kbd
            aria-hidden
            className="pointer-events-none absolute top-1/2 right-2.5 flex h-5 min-w-5 -translate-y-1/2 items-center justify-center rounded border border-white/15 px-1.5 font-sans text-[11px] text-on-dark-muted"
          >
            /
          </kbd>
        )}
      </div>
      {!compact && (
        <Button
          type="submit"
          className="h-14 rounded-xl bg-lime px-7 font-display text-[17px] font-bold tracking-[0.06em] text-night uppercase hover:bg-lime/90"
        >
          Search
        </Button>
      )}
    </form>
  );
}
