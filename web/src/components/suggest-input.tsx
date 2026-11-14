"use client";

import { useRouter } from "next/navigation";
import {
  type ComponentProps,
  type KeyboardEvent,
  useEffect,
  useId,
  useState,
} from "react";

import type { Suggestion } from "@/app/api/suggest/route";
import { cn } from "@/lib/utils";

const DELAY_MS = 150;

const dateFormat = new Intl.DateTimeFormat("en-AU", {
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** The search input with player suggestions as you type (ARIA combobox). Arrow keys pick a
 * player, Enter opens them; Enter with nothing picked submits the surrounding form as before,
 * so the search still works without JavaScript. */
export function SuggestInput({
  className,
  defaultValue,
  ...props
}: Omit<ComponentProps<"input">, "value" | "onChange">) {
  const router = useRouter();
  const listId = useId();
  const [value, setValue] = useState(String(defaultValue ?? ""));
  const [items, setItems] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [typed, setTyped] = useState(false); // not for a prefilled query, only once typing

  useEffect(() => {
    const q = value.trim();
    if (!typed || q.length < 2) return; // `show` hides the list below 2 characters
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const r = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`, {
          signal: controller.signal,
        });
        const found = (await r.json()) as Suggestion[];
        setItems(found);
        setActive(-1);
        setOpen(true);
      } catch {
        // aborted by the next keystroke, or offline: keep the form working
      }
    }, DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value, typed]);

  const show = open && value.trim().length >= 2 && typed;

  function go(s: Suggestion) {
    setOpen(false);
    router.push(`/players/${s.id}`);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" && items.length) {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % items.length);
    } else if (e.key === "ArrowUp" && items.length) {
      e.preventDefault();
      setActive((i) => (i <= 0 ? items.length - 1 : i - 1));
    } else if (e.key === "Enter" && show && active >= 0 && items[active]) {
      e.preventDefault();
      go(items[active]);
    } else if (e.key === "Escape" && show) {
      e.preventDefault();
      setOpen(false);
      setActive(-1);
    }
  }

  return (
    <>
      <input
        {...props}
        // uncontrolled: text typed before hydration is kept, a controlled value would reset it
        defaultValue={defaultValue}
        onChange={(e) => {
          setTyped(true);
          setValue(e.target.value);
        }}
        onKeyDown={onKeyDown}
        onBlur={() => setOpen(false)}
        onFocus={() => items.length && setOpen(true)}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={show}
        aria-controls={listId}
        aria-activedescendant={
          show && active >= 0 ? `${listId}-${active}` : undefined
        }
        className={className}
      />
      <ul
        id={listId}
        role="listbox"
        aria-label="Player suggestions"
        hidden={!show}
        className="absolute inset-x-0 top-full z-40 mt-1 max-h-80 overflow-y-auto rounded-md border border-input bg-background py-1 text-left shadow-[0_8px_24px_-12px_rgb(20_23_26/0.35)]"
      >
        {items.length === 0 ? (
          <li
            role="option"
            aria-selected={false}
            aria-disabled
            className="px-3 py-2 text-[14px] text-muted-foreground"
          >
            No players match yet. Press Enter to search.
          </li>
        ) : (
          items.map((s, i) => (
            <li
              key={s.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              // mousedown keeps focus in the input, so blur does not close the list first
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => go(s)}
              onMouseEnter={() => setActive(i)}
              className={cn(
                "flex cursor-pointer flex-wrap items-baseline justify-between gap-x-3 px-3 py-2",
                i === active && "bg-wash",
              )}
            >
              <span className="font-semibold">{s.name}</span>
              <span className="num shrink-0 text-[12px] text-muted-foreground">
                {s.matches} {s.matches === 1 ? "match" : "matches"}
                {s.last_played
                  ? ` · ${dateFormat.format(new Date(`${s.last_played}T00:00:00Z`))}`
                  : ""}
              </span>
            </li>
          ))
        )}
      </ul>
      <span aria-live="polite" className="sr-only">
        {show ? `${items.length} player suggestions` : ""}
      </span>
    </>
  );
}
