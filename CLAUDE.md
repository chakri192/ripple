# Ripple — build notes for Claude Code

You are helping build **Ripple**, a data-incident triage agent for the DataHub
Agent Hackathon (track: *Agents That Do Real Work*). Deadline: **Aug 10, 2026**.

## Context you have

- A local DataHub Core instance is running at `http://localhost:8080` (UI on `:9002`,
  user/pass `datahub`/`datahub`) with the `showcase-ecommerce` sample data loaded.
- The **DataHub MCP server is connected to this Claude Code session** as `datahub`
  (tools: `search`, `get_entities`, `get_lineage`, `add_tags`, `save_document`, ...).
  Use it to explore the real graph and to validate the SDK/GraphQL calls in
  `ripple/datahub_client.py`.

## What to do next (priority order)

1. **Make `datahub_client.downstream_lineage` actually work** against this instance.
   Cross-check the GraphQL field names using the MCP `get_lineage` tool and the
   GraphiQL explorer at `http://localhost:8080/api/graphiql`. Fix response parsing.
2. **Make the write-back work.** Verify `tag_asset` and `save_runbook`. If the
   GraphQL mutations are awkward, switch to emitting aspects via the SDK, or drive
   the MCP `add_tags` / `save_document` tools. Confirm the tag + runbook show up in
   the UI on the target asset.
3. **Run the golden-path demo** end to end on `order_history` and capture the output
   into `examples/` (replace the sample with a real generated run).
4. **Tighten criticality ranking** — pull real usage stats / tags to decide
   `is_customer_facing` instead of the type-based heuristic.
5. **Polish for judging:** keep the README's criteria table accurate, record a
   <3 min demo video, and prep the Skill as a PR to DataHub's Agent Skills repo.

## New features to validate against the live instance

These were added on top of the working core; each needs a quick check against
your DataHub version (field/class names can drift):

1. **root-cause mode** — `python -m ripple root-cause "<downstream-urn>"` should
   list upstream suspects. Uses the same searchAcrossLineage path as triage, so
   high confidence.
2. **column-level lineage** — re-seed (`python demo/seed_incident_demo.py`, which
   now also emits schema + fine-grained lineage), then
   `python -m ripple triage "<source-urn>" --columns`. If the column table is
   empty, verify `column_paths()` parses `fineGrainedLineages` correctly.
3. **native Incident entity** — `... triage "<urn>" --incident`. If it prints
   "skipped", the `IncidentInfoClass` field names differ in your version — check
   with `python -c "import datahub.metadata.schema_classes as s; help(s.IncidentInfoClass)"`
   and adjust `raise_incident()`.
4. **watch** — tag a dataset `broken` in the UI, then `python -m ripple watch
   --once`. Confirm `find_broken_assets()` returns it (the `get_urns_by_filter`
   filter syntax is the thing to verify).

## Guardrails

- Never hardcode the token — it's read from `.env` (`DATAHUB_GMS_TOKEN`).
- Keep the LLM out of the fact-gathering path; it only writes the narrative. This is
  what keeps the demo reproducible for judges.
- Every catalog write must be intentional and visible in the demo.

## Judging criteria to optimise for

Use of DataHub (read **and** write back) · Technical execution (works end-to-end) ·
Originality (extends the platform via a reusable Skill, doesn't re-skin the UI) ·
Real-world usefulness · Submission quality · **Bonus: OSS contribution to DataHub.**
