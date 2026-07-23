---
name: incident-triage
description: >
  Triage a broken or degraded data asset in DataHub. Traces the downstream blast
  radius across all lineage hops, resolves owners, ranks by criticality, writes a
  structured incident report, and records the incident back into the catalog
  (tag + runbook document + native incident). Use when a table, view, dashboard,
  or model has broken, is producing bad data, or is about to be changed and you
  need to know what and who is affected.
---

# Incident Triage Skill

A reusable DataHub Agent Skill that turns "this asset broke" into an actionable,
persisted incident. It works with any MCP client connected to the DataHub MCP
Server. Read-only tools do the investigation; mutation tools persist the result.

The split is deliberate: **lineage traversal, owner resolution, and ranking are
deterministic** — same input, same output, every run. A model is only used to
write the human-readable narrative. Nothing about *what* is affected is generated
by a model, which is what makes the result safe to act on.

## When to use

Trigger this skill when the user says any of:
- "X broke / is failing / has bad data — what's affected?"
- "What breaks if I change / drop / rename X?"
- "Who owns the things downstream of X?"
- "Open an incident for X."

## Inputs

- `target` — the URN (or a name to search for) of the broken / at-risk asset.

## Procedure

1. **Resolve the target.** If given a name rather than a URN, call `search` to
   find the matching entity; confirm with the user if ambiguous.

2. **Trace the blast radius.** Call `get_lineage` with `direction: DOWNSTREAM` and
   a generous hop count. Collect every downstream dataset, dashboard, chart, and
   model, keeping each entity's hop distance (degree) from the source.

3. **Enrich.** For the affected entities, call `get_entities` to pull ownership,
   platform, domains, and glossary terms. Flag customer-facing surfaces
   (dashboards / charts) and owned production tables as high priority.

4. **Rank.** Order the blast radius by criticality: customer-facing first, then
   owned production assets, then everything else, with closer hops ranked higher.
   A simple, transparent scoring function keeps the ranking reproducible.

5. **Report.** Produce a concise Markdown incident report:
   - a one-line summary of scope (N assets, M customer-facing, owners to page),
   - a ranked impact table (asset · platform · type · hops · owners),
   - a short recommended-actions checklist.

6. **Persist (write-back).** Using the mutation tools, and **confirming with the
   user before each write**:
   - `add_tags` — apply the `incident` tag to the broken asset.
   - `save_document` / `update_description` — save the incident report as a
     runbook on the asset, so the next engineer or agent inherits full context.
   - `raise_incident` (native Incident entity) — where the DataHub version and MCP
     server support it, so the incident shows on the asset's Incidents tab.

## Guardrails

- Never write to the catalog without surfacing exactly what will change and
  getting a confirmation for each write.
- Treat lineage as potentially incomplete; state assumptions in the report.
- Prefer proposals over direct writes in governed environments (`propose_*`
  tools) when the user is not an owner of the asset.
- Column-level and native-incident steps are best-effort: if the instance does
  not expose fine-grained lineage or the incident aspect, degrade to the
  tag + runbook write-back rather than failing the whole triage.

## Known DataHub gotchas

These are documented from building against a live DataHub instance; see
[`docs/known-issues.md`](../../docs/known-issues.md) for full reproductions.

- **Dashboards/charts appear in `searchAcrossLineage` as downstream, but the
  dataset→dashboard edge is not in `UpstreamLineage`.** Reconstruct those edges
  from `DashboardInfo` / `ChartInfo` inputs when you need a connected graph.
- **A native Incident (`IncidentInfo`) emitted on its own URN does not always
  surface on the asset's Incidents tab.** Confirm the incident schema for your
  running version before relying on it; keep the tag + runbook path as fallback.
- **Filtering datasets by tag via `get_urns_by_filter` is field-name sensitive**
  (`tags` vs `tags.keyword`) and can throw rather than return empty. Wrap it.

## Example

> User: order_history just started returning nulls — what's affected?

The agent searches for `order_history`, traces downstream to assets across
Snowflake / dbt / Looker / PowerBI / Tableau, flags the customer-facing
dashboards, lists the owners to page, writes the report, tags the asset
`incident`, and saves a runbook document — in one turn.

---

*This skill is extracted from the [Ripple](https://github.com/chakri192/ripple)
project, built for the DataHub Agent Hackathon, and is intended for contribution
to the DataHub open-source Agent Skills ecosystem.*
