import type { Metadata } from "next";
import { Suspense } from "react";

import { FedCode, RowsSkeleton, Section } from "@/components/bits";
import { Shell } from "@/components/shell";
import { type Coverage, api } from "@/lib/api/client";
import { formatDate, formatMoment, formatNextSync } from "@/lib/format";
import { FEDERATION, PROVIDER_STATUS, SYNC_STATUS } from "@/lib/providers";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Data coverage" };

// status as words in a tone, not filled chips: green good, ink partial, grey waiting, red bad
const TONE = {
  good: "text-win",
  partial: "text-foreground",
  waiting: "text-muted-foreground",
  bad: "text-loss",
};

export default function CoveragePage() {
  return (
    <Shell>
      <header className="max-w-3xl pb-6">
        <h1 className="display text-[32px] leading-[1.05] sm:text-[42px]">
          Data coverage
        </h1>
        <p className="mt-2 text-[15px] text-muted-foreground">
          Where every record comes from, how fresh it is, and what is not yet
          covered. A federation listed here means some of its tournaments are
          imported, not all of them.
        </p>
      </header>
      <Suspense fallback={<RowsSkeleton rows={6} />}>
        <Ledger />
      </Suspense>
    </Shell>
  );
}

async function Ledger() {
  const c = await api.coverage();
  return (
    <div className="space-y-10">
      <p className="num max-w-[65ch] border-t-2 border-b border-t-form border-b-border py-3 text-[15px]">
        {c.public_tournaments.toLocaleString("en-AU")} public tournaments,{" "}
        {c.public_matches.toLocaleString("en-AU")} matches and{" "}
        {c.public_players.toLocaleString("en-AU")} players.{" "}
        <span className="text-muted-foreground">
          {c.awaiting_import.toLocaleString("en-AU")} more tournaments are
          listed and awaiting import.
        </span>
      </p>

      <Section title="Data freshness">
        <dl className="grid gap-6 pt-5 sm:grid-cols-2">
          <div>
            <dt className="text-[13px] text-muted-foreground">
              Last successful sync
            </dt>
            <dd className="mt-1.5 text-[16px]">
              {formatMoment(c.last_sync_at) ?? "No sync has run yet"}
            </dd>
          </div>
          <div>
            <dt className="text-[13px] text-muted-foreground">
              Next scheduled sync
            </dt>
            <dd className="mt-1.5 text-[16px]">
              {formatNextSync(c.next_sync_at)}
            </dd>
          </div>
        </dl>
        <p className="mt-4 max-w-[65ch] text-[14px] text-pretty text-muted-foreground">
          A scheduled job imports new and corrected results within each
          provider’s daily request allowance. Pages read our database only; they
          never contact the providers. Awaiting import counts listings, not
          results.
        </p>
      </Section>

      <Federations coverage={c} />

      <div className="grid gap-12 md:grid-cols-2">
        <Section title="How players are identified">
          <div className="max-w-[65ch] space-y-3 pt-4 text-[14px] text-pretty text-muted-foreground">
            <p>
              Records are joined automatically only on a stable identifier
              issued by the same federation, and only when nothing conflicts.
              Similar names alone never join two records.
            </p>
            <p>
              Anything uncertain stays as separate records until stronger
              evidence arrives. Every link is recorded and can be undone.
            </p>
          </div>
        </Section>
        <Section title="Sourced and calculated">
          <div className="max-w-[65ch] space-y-3 pt-4 text-[14px] text-pretty text-muted-foreground">
            <p>
              <span className="text-foreground">Sourced, as published:</span>{" "}
              names, tournaments, dates, events, rounds, scores, walkovers,
              retirements, courts and durations.
            </p>
            <p>
              <span className="text-foreground">Calculated here:</span> win–loss
              records, head-to-head counts and recent form, from decided matches
              only. A cancelled or unplayed match never counts as a win or a
              loss. There are no rankings or ratings.
            </p>
          </div>
        </Section>
      </div>

      {c.excluded.length > 0 && (
        <Section title="Deliberately not published">
          <ul className="list-disc space-y-1 pt-4 pl-5 text-[14px] text-muted-foreground">
            {c.excluded.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

/** The ledger: one row per source, its real public counts, span, health and known limits. */
function Federations({ coverage }: { coverage: Coverage }) {
  const rows = [...coverage.providers].sort(
    (a, b) => b.public_matches - a.public_matches,
  );
  return (
    <Section title="Federations and sources">
      <ul className="divide-y">
        {rows.map((p) => {
          const status = PROVIDER_STATUS[p.status];
          const fed = FEDERATION[p.source_id];
          return (
            <li
              key={p.source_id}
              className="grid gap-x-8 gap-y-3 py-6 md:grid-cols-[minmax(0,1fr)_14rem]"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3">
                  <FedCode code={fed?.code ?? "—"} />
                  <h3 className="display text-[22px]">
                    {fed?.country ?? fed?.label ?? p.name}
                  </h3>
                  <span
                    className={cn(
                      "text-[13px] font-semibold",
                      TONE[status.tone],
                    )}
                  >
                    {status.text}
                  </span>
                </div>
                <p className="mt-1 text-[13px] text-subtle">{p.name}</p>
                {p.limitations.length > 0 && (
                  <ul className="mt-3 space-y-1 text-[14px] text-muted-foreground">
                    {p.limitations.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                )}
              </div>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-[13px] md:grid-cols-1">
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Public tournaments</dt>
                  <dd className="num font-medium">
                    {p.public_tournaments.toLocaleString("en-AU")}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Public matches</dt>
                  <dd className="num font-medium">
                    {p.public_matches.toLocaleString("en-AU")}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-muted-foreground">Discovered</dt>
                  <dd className="num">
                    {p.discovered_tournaments.toLocaleString("en-AU")}
                  </dd>
                </div>
                {p.awaiting_import > 0 && (
                  <div className="flex justify-between gap-4">
                    <dt className="text-muted-foreground">Awaiting import</dt>
                    <dd className="num">
                      {p.awaiting_import.toLocaleString("en-AU")}
                    </dd>
                  </div>
                )}
                {p.first_played && (
                  <div className="col-span-2 text-subtle md:col-span-1">
                    <dt className="sr-only">Matches span</dt>
                    <dd className="num">
                      Matches {formatDate(p.first_played)} –{" "}
                      {formatDate(p.last_played)}
                    </dd>
                  </div>
                )}
                <div className="col-span-2 text-subtle md:col-span-1">
                  <dt className="sr-only">Last sync</dt>
                  <dd>
                    {p.last_sync_at
                      ? `Synced ${formatMoment(p.last_sync_at)}: ${SYNC_STATUS[p.last_sync_status ?? ""] ?? p.last_sync_status}`
                      : "Not synced yet"}
                  </dd>
                </div>
              </dl>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
