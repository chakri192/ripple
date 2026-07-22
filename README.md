<img src="assets/ripple-logo.svg" alt="Ripple" height="72"/>

# Ripple — the data-incident triage agent for DataHub

> An AI agent that turns "a table just broke" into a full blast-radius report,
> notifies the right owners, and writes the incident back into DataHub — so the
> next person (or agent) inherits the knowledge instead of starting from zero.

**Built for [Build with DataHub: The Agent Hackathon](https://datahub.devpost.com/).**
Track: *Agents That Do Real Work.*

---

## The problem

A production table breaks at 3am. An on-call engineer now has to answer, by hand:

- What downstream tables, dashboards, and ML models are affected?
- Who owns each of them, and who do I page?
- Which of those are customer-facing right now?
- Where do I write this down so nobody re-investigates it tomorrow?

That's 30–60 minutes of frantic clicking through lineage graphs. Ripple does it
in one command — and, crucially, **records the result back into the catalog** so the
knowledge compounds instead of evaporating.

## What Ripple does

Given a single broken asset (URN), Ripple:

1. **Reads context** — traverses downstream lineage across every hop (Snowflake → dbt →
   Looker / PowerBI / Tableau), pulls ownership, domains, glossary terms, and usage
   signals, all through the DataHub MCP Server.
2. **Reasons** — ranks the blast radius by criticality (customer-facing dashboards and
   owned production tables first) and drafts a human-readable incident report.
3. **Acts + writes back** — applies a `deprecated`/`incident` tag to the broken asset,
   attaches a structured incident record, and saves a runbook document into DataHub so
   the next engineer or agent inherits full context.

The whole read → reason → write loop is packaged as a reusable **DataHub Agent Skill**
(`skills/incident-triage/`) that any MCP-compatible client can run — and that we're
contributing back to the open-source DataHub Skills ecosystem.

## Demo (90 seconds)

```
$ python -m ripple triage \
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_history,PROD)"

◉  Ripple — incident triage
→ Tracing downstream lineage ............ 14 affected assets across 4 platforms
→ Resolving owners ..................... 6 owners, 2 teams
→ Ranking by criticality .............. 3 customer-facing dashboards flagged
→ Writing incident record to DataHub .. ✓ tagged + runbook saved
→ Report: examples/incident_order_history.md
```

Then refresh the asset in the DataHub UI (http://localhost:9002) — the `incident` tag
and the generated runbook are now attached to the graph.

## How it maps to the judging criteria

| Criterion | How Ripple addresses it |
|---|---|
| **Use of DataHub** | Reads lineage/ownership/usage via the MCP Server **and** writes tags, incident records, and runbook docs back to the graph. Full read→act→write loop, not just queries. |
| **Technical execution** | Deterministic lineage traversal + owner resolution via the DataHub SDK; LLM used only for the narrative. Works end-to-end against a local quickstart instance. |
| **Originality** | Doesn't re-skin DataHub's lineage UI — it composes lineage + ownership + usage into an autonomous triage workflow and **ships it as a reusable Agent Skill**, extending the platform rather than rebuilding it. |
| **Real-world usefulness** | Every data team runs incident triage manually today. Ripple turns an hour of on-call clicking into one command, and makes the result persist. |
| **Submission quality** | Clean before/after demo, structured README, documented Skill, sample outputs in `examples/`. |
| **Bonus: OSS contribution** | The `incident-triage` Skill is designed to be contributed to DataHub's [Agent Skills repo](https://docs.datahub.com/docs/dev-guides/agent-context/skills). |

## Architecture

```
                ┌─────────────────────────────┐
   broken URN → │          Ripple           │
                │  ┌───────────────────────┐  │
                │  │ 1. read  (lineage,     │  │  ── MCP / SDK ──▶  DataHub GMS
                │  │    owners, usage)      │  │                    (localhost:8080)
                │  ├───────────────────────┤  │
                │  │ 2. reason (rank +      │  │  ── LLM ──▶  Claude / Gemini
                │  │    narrative report)   │  │
                │  ├───────────────────────┤  │
                │  │ 3. write (tag +        │  │  ── MCP / SDK ──▶  DataHub GMS
                │  │    incident + runbook) │  │
                │  └───────────────────────┘  │
                └─────────────────────────────┘
                             │
                             ▼
                 examples/incident_*.md  +  updated catalog
```

## Setup

Requires a running DataHub instance (local quickstart is fine) and Python 3.10+.

```bash
# 1. install deps
uv venv && source .venv/bin/activate      # or: python3 -m venv .venv && source .venv/bin/activate
uv pip install -e .                        # or: pip install -e .

# 2. point Ripple at your DataHub
cp .env.example .env
# edit .env: DATAHUB_GMS_URL + DATAHUB_GMS_TOKEN (grab the token from ~/.datahubenv)

# 3. run a triage
python -m ripple triage "<dataset-urn>"
```

To run Ripple as a **Skill inside Claude Code** instead of the CLI, see
[`skills/incident-triage/SKILL.md`](skills/incident-triage/SKILL.md).

## Commands

```bash
# Downstream impact triage (write-back on by default)
python -m ripple triage "<urn>"

# ...report only, no catalog writes
python -m ripple triage "<urn>" --no-write-back

# ...also trace column-level lineage and raise a native Incident entity
python -m ripple triage "<urn>" --columns --incident

# Root-cause: trace UPSTREAM to rank the likely sources of bad data
python -m ripple root-cause "<urn>"

# Auto-trigger: poll for broken assets and triage them automatically
python -m ripple watch --interval 15

# Web dashboard: interactive lineage graph + ranked impact (read-only)
python -m ripple web        # then open http://localhost:8000
```

The CLI renders a rich terminal view (severity banner, lineage tree, ranked
table). The `web` command serves a browser dashboard where you paste a URN and
watch the blast radius light up as an interactive graph — the read-only endpoint
never touches the catalog, so it's safe to demo live.

For the demo graph, seed it first with `python demo/seed_incident_demo.py`, then
use the source URN it prints. To see `watch` fire, tag any dataset `broken` in
the DataHub UI and it'll be picked up on the next poll.

## Roadmap

Ripple's core loop (read lineage → reason → write back) is complete. Planned
extensions, in priority order:

**Near term**
- **Assertion-driven triggering** — replace the tag-based `watch` detector with a
  subscription to DataHub Assertion-failure events, so triage fires the moment a
  data-quality check fails.
- **Impact quantification** — use DataHub usage stats and query history to report
  *how many* queries and users are affected, not just how many assets.
- **Severity classification** — derive an incident severity (SEV1–3) from the
  blast radius and drive escalation off it.

**Product**
- **Auto-remediation PRs** — when a schema change breaks a downstream model,
  generate the fix and open a GitHub pull request.
- **Notifications & routing** — page identified owners via Slack / PagerDuty and
  draft stakeholder comms automatically.
- **Pre-incident change simulation** — "what breaks if I drop table X?" as a
  CI/CD gate that blocks PRs which would break customer-facing surfaces.
- **ML asset support** — extend triage to ML models/features via DataHub's
  end-to-end ML lineage.

**Platform**
- **Multi-agent** — separate detector / triage / remediation agents coordinating
  through DataHub as shared memory.
- **Incident memory** — learn from past incidents to improve ranking and suggest
  proven fixes.
- **Slack-native interface** — run the whole workflow from a Slack thread.
- **Governance layer** — human-in-the-loop approvals, proposal-workflow writes,
  and a full audit log of agent actions.

## Repository layout

```
ripple/
├── ripple/                 # the agent
│   ├── __main__.py           # CLI entrypoint (python -m ripple ...)
│   ├── config.py             # env / connection config
│   ├── datahub_client.py     # thin DataHub read/write wrapper (lineage, owners, write-back)
│   ├── triage.py             # orchestration: read → reason → write
│   └── report.py             # narrative report generation
├── skills/incident-triage/   # the reusable DataHub Agent Skill (the OSS contribution)
│   └── SKILL.md
├── examples/                 # sample generated incident reports (for judges)
├── .env.example
├── pyproject.toml
├── LICENSE                   # Apache-2.0
└── README.md
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
