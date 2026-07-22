"""Narrative incident-report generation.

The lineage/owner facts are gathered deterministically in triage.py; the LLM's
only job is to turn those facts into a clear, human-readable incident report.
Keeping the LLM out of the data-gathering path is what makes the demo reliable.
"""
from __future__ import annotations

from .config import Config
from .datahub_client import AffectedAsset

_SYSTEM = (
    "You are an on-call data reliability engineer. Given a broken data asset and "
    "its downstream blast radius, write a concise incident report a team could act "
    "on immediately. Be specific, prioritise customer-facing impact, and end with a "
    "short recommended-actions checklist. Use Markdown."
)


def _facts_block(broken_urn: str, assets: list[AffectedAsset]) -> str:
    lines = [f"BROKEN ASSET: {broken_urn}", "", "DOWNSTREAM BLAST RADIUS:"]
    for a in sorted(assets, key=lambda x: x.criticality, reverse=True):
        owners = ", ".join(a.owners) or "unowned"
        flag = " [CUSTOMER-FACING]" if a.is_customer_facing else ""
        lines.append(
            f"- {a.name} ({a.entity_type} on {a.platform}, {a.hops} hop(s), "
            f"owners: {owners}){flag}"
        )
    return "\n".join(lines)


def generate_report(
    config: Config, broken_urn: str, assets: list[AffectedAsset]
) -> str:
    """Return a Markdown incident report. Falls back to a template if no LLM key."""
    facts = _facts_block(broken_urn, assets)

    if config.anthropic_api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=config.anthropic_api_key)
            msg = client.messages.create(
                model="claude-sonnet-5",
                max_tokens=1200,
                system=_SYSTEM,
                messages=[{"role": "user", "content": facts}],
            )
            return "".join(
                block.text for block in msg.content if block.type == "text"
            )
        except Exception as exc:  # keep the demo alive if the API hiccups
            return _template_report(broken_urn, assets, note=f"(LLM error: {exc})")

    # TODO: add a Gemini path here using config.gemini_api_key if you prefer.
    return _template_report(broken_urn, assets)


def generate_root_cause_report(
    config: Config, broken_urn: str, suspects: list[AffectedAsset]
) -> str:
    """Return a Markdown root-cause report ranking upstream suspects."""
    ranked = sorted(suspects, key=lambda x: x.root_cause_likelihood, reverse=True)
    out = [
        "# Root-Cause Analysis",
        "",
        f"**Symptom asset:** `{broken_urn}`  ",
        f"**Upstream suspects:** {len(ranked)}",
        "",
        "## Most likely sources (ranked)",
        "",
        "| Upstream asset | Type | Platform | Hops | Owners |",
        "|---|---|---|---|---|",
    ]
    for a in ranked:
        out.append(
            f"| {a.name} | {a.entity_type} | {a.platform} | {a.hops} | "
            f"{', '.join(a.owners) or '—'} |"
        )
    out += [
        "",
        "## Recommended checks",
        "1. Start with the closest raw-source table above — that's where bad "
        "data most often enters.",
        "2. Check its last successful load / freshness before blaming transforms.",
        "3. Walk down hop by hop until the values first go wrong.",
    ]
    return "\n".join(out)


def column_section(column_paths: list) -> str:
    """Render the column-level blast radius as a Markdown section."""
    if not column_paths:
        return ""
    lines = [
        "",
        "## Column-level impact",
        "",
        "| Downstream dataset | Downstream column | Traces to column |",
        "|---|---|---|",
    ]
    for dataset, down_col, up_col in column_paths:
        lines.append(f"| {dataset} | {down_col} | {up_col} |")
    return "\n".join(lines)


def _template_report(
    broken_urn: str, assets: list[AffectedAsset], note: str = ""
) -> str:
    ranked = sorted(assets, key=lambda x: x.criticality, reverse=True)
    customer_facing = [a for a in ranked if a.is_customer_facing]
    owners = sorted({o for a in ranked for o in a.owners})
    out = [
        "# Data Incident Report",
        "",
        f"**Broken asset:** `{broken_urn}`  ",
        f"**Downstream assets affected:** {len(assets)}  ",
        f"**Customer-facing surfaces at risk:** {len(customer_facing)}  ",
        f"**Owners to notify:** {', '.join(owners) or 'none found'}",
        "",
        "## Blast radius (ranked by criticality)",
        "",
        "| Asset | Type | Platform | Hops | Owners | Customer-facing |",
        "|---|---|---|---|---|---|",
    ]
    for a in ranked:
        out.append(
            f"| {a.name} | {a.entity_type} | {a.platform} | {a.hops} | "
            f"{', '.join(a.owners) or '—'} | {'yes' if a.is_customer_facing else 'no'} |"
        )
    out += [
        "",
        "## Recommended actions",
        "1. Page the owners of the customer-facing surfaces first.",
        "2. Freeze downstream refreshes until the source is validated.",
        "3. Post this report in the incident channel and link the DataHub asset.",
    ]
    if note:
        out += ["", f"> {note}"]
    return "\n".join(out)
