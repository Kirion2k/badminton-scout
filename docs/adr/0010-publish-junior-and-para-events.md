# ADR-0010: Publish junior and para events

Status: Accepted 2026-11-13. Supersedes ADR-0009's decision to withhold junior and para events.

## Context
ADR-0009 stored junior (minors') and para-badminton (sport class, i.e. health information) events
but never served them. The owner reviewed this on 2026-11-13. The coverage this rule withheld was
large: most `www.` events and every junior-only tournament. The providers already publish these
results openly.

## Decision
The owner decided to publish junior and para events like any other, and accepts responsibility
for that decision and its legal basis.

- `scout.privacy.PUBLISH_RESTRICTED_EVENTS = True`. It is a code constant, not a configuration
  switch (ADR-0002), and changing it needs a new ADR.
- `is_adult_event` (the ADR-0009 allowlist) is kept, so the categories stay known. Events whose
  category isn't recognised are served too.
- The hiding path is kept and tested: `event.redistributable`, `_visible_matches()` and
  `scout privacy reclassify`. Setting the constant to `False` and running `reclassify` hides
  them again.
- The Coverage page no longer claims anything is withheld.

The owner reconfirmed on 2026-11-13, for the global federation expansion, that this applies to
every source. It is a single policy, not per-country rules.

## Consequences and risks the owner accepted
- Children's names, clubs and results are searchable and have profile pages. Privacy law in
  Australia, New Zealand and the EU treats children's data with extra care. A takedown or
  correction request has to be handled by hand: there is no per-player opt-out yet.
- A para sport class is health information (special-category data under GDPR). Publishing it in
  a searchable profile is a different purpose from the provider's results page.
- Anything once published may be cached or indexed elsewhere. Switching back stops serving it,
  but does not recall copies.

## Removal and correction requests (implemented 2026-11-13)
`scout privacy withhold <player> --reason "<who asked, why>"` acts on a removal request:
- the player has no profile (same 404 as an unknown id) and no search hits;
- the name shows as "Name withheld", with no link, in other people's matches;
- the player is left out of opponents lists.

Their matches stay, so opponents' records remain correct. `scout privacy restore` undoes it.
Both are recorded in `privacy_action` (who, when, why), and both act on the canonical player and
everyone merged into it. A correction to a result is made at the source; the next sync picks up
the new revision (ADR-0005).

## Privacy review, 2026-11-13 (global expansion)
What is exposed for every player: name, the events and rounds they played, results and scores,
tournament, date and place. Not exposed: member IDs, clubs, birth dates, contact details,
nationality. What the junior and para policy adds:
- **Minors.** Children's names and results are published (Australia: APP 3/6 and the Children's
  Online Privacy Code in preparation; New Zealand: Privacy Act 2020 IPP 11; EU/UK: GDPR Art. 8
  and the age-appropriate design code; Brazil: LGPD Art. 14 requires the child's best interest).
  The source publishes the same results; republishing them in a searchable, aggregated profile is
  a new purpose. The owner accepts this (above).
- **Para classes.** An event name like "MS SL3" reveals a sport class, which is health data
  (GDPR Art. 9 special category; sensitive information under the Australian Privacy Act).
- **Not in place:** per-source restrictions. One policy covers every federation, as the owner
  decided. If a federation's terms or a regulator require otherwise, the hiding path (this ADR's
  constant plus `reclassify`) and per-player withholding are the tools available today.
  Per-source rules would be a small addition to `privacy.is_redistributable_event`.

## Follow-ups recommended before a public deployment
- A public contact address for removal requests, answered with the withhold command above.
- `noindex` for profiles of players seen only in junior events.
- Legal review of the basis for publishing minors' and health data in each country served.
