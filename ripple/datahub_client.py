"""DataHub read/write wrapper used by the Ripple agent.

Reads (lineage, owners, columns, failing assets) and writes (tags, incident
records, runbook docs, native Incident entities) go through the DataHub Python
SDK against your GMS endpoint.

NOTE (for the hackathon build): the newer methods (column lineage, incidents,
failing-asset detection) are working starting points — validate each against
your instance. Any MCP client connected to the DataHub MCP server can confirm
the exact response shapes fast.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.graph.client import DataHubGraph, DataHubGraphConfig
from datahub.metadata.schema_classes import (
    EditableDatasetPropertiesClass,
    GlobalTagsClass,
    TagAssociationClass,
    TagPropertiesClass,
    UpstreamLineageClass,
)

from .config import Config

# searchAcrossLineage query, parametrised by direction (UPSTREAM | DOWNSTREAM)
_LINEAGE_QUERY = """
query lineage($urn: String!, $dir: LineageDirection!, $count: Int!) {
  searchAcrossLineage(
    input: { urn: $urn, direction: $dir, query: "*", start: 0, count: $count }
  ) {
    searchResults {
      degree
      entity {
        urn
        type
        ... on Dataset {
          name
          platform { name }
          ownership { owners { owner { ... on CorpUser { username } } } }
        }
        ... on Dashboard {
          properties { name }
          platform { name }
          ownership { owners { owner { ... on CorpUser { username } } } }
        }
        ... on Chart {
          properties { name }
          platform { name }
          ownership { owners { owner { ... on CorpUser { username } } } }
        }
      }
    }
  }
}
"""


@dataclass
class AffectedAsset:
    urn: str
    name: str
    platform: str
    entity_type: str
    hops: int
    owners: list[str] = field(default_factory=list)
    is_customer_facing: bool = False

    @property
    def criticality(self) -> int:
        """Rank the downstream blast radius. Higher = more urgent."""
        score = 0
        if self.is_customer_facing:
            score += 100
        if self.entity_type in {"DASHBOARD", "CHART"}:
            score += 50
        if self.owners:
            score += 20
        score += max(0, 10 - self.hops)
        return score

    @property
    def root_cause_likelihood(self) -> int:
        """Rank upstream suspects for root-cause mode. Higher = more likely.

        Closer hops and raw source platforms (where bad data usually enters)
        are the most likely culprits.
        """
        score = max(0, 20 - self.hops * 3)
        if self.platform in {"s3", "kafka", "snowflake"}:
            score += 10  # raw ingestion points
        return score


class DataHubClient:
    def __init__(self, config: Config):
        self.config = config
        self.graph = DataHubGraph(
            DataHubGraphConfig(server=config.gms_url, token=config.gms_token)
        )

    # ------------------------------------------------------------------ reads

    def _lineage(self, urn: str, direction: str) -> list[AffectedAsset]:
        result = self.graph.execute_graphql(
            _LINEAGE_QUERY,
            variables={"urn": urn, "dir": direction, "count": 200},
        )
        rows = result.get("searchAcrossLineage", {}).get("searchResults", []) or []
        assets: list[AffectedAsset] = []
        for row in rows:
            entity = row.get("entity", {}) or {}
            etype = entity.get("type", "UNKNOWN")
            name = (
                entity.get("name")
                or (entity.get("properties") or {}).get("name")
                or entity.get("urn", "").split(",")[-2:][-1]
            )
            platform = ((entity.get("platform") or {}).get("name")) or "unknown"
            owners = [
                (o.get("owner") or {}).get("username")
                for o in ((entity.get("ownership") or {}).get("owners") or [])
                if (o.get("owner") or {}).get("username")
            ]
            assets.append(
                AffectedAsset(
                    urn=entity.get("urn", ""),
                    name=name,
                    platform=platform,
                    entity_type=etype,
                    hops=row.get("degree", 1),
                    owners=owners,
                    is_customer_facing=etype in {"DASHBOARD", "CHART"},
                )
            )
        return assets

    def downstream_lineage(self, urn: str) -> list[AffectedAsset]:
        """Everything downstream of `urn` (the impact / blast radius)."""
        return self._lineage(urn, "DOWNSTREAM")

    def upstream_lineage(self, urn: str) -> list[AffectedAsset]:
        """Everything upstream of `urn` (the root-cause suspects)."""
        return self._lineage(urn, "UPSTREAM")

    def column_paths(
        self, broken_urn: str, downstream: list[AffectedAsset] | None = None
    ) -> list[tuple[str, str, str]]:
        """Best-effort column-level blast radius.

        For each downstream dataset, read its fine-grained (column) lineage and
        return the (downstream_dataset, downstream_column, upstream_column)
        triples that trace back to a column of the broken asset. Requires the
        upstream datasets to carry fineGrainedLineages (the seeder emits these).

        Pass `downstream` to reuse an already-fetched blast radius and avoid a
        second lineage round-trip.
        """
        out: list[tuple[str, str, str]] = []
        assets = downstream if downstream is not None else self.downstream_lineage(
            broken_urn
        )
        for asset in assets:
            if asset.entity_type != "DATASET":
                continue
            up = self.graph.get_aspect(asset.urn, UpstreamLineageClass)
            for fg in (up.fineGrainedLineages if up and up.fineGrainedLineages else []):
                for up_col in fg.upstreams or []:
                    for down_col in fg.downstreams or []:
                        out.append(
                            (asset.name, _col(down_col), _col(up_col))
                        )
        return out

    def blast_graph(
        self, urn: str, downstream: list[AffectedAsset] | None = None
    ) -> dict:
        """Return {nodes, edges} describing the downstream blast radius as a
        graph, for visualisation. Reconstructs real dataset->dataset edges from
        UpstreamLineage where available; falls back to linking from the source
        so every affected node stays connected.

        Pass `downstream` to reuse an already-fetched blast radius and avoid a
        second lineage round-trip (the web endpoint does this).
        """
        assets = downstream if downstream is not None else self.downstream_lineage(urn)
        node_urns = {urn} | {a.urn for a in assets}
        src_name = urn.split(",")[-2] if "," in urn else urn
        src_plat = (
            urn.split("dataPlatform:")[1].split(",")[0]
            if "dataPlatform:" in urn
            else "source"
        )
        nodes = [
            {
                "id": urn,
                "label": src_name,
                "kind": "SOURCE",
                "cf": False,
                "platform": src_plat,
                "level": 0,
            }
        ]
        for a in assets:
            nodes.append(
                {
                    "id": a.urn,
                    "label": a.name,
                    "kind": a.entity_type,
                    "cf": a.is_customer_facing,
                    "platform": a.platform,
                    "level": a.hops,
                }
            )
        edges: list[dict] = []
        for a in assets:
            parents: list[str] = []
            if a.entity_type == "DATASET":
                up = self.graph.get_aspect(a.urn, UpstreamLineageClass)
                if up and up.upstreams:
                    parents = [
                        u.dataset for u in up.upstreams if u.dataset in node_urns
                    ]
            elif a.entity_type in {"DASHBOARD", "CHART"}:
                # dashboards/charts consume datasets via DashboardInfo/ChartInfo,
                # not UpstreamLineage — reconstruct those edges too
                parents = self._consumed_datasets(
                    a.urn, a.entity_type, node_urns
                )
            if not parents:
                parents = [urn]  # keep the node connected to the blast source
            for p in parents:
                edges.append({"from": p, "to": a.urn})
        return {"nodes": nodes, "edges": edges}

    def _consumed_datasets(
        self, urn: str, etype: str, node_urns: set
    ) -> list[str]:
        """Datasets a dashboard/chart reads from (for graph edges)."""
        try:
            if etype == "DASHBOARD":
                from datahub.metadata.schema_classes import DashboardInfoClass

                info = self.graph.get_aspect(urn, DashboardInfoClass)
            else:
                from datahub.metadata.schema_classes import ChartInfoClass

                info = self.graph.get_aspect(urn, ChartInfoClass)
            if not info:
                return []
            ds: list[str] = list(getattr(info, "datasets", None) or [])
            ds += list(getattr(info, "inputs", None) or [])
            for e in getattr(info, "datasetEdges", None) or []:
                ds.append(e.destinationUrn)
            for e in getattr(info, "inputEdges", None) or []:
                ds.append(e.destinationUrn)
            return [d for d in ds if d in node_urns]
        except Exception:
            return []

    def find_broken_assets(self, tag: str = "broken") -> list[str]:
        """Auto-trigger detector: URNs of datasets flagged as broken.

        Demo path: polls for datasets carrying the `broken` tag. In production
        you'd instead subscribe to DataHub Assertion-failure events; swap this
        method for that source and the watch loop is unchanged.
        """
        tag_urn = f"urn:li:tag:{tag}"
        try:
            return list(
                self.graph.get_urns_by_filter(
                    entity_types=["dataset"],
                    extraFilters=[
                        {"field": "tags", "condition": "EQUAL", "values": [tag_urn]}
                    ],
                )
            )
        except Exception as exc:  # surface, don't hide — helps diagnose filter issues
            import sys

            print(f"[find_broken_assets] detector error: {exc}", file=sys.stderr)
            return []

    # ----------------------------------------------------------------- writes

    def tag_asset(self, urn: str, tag: str) -> None:
        """Apply a tag to an asset, creating the tag entity first."""
        tag_urn = f"urn:li:tag:{tag}"
        self.graph.emit(
            MetadataChangeProposalWrapper(
                entityUrn=tag_urn, aspect=TagPropertiesClass(name=tag)
            )
        )
        existing = self.graph.get_aspect(urn, GlobalTagsClass)
        tags = list(existing.tags) if existing and existing.tags else []
        if all(t.tag != tag_urn for t in tags):
            tags.append(TagAssociationClass(tag=tag_urn))
        self.graph.emit(
            MetadataChangeProposalWrapper(
                entityUrn=urn, aspect=GlobalTagsClass(tags=tags)
            )
        )

    def save_runbook(self, urn: str, title: str, body_md: str) -> None:
        """Attach the runbook to the asset as editable documentation."""
        self.graph.emit(
            MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=EditableDatasetPropertiesClass(
                    description=f"### {title}\n\n{body_md}"
                ),
            )
        )

    def raise_incident(self, urn: str, title: str, description: str) -> str:
        """Create a native DataHub Incident entity linked to the asset.

        This is the 'first-class' write-back: it shows up under the asset's
        Incidents tab, not just as a tag. Falls back gracefully if the running
        DataHub version's incident schema differs — validate against your
        instance and adjust the aspect fields if needed.
        """
        import uuid

        # lazy import so a schema mismatch can't break the whole module
        from datahub.metadata.schema_classes import (
            AuditStampClass,
            IncidentInfoClass,
            IncidentSourceClass,
            IncidentSourceTypeClass,
            IncidentStateClass,
            IncidentStatusClass,
            IncidentTypeClass,
        )

        incident_urn = f"urn:li:incident:{uuid.uuid4()}"
        now = AuditStampClass(time=0, actor="urn:li:corpuser:ripple")
        info = IncidentInfoClass(
            type=IncidentTypeClass.OPERATIONAL,
            title=title,
            description=description[:500],
            entities=[urn],
            status=IncidentStatusClass(
                state=IncidentStateClass.ACTIVE, lastUpdated=now
            ),
            source=IncidentSourceClass(type=IncidentSourceTypeClass.MANUAL),
            created=now,
        )
        self.graph.emit(
            MetadataChangeProposalWrapper(entityUrn=incident_urn, aspect=info)
        )
        return incident_urn


def _col(field_urn: str) -> str:
    """Pull the column name out of a schemaField URN."""
    return field_urn.rstrip(")").split(",")[-1] if field_urn else field_urn
