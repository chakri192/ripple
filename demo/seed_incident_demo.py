"""Seed a realistic incident scenario into DataHub for the Ripple demo.

The showcase-ecommerce sample graph has almost no downstream fan-out, which makes
for a weak "blast radius" demo. This script emits a purpose-built slice with a
clear source → transform → BI fan-out and real owners, so:

    python -m ripple triage "<RAW_ORDERS_URN>"

lights up a rich, reproducible blast radius (5 tables + 3 dashboards, 2 of them
customer-facing).

Run it (with your venv active and .env configured):

    python demo/seed_incident_demo.py

It prints the source URN to triage at the end. Idempotent — re-running overwrites.
"""
from __future__ import annotations

import time

from datahub.emitter.mce_builder import (
    make_dashboard_urn,
    make_dataset_urn,
    make_user_urn,
)
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.metadata.schema_classes import (
    AuditStampClass,
    ChangeAuditStampsClass,
    DashboardInfoClass,
    DatasetLineageTypeClass,
    DatasetPropertiesClass,
    OwnerClass,
    OwnershipClass,
    OwnershipTypeClass,
    SubTypesClass,
    UpstreamClass,
    UpstreamLineageClass,
)

# reuse Ripple's connection config so this matches your .env
from ripple.config import Config

ENV = "PROD"
NOW_MS = int(time.time() * 1000)
ACTOR = "urn:li:corpuser:datahub"


def _audit() -> ChangeAuditStampsClass:
    stamp = AuditStampClass(time=NOW_MS, actor=ACTOR)
    return ChangeAuditStampsClass(created=stamp, lastModified=stamp)


def _ownership(*usernames: str) -> OwnershipClass:
    return OwnershipClass(
        owners=[
            OwnerClass(owner=make_user_urn(u), type=OwnershipTypeClass.TECHNICAL_OWNER)
            for u in usernames
        ]
    )


def _dataset(emitter, platform, name, upstreams=None, owners=(), subtype="Table"):
    urn = make_dataset_urn(platform=platform, name=name, env=ENV)
    aspects = [
        DatasetPropertiesClass(name=name.split(".")[-1]),
        SubTypesClass(typeNames=[subtype]),
    ]
    if owners:
        aspects.append(_ownership(*owners))
    if upstreams:
        aspects.append(
            UpstreamLineageClass(
                upstreams=[
                    UpstreamClass(
                        dataset=u, type=DatasetLineageTypeClass.TRANSFORMED
                    )
                    for u in upstreams
                ]
            )
        )
    for aspect in aspects:
        emitter.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))
    return urn


def _dashboard(emitter, platform, name, feeds_from, owners=()):
    urn = make_dashboard_urn(platform=platform, name=name)
    info = DashboardInfoClass(
        title=name,
        description=f"{name} — fed by the order pipeline.",
        lastModified=_audit(),
        datasets=list(feeds_from),  # establishes dataset -> dashboard lineage
        dashboardUrl=f"http://example.com/{platform}/{name}",
    )
    emitter.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=info))
    if owners:
        emitter.emit(
            MetadataChangeProposalWrapper(entityUrn=urn, aspect=_ownership(*owners))
        )
    return urn


