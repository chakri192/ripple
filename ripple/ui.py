"""Rich terminal rendering for Ripple — the CLI's visual layer.

Kept purely presentational: it receives already-fetched data and draws it. The
palette mirrors the web UI — neutral greys with red reserved for severity and
customer-facing impact.
"""
from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .datahub_client import AffectedAsset

_BORDER = "grey37"
_RULE = "grey42"


def severity(assets: list[AffectedAsset]) -> tuple[str, str]:
    """Map a blast radius to a SEV level + colour."""
    if any(a.is_customer_facing for a in assets):
        return "SEV1", "red"
    if assets:
        return "SEV2", "yellow"
    return "SEV3", "green"


def _short(urn: str) -> str:
    return urn.split(",")[-2] if "," in urn else urn


def _summary_line(sev, color, n_assets, n_cf, n_owners, n_plat) -> Text:
    t = Text()
    t.append(f" {sev} ", style=f"bold white on {color}")
    t.append("   ")
    t.append(str(n_assets), style="bold")
    t.append(" assets  ·  ")
    t.append(str(n_cf), style="bold red" if n_cf else "bold")
    t.append(" customer-facing  ·  ")
    t.append(str(n_owners), style="bold")
    t.append(" owners  ·  ")
    t.append(str(n_plat), style="bold")
    t.append(" platforms")
    return t


def render_blast_radius(
    console: Console,
    broken_urn: str,
    assets: list[AffectedAsset],
    col_paths: list | None = None,
) -> None:
    sev, color = severity(assets)
    owners = sorted({o for a in assets for o in a.owners})
    cf = [a for a in assets if a.is_customer_facing]
    platforms = len({a.platform for a in assets})

    console.print()
    console.print(Rule(Text("Ripple · incident triage", style="bold"), style=_RULE))
    console.print(
        _summary_line(sev, color, len(assets), len(cf), len(owners), platforms)
    )
    console.print(Text(broken_urn, style="dim"))
    console.print()

    # blast radius as a tree, grouped by hop distance
    tree = Tree(
        Text(_short(broken_urn), style="bold cyan") + Text("  source", style="dim"),
        guide_style=_BORDER,
    )
    by_hop: dict[int, list[AffectedAsset]] = {}
    for a in assets:
        by_hop.setdefault(a.hops, []).append(a)
    for hop in sorted(by_hop):
        label = f"{hop} hop{'s' if hop != 1 else ''} downstream"
        branch = tree.add(Text(label, style="dim"))
        for a in sorted(by_hop[hop], key=lambda x: x.criticality, reverse=True):
            node = Text()
            node.append(a.name, style="bold red" if a.is_customer_facing else "")
            node.append(f"  {a.entity_type.lower()} · {a.platform}", style="dim")
            if a.is_customer_facing:
                node.append("  ⚠ customer-facing", style="red")
            if a.owners:
                node.append(f"  ·  {', '.join(a.owners)}", style="dim")
            branch.add(node)
    console.print(tree)
    console.print()

    # ranked impact
    table = Table(
        box=box.ROUNDED, border_style=_BORDER, header_style="bold",
        title="Ranked impact", title_style="bold", title_justify="left",
    )
    table.add_column("Asset")
    table.add_column("Type", style="dim")
    table.add_column("Platform", style="dim")
    table.add_column("Hops", justify="right", style="dim")
    table.add_column("Owners")
    table.add_column("CF", justify="center")
    for a in sorted(assets, key=lambda x: x.criticality, reverse=True):
        table.add_row(
            Text(a.name, style="red" if a.is_customer_facing else ""),
            a.entity_type.lower(),
            a.platform,
            str(a.hops),
            ", ".join(a.owners) or "—",
            Text("●", style="red") if a.is_customer_facing else "",
        )
    console.print(table)

    if col_paths:
        ct = Table(
            box=box.ROUNDED, border_style=_BORDER, header_style="bold",
            title="Column-level impact", title_style="bold", title_justify="left",
        )
        ct.add_column("Downstream dataset")
        ct.add_column("Column")
        ct.add_column("Traces to")
        for dataset, down_col, up_col in col_paths:
            ct.add_row(dataset, down_col, up_col)
        console.print(ct)

    # recommended actions
    page = sorted({o for a in cf for o in a.owners})
    body = Text()
    body.append("1  ", style="bold")
    if page:
        body.append("Page the customer-facing owners:  ")
        body.append(", ".join(page), style="bold red")
    else:
        body.append("No owners on the customer-facing surfaces — assign owners.")
    body.append("\n2  ", style="bold")
    body.append("Freeze downstream refreshes until the source is validated.")
    body.append("\n3  ", style="bold")
    body.append("Post this report in the incident channel and link the asset.")
    console.print(
        Panel(
            body, title="Recommended actions", title_align="left",
            border_style=_BORDER,
        )
    )


def render_root_cause(
    console: Console, symptom_urn: str, suspects: list[AffectedAsset]
) -> None:
    console.print()
    console.print(
        Rule(Text("Ripple · root-cause analysis", style="bold"), style=_RULE)
    )
    head = Text()
    head.append(str(len(suspects)), style="bold")
    head.append(" upstream suspect(s)  ·  ")
    head.append(str(len({s.platform for s in suspects})), style="bold")
    head.append(" platform(s)")
    console.print(head)
    console.print(Text(symptom_urn, style="dim"))
    console.print()

    table = Table(
        box=box.ROUNDED, border_style=_BORDER, header_style="bold",
        title="Most likely sources", title_style="bold", title_justify="left",
    )
    table.add_column("#", justify="right", style="dim")
    table.add_column("Upstream asset")
    table.add_column("Type", style="dim")
    table.add_column("Platform", style="dim")
    table.add_column("Hops", justify="right", style="dim")
    table.add_column("Owners")
    ranked = sorted(suspects, key=lambda x: x.root_cause_likelihood, reverse=True)
    for i, s in enumerate(ranked, 1):
        table.add_row(
            str(i), s.name, s.entity_type.lower(), s.platform,
            str(s.hops), ", ".join(s.owners) or "—",
        )
    console.print(table)
    console.print(
        Panel(
            Text(
                "Start with the closest raw-source table above — that's where bad "
                "data usually enters. Check its last successful load before "
                "blaming transforms.",
            ),
            title="Where to look", title_align="left", border_style=_BORDER,
        )
    )
