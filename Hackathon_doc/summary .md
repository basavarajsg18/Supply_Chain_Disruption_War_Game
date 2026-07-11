# Project Summary — Supply Chain Disruption War Game

## The problem

Supply chain teams make high-stakes trade-off calls — which supplier to
lean on, which route to take, how much safety stock to hold — under
conditions that shift constantly: a port strike here, a demand spike
there, a supplier going dark without warning. Most SCM software isn't
built to reason through that in the moment. It's a **pipeline**: data
flows in, a fixed rule or a trained model scores it, a dashboard turns
red, and a human has to translate that flag into an actual decision. The
intelligence lives in the person reading the dashboard, not the system
itself. Training people to make good calls under that pressure — or
demonstrating how an AI system *should* reason through it — is hard to do
with a static slide deck. You need something that reacts the way the real
thing does.

## What we built

A live, multi-agent simulation of a small but complete supply chain — two
suppliers, a logistics/routing layer, one central warehouse, and three
retail demand points — where a presenter (or any user) can inject a real
disruption **mid-conversation**, in plain language, and watch a mesh of
specialist AI agents detect it, reason about the trade-offs, and
recommend a response entirely on their own — no human pre-translating the
disruption into a form the system understands. Alongside the chat
interface, we built a live web dashboard so the same simulation can be
watched and operated visually, with real-time sync in both directions.

## What makes this agentic, not just "an LLM with a UI"

This isn't a linear pipeline where each agent does its stage of work and
hands off to the next — a conveyor belt with a fixed direction. Each node
in the chain has its **own objective**, and those objectives don't always
agree: `SupplierRelationsManager` is watching supplier lead times and
reliability, `LogisticsPlanner` wants to minimize cost and distance,
`WarehouseOperations` is trying to avoid both stockouts and overstock,
`DemandForecastingUnit` is reading what retail demand is actually doing.
When a disruption hits, these aren't independent reports filed in
sequence — the `Coordinator` has to weigh genuinely competing pulls
(cheaper vs. faster vs. safer) against each other and commit to one
trade-off call, the same way a human ops team would argue it out in a
room.

The bar we held ourselves to: there should be no pre-written answer for
any given disruption. Tell it "Supplier B just went offline and demand at
Retail West spiked 2.5x, optimize for speed," and nobody scripted a
response for that exact combination — Logistics has to compare live
route cost/speed/risk numbers, Warehouse has to recompute days-of-supply
against the new demand figure, and the Coordinator has to resolve the
tension between those specialists into a single justified answer. Change
the disruption and the recommendation changes with it, because every
answer is derived from live tool output in that moment, not retrieved
from a lookup table. This is built on `neuro-san-studio`'s
Agents-as-Orchestrated-Sub-Agents (AAOSA) pattern.

**Real tools, not hallucinated numbers.** Every agent's factual claim —
inventory levels, shipping costs, supplier status — comes from a Python
"coded tool" querying a shared, live database. The LLM's job is to reason
over facts a tool actually returned, never to invent them.

## Where the pipeline analogy breaks down further: state

A classic SCM report is a snapshot — stale the moment conditions change.
Here, disruptions **compound**. We rebuilt the project's original
in-memory prototype state into a real **SQLite** database (WAL mode, safe
for concurrent readers/writers), so state survives restarts and — more
importantly — is shared live between the agent server and the dashboard
as two separate processes watching the same file. Inject a disruption
from the dashboard and the agents see it on their very next tool call;
change something in chat and the dashboard reflects it within seconds. We
deliberately kept every original tool function's signature and return
shape identical during this migration, so it required zero changes to
four of the five original coded tools.

**New simulation depth.** Two new capabilities push disruptions from
cosmetic flags into real, compounding consequences: `AdjustInventoryTool`,
a fully audited way to add or remove real stock (shipments, damage
write-offs, corrections), and `RunWeeklyReplenishmentTool`, which
simulates a week passing — every online supplier ships its full weekly
capacity into the warehouse, an offline supplier contributes nothing, and
the total is capped at warehouse capacity with overflow explicitly
reported rather than silently absorbed. That's what turns a
`supplier_offline` disruption into something that actually gets worse
over multiple turns instead of a status flag that just sits there.

## A live control-room dashboard

A standalone Flask app renders a dark, data-dense "war room" view: live
warehouse stock with a capacity bar and days-of-supply, supplier and
route health tables, retail demand, an active-disruptions list with
one-click resolve, a full event log, and controls to inject disruptions
or adjust stock directly — all reading and writing the exact same
database the chat agents use. It's a second window into one live system,
not a separate mock of it.

## Results / what we validated

- End-to-end disruption injection → multi-agent reasoning → coordinated
  recommendation, tested across all three disruption types (port strike,
  supplier offline, demand spike), individually and stacked together.
- Bidirectional live sync verified: dashboard → chat and chat →
  dashboard, both reflected within the dashboard's 3-second poll cycle.
- Weekly replenishment logic verified against edge cases: a fully healthy
  week (8,000 units/week combined capacity), a degraded week (one
  supplier offline, capacity drops to 3,000/week), and a
  warehouse-at-capacity overflow case (excess correctly reported as lost,
  never silently discarded or overfilled).
- Persistence verified across a full server restart — state is no longer
  lost when the process stops.

## What's next

Per-SKU inventory instead of one warehouse total, a scheduler that
auto-advances "weeks" instead of requiring a manual trigger, and swapping
SQLite for a hosted database to support multiple concurrent games — none
of which require touching a single agent definition, because of how
cleanly the persistence layer is separated from the agent/tool layer.
That separation is the whole bet: the reasoning layer shouldn't have to
change just because the world it's reasoning about gets bigger.
