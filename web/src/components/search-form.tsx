import { Search } from "lucide-react";

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
  const id = compact ? "q-compact" : "q";
  return (
    <form
      action="/"
      method="get"
      role="search"
      className="flex w-full items-center gap-2"
    >
      <label htmlFor={id} className="sr-only">
        Search players by name
      </label>
      <div className="relative flex-1">
        <Search
          aria-hidden
          className={`pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-subtle ${compact ? "size-4" : "size-5"}`}
        />
        <input
          id={id}
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
            compact ? "Search players" : "Player name, e.g. a surname"
          }
          className={
            compact
              ? "control w-full pr-9 pl-9 [&::-webkit-search-cancel-button]:hidden"
              : "control h-12 w-full pl-10 text-[17px]"
          }
        />
        {compact && (
          <kbd
            aria-hidden
            className="pointer-events-none absolute top-1/2 right-2.5 hidden h-5 min-w-5 -translate-y-1/2 items-center justify-center rounded border px-1.5 font-sans text-[11px] text-subtle sm:flex"
          >
            /
          </kbd>
        )}
      </div>
      {!compact && (
        <button
          type="submit"
          className="h-12 rounded-md bg-form px-6 text-[15px] font-semibold text-white transition-colors hover:bg-form/90"
        >
          Search
        </button>
      )}
    </form>
  );
}
