# vps-stock-opencli

Standalone, read-only VPS inventory monitoring. The default checks ByteVirt's
Japan ISP and Los Angeles CN2 GIA product families, ByteVirt PID 329's annual
offer, the Japan 512 MB ISP prepaid offer (PID 324), and YINNET Singapore VPS ①. The executable lives at
`tools/vps_stock.py`; it never logs in, adds a product to a cart, submits an
order, or changes a server.

Run it from the repository root:

```bash
python3 tools/vps_stock.py
```

The default target-mode state file is
`~/.cache/vps-stock-opencli/vps-stock-targets.json`, separate from the historic
`vps-stock.json`. Override it with `--state-file` when needed. The default
monitor reports only new availability transitions and source errors.

The first successful run creates a baseline and does not notify existing stock.
Later transport and parser failures are written to `<state>.last-run.json` but
do not overwrite the last valid source state. State, previous state, and
run-report files are replaced atomically; webhook events use a persisted
pending record and deterministic idempotency key until delivery. Each source
establishes its own baseline: a source whose first attempt fails is stored as
`unobserved`, and its first later success does not produce a false restock
notification. After a valid ByteVirt catalog baseline, a newly listed eligible
SKU already in stock also triggers a notification. Failed attempts on previously valid sources are attached as
`last_attempt` while the last valid status remains available for comparison.

## State ownership

The executable owns only the explicit state path and its adjacent artifacts:
`<state>.prev`, `<state>.last-run.json`, and
`<state>.pending-notification.json`. It does not write Codex, Claude, or other
automation memory and does not depend on an automation ID.

If a scheduler wants a concise run history, the scheduler or its Agent writes
that history in its own task-scoped memory after parsing stdout. This keeps the
monitor reusable from cron, CI, Codex, or a terminal without hidden side effects.

ByteVirt uses its public catalog JSON to validate SKU identity, route,
dedicated IPv4, inventory consistency, displayed currency, and price amount.
Eligible monthly offers must be USD $15 or less. PID 329's annual offer is
tracked separately with a $66 ceiling. Japan ISP PID 324
has one shared restock alert for its prepaid terms, prioritizing the shortest
qualifying term: $25 per quarter, $40 per half-year, or $69 per year.
Other over-budget and non-monthly offers use
the persisted `ineligible` state, so they do not degrade a normal run and a
later return to budget can still produce a restock transition. Malformed
catalog data remains `unknown` and preserves the last valid status. Use
`--bytevirt-only` to check these ByteVirt targets without requesting YINNET.

YINNET is read from its public Singapore VPS listing and tracks VPS ① only.
The parser requires an exact product link, monthly USD price, and a consistent
stock signal. Route performance is not inferred from the listing.

## Legacy source set

Use `--legacy` to run the historic wider provider and discovery sources; this
mode uses the previous `~/.cache/vps-stock-opencli/vps-stock.json` state file.
For backward compatibility, `--all`, `--cn2-only`, and `--no-social` also
select legacy mode when supplied without `--legacy`. An explicit
`--state-file` is used as given in either mode. Plain `--monitorability` shows
the current targets; `--legacy --monitorability` prints the historic matrix.

The legacy source order is official provider pages, Exa web discovery, named
provider X/Reddit leads, and generic X/Reddit discovery. Exa is a web-search
lead source, not an inventory authority: results are kept only when they are
within the three-day window and contain eligible price plus concrete VPS
evidence, then still require official verification. Configure it locally with:

```bash
mcporter config add exa https://mcp.exa.ai/mcp
```

If Exa is unavailable, legacy mode reports the exception and continues with
the remaining sources. In legacy mode, `--no-social` skips Exa and X/Reddit
discovery and keeps only official sources.

Legacy ByteVirt checks use the fixed `VPS-1024-KVM-ISP-JP` and
`VPS-1024-KVM-CN2 GIA LA` SKUs. A non-USD currency, price over $15/month, or
removal of the monthly cycle is recorded as `offer_changed` in legacy mode.
Conflicting currency fields or malformed catalog data remain `unknown` and
preserve the last valid state. The public catalog's orderability flag is not a
guarantee of successful provisioning.

X and Reddit discovery use `opencli` when available. Both `opencli` and
`mcporter` are optional integrations: a missing command is reported as a source
exception and does not disable official-source checks.

The legacy overall source-check budget is 300 seconds (`--run-timeout`).
Legacy official pages are checked first, duplicate official URLs share one
response, and transient transport/5xx failures receive one retry. A Twitter/X 429 opens
a per-run circuit breaker so later X searches are skipped without erasing
their previous successful state. Set `--run-timeout 0` only when an unbounded
manual run is intentional.

The official matrix includes the ZgoVPS Los Angeles AMD Optimised Starter at
`$18/quarter` (`$6/month` equivalent), tracked separately from the `$52/year`
special-offer page.
It also includes DediOne `LAX.VPS.CMIN2.1C1G10G-Annual` at `$29.99/year`; the
official product card exposes an order action but no numeric inventory count.
YT.NET's [Los Angeles deployment page](https://cloud.yt.net/deploy/us-lax) is
tracked as two independent CNY monthly sources: `US.LAX.A` at `¥22/month` and
`US.LAX.B` at `¥35/month`. The monitor reads each plan card separately and uses
the page's `缺货` label as an orderability signal. If either configured offer
keeps the plan name but changes price, it reports `offer_changed` with the
observed prices instead of treating the page as unreachable. It does not claim
a numeric inventory count or convert the CNY prices to the USD budget
threshold. The page's `US.LAX.C` tier is not included in this monitor.
ZoroCloud's [Japan residential BGP page](https://my.zorocloud.com/store/jpisp)
is also tracked for the requested `JP-Titan-Plus` plan at `¥138/month`. The
monitor uses a numeric `可用` count when published and otherwise falls back to
the enabled/disabled order action at medium confidence. Its CNY price is
tracked as a user-requested source and is not treated as within the monitor's
default USD value filter.

LightLayer keeps its whole catalog behind an account login, so its two Los
Angeles annual plans use the `manual` source kind: the monitor never fetches
them and reports the specs and price verified by hand, plus how old that
snapshot is. Past `stale_after_days` (30 by default) the source turns
`unknown`, surfacing as an exception that prompts a re-check.

- `lightlayer-lax-vp01-a-annual` — `LA-VP01-A`, `$24.99/year`, Premium line,
  20Mbps unmetered, 50GB NVMe, native IPv4
- `lightlayer-lax-vp04-l-a-annual` — `LA-VP04-L-A`, `$49.99/year`, Premium
  line, 1Gbps at 1TB/month, 50GB NVMe, native IPv4

Premium means CN2 for China Telecom and CMIN2 for China Unicom and Mobile.
Both promo plans are non-upgradeable and non-refundable. Re-verify at the URL
recorded on each source and bump `verified_on` when the snapshot changes.

Validation for monitor changes:

```bash
python3 -m py_compile tools/vps_stock.py
python3 -m unittest tests.test_vps_stock
```

This repository was extracted from
[`mtmtian/Network-Node`](https://github.com/mtmtian/Network-Node) at commit
`8b6433a` so the monitor can evolve without proxy deployment or Mihomo routing
changes sharing the same branch.
