# Known DataHub issues found while building Ripple

These were observed building Ripple against a live DataHub instance using the
`acryl-datahub` Python SDK **1.6.0.15** and the DataHub MCP Server. Each block
below is written to be filed as-is on the DataHub issue tracker
(`datahub-project/datahub`). Fill in the exact **GMS / server version** you ran
against before submitting — the SDK version is pinned above.

Ripple works around all three today; they are filed to fix the root cause upstream
so the workarounds can be removed.

---

## Issue 1 — `IncidentInfo` emitted on its own URN does not surface on the asset's Incidents tab

**Type:** bug
**Area:** metadata-service / incidents, GraphQL
**SDK:** acryl-datahub 1.6.0.15 · **GMS:** `<fill in>`

### Summary
Emitting an `IncidentInfo` aspect on a freshly minted `urn:li:incident:*` and
listing the affected dataset in `entities` creates the incident entity, but the
incident does not consistently appear under the linked dataset's **Incidents**
tab in the UI or via the dataset's incident relationships.

### Steps to reproduce
1. Build an `IncidentInfo` aspect with `type=OPERATIONAL`, `status.state=ACTIVE`,
   `source.type=MANUAL`, and `entities=[<dataset_urn>]`.
2. Emit it via `MetadataChangeProposalWrapper(entityUrn="urn:li:incident:<uuid>", aspect=info)`.
3. Open the referenced dataset in the UI → **Incidents** tab.

### Expected
The dataset's Incidents tab lists the new active incident.

### Actual
The incident entity exists (queryable by its own URN) but is not reliably linked
back onto the dataset's Incidents tab; behavior appears to depend on the running
GMS version's incident schema. There is no clear error — the write succeeds.

### Notes / ask
Document the exact aspect(s) required to make an SDK-emitted incident show on the
asset (e.g. whether an `IncidentsSummary` update on the dataset is also required),
or validate `IncidentInfo` on ingest and warn when the link cannot be established.

### Ripple's workaround
`raise_incident()` lazy-imports the incident classes and degrades gracefully;
Ripple always also writes the `incident` tag + runbook so the incident is visible
even when the native entity does not surface. See
`ripple/datahub_client.py::raise_incident`.

---

## Issue 2 — Dataset→dashboard/chart edges are absent from `UpstreamLineage`, so a lineage graph cannot be reconstructed from it alone

**Type:** bug / documentation
**Area:** lineage, GraphQL (`searchAcrossLineage`)
**SDK:** acryl-datahub 1.6.0.15 · **GMS:** `<fill in>`

### Summary
`searchAcrossLineage(direction: DOWNSTREAM)` correctly returns dashboards and
charts as downstream entities of a dataset, but the corresponding dataset→dashboard
edge cannot be recovered from the dashboard's `UpstreamLineage` aspect (dashboards
and charts consume datasets via `DashboardInfo` / `ChartInfo` inputs, not
`UpstreamLineage`). A consumer that reconstructs a graph purely from
`UpstreamLineage` ends up with disconnected dashboard/chart nodes.

### Steps to reproduce
1. `searchAcrossLineage` downstream from a dataset that feeds a dashboard — the
   dashboard is returned in `searchResults`.
2. `get_aspect(dashboard_urn, UpstreamLineageClass)` → empty / no dataset edge.

### Expected
Either the edge is discoverable through a single, consistent lineage aspect, or
the docs make explicit that dashboard/chart input edges live on
`DashboardInfo.datasetEdges` / `ChartInfo.inputEdges` and must be read separately.

### Actual
The edge only exists on `DashboardInfo` / `ChartInfo`; nothing in the lineage
response points a consumer there, so graph reconstruction silently drops edges.

### Ripple's workaround
`blast_graph()` falls back to `_consumed_datasets()`, which reads
`DashboardInfo` / `ChartInfo` (`datasets`, `inputs`, `datasetEdges`, `inputEdges`)
to rebuild the missing edges, and links any still-orphaned node to the blast
source. See `ripple/datahub_client.py::blast_graph` / `_consumed_datasets`.

---

## Issue 3 — `get_urns_by_filter` tag filter is field-name sensitive and throws instead of returning empty

**Type:** bug / dx
**Area:** python SDK (`DataHubGraph.get_urns_by_filter`), search filters
**SDK:** acryl-datahub 1.6.0.15 · **GMS:** `<fill in>`

### Summary
Filtering datasets by tag with `extraFilters=[{"field": "tags", ...}]` is
sensitive to the exact indexed field name (`tags` vs `tags.keyword`) and, on a
mismatch, raises an exception rather than returning an empty result set. This
makes a simple "find all datasets carrying tag X" query fragile.

### Steps to reproduce
```python
graph.get_urns_by_filter(
    entity_types=["dataset"],
    extraFilters=[{"field": "tags", "condition": "EQUAL",
                   "values": ["urn:li:tag:broken"]}],
)
```

### Expected
Returns the URNs of datasets carrying the tag (empty list if none), with a single
documented field name for tag filtering.

### Actual
Depending on the field name used, the call throws; the correct field name is not
obvious from the SDK signature or docs.

### Notes / ask
Document the canonical field name for tag filtering in `get_urns_by_filter`, and/or
accept the tag `urn`/field robustly and return empty on no-match instead of raising.

### Ripple's workaround
`find_broken_assets()` wraps the call in try/except and prints the detector error
to stderr so a filter mismatch is diagnosable rather than fatal. See
`ripple/datahub_client.py::find_broken_assets`.

---

### Filing checklist
- [ ] Confirm each still reproduces on the latest GMS + SDK.
- [ ] Fill in the exact GMS/server version in each block.
- [ ] Attach a minimal repro (the seeder in `demo/` reproduces the graph shape).
- [ ] Cross-link the three issues; #2 and #3 are small, #1 is the substantive one.