def main() -> None:
    cfg = Config.from_env()
    emitter = DatahubRestEmitter(gms_server=cfg.gms_url, token=cfg.gms_token)

    # --- source (the asset that "breaks") ---
    raw_orders = _dataset(
        emitter, "snowflake", "prod.raw.orders_raw", owners=["data-eng"]
    )

    # --- staging + fact (dbt) ---
    stg_orders = _dataset(
        emitter, "dbt", "prod.staging.stg_orders", upstreams=[raw_orders]
    )
    stg_customers = _dataset(
        emitter, "dbt", "prod.staging.stg_customers", upstreams=[raw_orders]
    )
    fct_orders = _dataset(
        emitter,
        "dbt",
        "prod.marts.fct_orders",
        upstreams=[stg_orders, stg_customers],
        owners=["jrivera"],
    )

    # --- aggregates ---
    agg_daily_revenue = _dataset(
        emitter,
        "snowflake",
        "prod.analytics.agg_daily_revenue",
        upstreams=[fct_orders],
        owners=["amanda.lee"],
    )
    agg_regional_sales = _dataset(
        emitter,
        "snowflake",
        "prod.analytics.agg_regional_sales",
        upstreams=[fct_orders],
        owners=["priya.n"],
    )

    # --- BI dashboards (2 customer-facing, 1 internal) ---
    _dashboard(
        emitter,
        "powerbi",
        "Executive Revenue",
        feeds_from=[agg_daily_revenue],
        owners=["amanda.lee"],
    )
    _dashboard(
        emitter,
        "looker",
        "Regional Sales",
        feeds_from=[agg_regional_sales],
        owners=["priya.n"],
    )
    _dashboard(
        emitter,
        "tableau",
        "Ops Monitoring",
        feeds_from=[fct_orders],
        owners=["ops-analytics"],
    )

    # Column-level lineage (best-effort; enables `ripple triage --columns`).
    # Guarded so a schema-class mismatch can never break the base seed above.
    try:
        _seed_columns(emitter, raw_orders, {stg_orders, stg_customers})
        cols_note = "   + column-level lineage for --columns mode.\n"
    except Exception as exc:  # noqa: BLE001
        cols_note = f"   (column-level lineage skipped: {exc})\n"

    print("\n✅ Seeded incident demo graph.")
    print("   5 downstream tables + 3 dashboards (2 customer-facing).")
    print(cols_note)
    print("Triage the source with:\n")
    print(f'   python -m ripple triage "{raw_orders}" --no-write-back\n')


def _seed_columns(emitter, source_urn, direct_children):
    """Give datasets a small schema and wire column-level lineage from source."""
    from datahub.emitter.mce_builder import make_schema_field_urn
    from datahub.metadata.schema_classes import (
        DatasetLineageTypeClass,
        FineGrainedLineageClass,
        FineGrainedLineageDownstreamTypeClass,
        FineGrainedLineageUpstreamTypeClass,
        NumberTypeClass,
        OtherSchemaClass,
        SchemaFieldClass,
        SchemaFieldDataTypeClass,
        SchemaMetadataClass,
        StringTypeClass,
        UpstreamClass,
        UpstreamLineageClass,
    )

    columns = [("order_id", StringTypeClass), ("customer_id", StringTypeClass),
               ("amount", NumberTypeClass)]

    def emit_schema(urn):
        fields = [
            SchemaFieldClass(
                fieldPath=name,
                type=SchemaFieldDataTypeClass(type=tcls()),
                nativeDataType=name,
            )
            for name, tcls in columns
        ]
        emitter.emit(
            MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=SchemaMetadataClass(
                    schemaName="demo",
                    # platform must be a dataPlatform URN, e.g.
                    # urn:li:dataPlatform:snowflake — pull it out of the dataset urn
                    platform=urn.split("(")[1].split(",")[0],
                    version=0,
                    hash="",
                    platformSchema=OtherSchemaClass(rawSchema=""),
                    fields=fields,
                ),
            )
        )

    # schema on the source + its direct children
    emit_schema(source_urn)
    for child in direct_children:
        emit_schema(child)
        # re-emit upstream lineage WITH fine-grained (column) edges
        fg = [
            FineGrainedLineageClass(
                upstreamType=FineGrainedLineageUpstreamTypeClass.FIELD_SET,
                upstreams=[make_schema_field_urn(source_urn, name)],
                downstreamType=FineGrainedLineageDownstreamTypeClass.FIELD,
                downstreams=[make_schema_field_urn(child, name)],
            )
            for name, _ in columns
        ]
        emitter.emit(
            MetadataChangeProposalWrapper(
                entityUrn=child,
                aspect=UpstreamLineageClass(
                    upstreams=[
                        UpstreamClass(
                            dataset=source_urn,
                            type=DatasetLineageTypeClass.TRANSFORMED,
                        )
                    ],
                    fineGrainedLineages=fg,
                ),
            )
        )


if __name__ == "__main__":
    main()
