import type { Metadata } from "next";
import { Suspense } from "react";

import { Fact, Panel, PageHeader, RowsSkeleton } from "@/components/bits";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api/client";
import {
  formatDate,
  formatMoment,
  formatNextSync,
  formatRetrieved,
} from "@/lib/format";
import { PROVIDER_STATUS, SYNC_STATUS } from "@/lib/providers";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Data coverage" };

const TONE = {
  good: "border-win/40 text-win",
  partial: "border-primary/40 text-primary",
  waiting: "border-neutral-status/40 text-neutral-status",
  bad: "border-loss/40 text-loss",
};

export default function CoveragePage() {
  return (
    <Shell>
      <PageHeader title="Data coverage">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Where every record comes from, how fresh it is, and what is
          deliberately left out.
        </p>
      </PageHeader>
      <div className="space-y-6">
        <Suspense fallback={<RowsSkeleton rows={4} />}>
          <Providers />
        </Suspense>
        <div className="grid gap-6 md:grid-cols-2">
          <Panel title="How players are identified">
            <div className="space-y-2 p-4 text-sm text-muted-foreground">
              <p>
                Each source’s own player identifier is kept as received. A
                player is never merged with another just because their names
                match.
              </p>
              <p>
                Possible duplicates are listed for a person to review. Every
                merge is recorded and can be undone, and an old player link then
                leads to the merged profile.
              </p>
            </div>
          </Panel>
          <Panel title="Sourced versus calculated">
            <div className="space-y-2 p-4 text-sm text-muted-foreground">
              <p>
                <span className="text-foreground">Sourced, as published:</span>{" "}
                names, tournaments, dates, events, rounds, scores, walkovers,
                retirements, courts and durations.
              </p>
              <p>
                <span className="text-foreground">Calculated here:</span>{" "}
                win–loss records, head-to-head counts and recent form, from
                decided matches only. A cancelled or unplayed match is never
                counted as a win or a loss. There are no rankings or ratings
                yet.
              </p>
            </div>
          </Panel>
        </div>
      </div>
    </Shell>
  );
}

async function Providers() {
  const coverage = await api.coverage();
  return (
    <>
      <Panel title="Data freshness">
        <dl className="grid grid-cols-2 gap-4 p-4 text-sm md:grid-cols-4">
          <Fact term="Last successful sync">
            {formatMoment(coverage.last_sync_at) ?? "No sync has run yet"}
          </Fact>
          <Fact term="Next scheduled sync">
            {formatNextSync(coverage.next_sync_at)}
          </Fact>
          <Fact term="Public tournaments">
            <span className="num">
              {coverage.public_tournaments.toLocaleString("en-AU")}
            </span>
          </Fact>
          <Fact term="Awaiting import">
            <span className="num">
              {coverage.awaiting_import.toLocaleString("en-AU")}
            </span>
          </Fact>
        </dl>
        <p className="border-t px-4 py-2 text-xs text-muted-foreground">
          A scheduled job imports new and updated results within each provider’s
          daily request allowance. Pages read our database only; they never
          contact the providers. Awaiting import counts listings, not results.
        </p>
      </Panel>
      <Panel title="Providers">
        <div
          className="overflow-x-auto"
          tabIndex={0}
          role="region"
          aria-label="Providers table"
        >
          <table className="w-full text-sm">
            <caption className="sr-only">
              Data providers, their connection status and what each contributes
            </caption>
            <thead className="border-b text-left text-xs text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Provider
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  Status
                </th>
                <th
                  scope="col"
                  className="px-4 py-2.5 text-right font-medium"
                  title="Listed by the provider: not a claim that results exist"
                >
                  Discovered
                </th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">
                  Public
                </th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">
                  Public matches
                </th>
                <th
                  scope="col"
                  className="hidden px-4 py-2.5 font-medium md:table-cell"
                >
                  Sync
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {coverage.providers.map((p) => {
                const status = PROVIDER_STATUS[p.status];
                return (
                  <tr key={p.source_id} className="align-top">
                    <td className="px-4 py-3">
                      <span className="font-medium">{p.name}</span>
                      <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                        {p.limitations.map((l) => (
                          <li key={l}>{l}</li>
                        ))}
                      </ul>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "rounded border px-1.5 py-0.5 text-xs whitespace-nowrap",
                          TONE[status.tone],
                        )}
                      >
                        {status.text}
                      </span>
                    </td>
                    <td className="num px-4 py-3 text-right">
                      {p.discovered_tournaments}
                    </td>
                    <td className="num px-4 py-3 text-right">
                      {p.public_tournaments}
                    </td>
                    <td className="num px-4 py-3 text-right">
                      {p.public_matches.toLocaleString("en-AU")}
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">
                      {p.last_sync_at
                        ? `synced ${formatMoment(p.last_sync_at)}: ${SYNC_STATUS[p.last_sync_status ?? ""] ?? p.last_sync_status}`
                        : formatRetrieved(p.last_retrieved_at)}
                      {p.awaiting_import > 0 && (
                        <span className="num block text-xs">
                          {p.awaiting_import} awaiting import
                        </span>
                      )}
                      {p.first_played && (
                        <span className="num block text-xs">
                          matches {formatDate(p.first_played)} –{" "}
                          {formatDate(p.last_played)}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <dl className="grid gap-x-6 gap-y-2 border-t px-4 py-3 text-xs text-muted-foreground sm:grid-cols-2">
          <div>
            <dt className="inline font-medium text-foreground">Discovered:</dt>{" "}
            <dd className="inline">
              listed by the provider. Results are not assumed.
            </dd>
          </div>
          <div>
            <dt className="inline font-medium text-foreground">Public:</dt>{" "}
            <dd className="inline">
              at least one match that may be shown here.
            </dd>
          </div>
        </dl>
      </Panel>
      {coverage.excluded.length > 0 && (
        <Panel title="Deliberately not published">
          <ul className="list-disc space-y-1 py-4 pr-4 pl-9 text-sm text-muted-foreground">
            {coverage.excluded.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
          <p className="border-t px-4 py-2 text-xs text-muted-foreground">
            These records are filtered on the server before any page is built,
            and every count on this site includes published records only.
          </p>
        </Panel>
      )}
    </>
  );
}
