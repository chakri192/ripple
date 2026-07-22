---
name: incident-triage
description: >
  Triage a broken or degraded data asset in DataHub. Traces the downstream blast
  radius across all lineage hops, resolves owners, ranks by criticality, writes a
  structured incident report, and records the incident back into the catalog
  (tag + runbook document). Use when a table, view, dashboard, or model has broken,
  is producing bad data, or is about to be changed and you need to know what and
  who is affected.
---

# Incident Triage Skill

A reusable DataHub Agent Skill that turns "this asset broke" into an actionable,
persisted incident. Works with any MCP client connected to the DataHub MCP Server
(Claude Code, Cursor, etc.). Read-only tools do the investigation; mutation tools
persist the result.

## When to use

Trigger this skill when the user says any of:
- "X broke / is failing / has bad data — what's affected?"
- "What breaks if I change / drop / rename X?"
- "Who owns the things downstream of X?"
- "Open an incident for X."

## Inputs

- `target`: the URN (or a name to search for) of the broken/at-risk asset.

## Procedure

1. **Resolve the target.** If given a name rather than a URN, call `search` to find
   the matching entity and confirm with the user if ambiguous.

2. **Trace the blast radius.** Call `get_lineage` with `direction: DOWNSTREAM` and a
   generous hop count. Collect every downstream dataset, dashboard, chart, and model.

3. **Enrich.** For the affected entities, call `get_entities` to pull ownership,
   domains, glossary terms, and any usage signals. Flag customer-facing surfaces
   (dashboards/charts) and production-owned tables as high priority.

4. **Rank.** Order the blast radius by criticality: customer-facing first, then
   owned production assets, then everything else, with closer hops ranked higher.

5. **Report.** Produce a concise Markdown incident report:
   - one-line summary of scope (N assets, M customer-facing, owners to page),
   - a ranked impact table,
   - a short recommended-actions checklist.

6. **Persist (write-back).** Using the mutation tools, and **confirming with the user
   before each write**:
   - `add_tags` — apply the `incident` tag to the broken asset.
   - `save_document` — save the incident report as a runbook document linked to the
     asset, so the next engineer or agent inherits full context.
   - Optionally `update_description` to note the active incident inline.

## Guardrails

- Never write to the catalog without surfacing exactly what will change and getting
  a confirmation.
- Treat lineage as potentially incomplete; state assumptions in the report.
- Prefer proposals over direct writes in governed environments
  (`propose_*` tools) when the user isn't an owner.

## Example

> User: order_history just started returning nulls — what's affected?

The agent searches for `order_history`, traces downstream to 14 assets across
Snowflake / dbt / Looker / PowerBI / Tableau, flags 3 customer-facing dashboards,
lists the 6 owners to page, writes the report, tags the asset `incident`, and saves
a runbook document — all in one turn.

---

*This skill is part of the [Ripple](https://github.com/) project, built for the
DataHub Agent Hackathon, and is intended for contribution to the DataHub open-source
Agent Skills ecosystem.*
