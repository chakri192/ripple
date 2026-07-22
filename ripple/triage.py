"""Orchestration: read → reason → write.

This is the heart of the agent. It ties the DataHub reads, the narrative
generation, and the write-back into one triage run.
"""
from __future__ import annotations

import re
from pathlib import Path

from rich.console import Console
from rich.text import Text

from .config import Config
from .datahub_client import DataHubClient
from .report import (
    column_section,
    generate_report,
    generate_root_cause_report,
)
from .ui import render_blast_radius, render_root_cause

console = Console()


def _slug(urn: str) -> str:
    tail = urn.split(",")[-2] if "," in urn else urn
    return re.sub(r"[^a-zA-Z0-9]+", "_", tail).strip("_").lower() or "asset"


def run_triage(
    urn: str,
    *,
    write_back: bool = True,
    with_columns: bool = False,
    raise_incident: bool = False,
    client: DataHubClient | None = None,
) -> Path:
    """Run a full incident triage for a broken asset. Returns the report path."""
    config = Config.from_env()
    client = client or DataHubClient(config)

    console.print("[bold cyan]◉  Ripple — incident triage[/]")
    console.print(f"   broken asset: [dim]{urn}[/]")

    # 1. READ — trace the blast radius
    console.print("→ Tracing downstream lineage ...", end=" ")
    assets = client.downstream_lineage(urn)
    console.print(
        f"[green]{len(assets)} affected assets across "
        f"{len({a.platform for a in assets})} platform(s)[/]"
    )

    owners = sorted({o for a in assets for o in a.owners})
    customer_facing = [a for a in assets if a.is_customer_facing]
    console.print(
        f"→ Resolving owners ............. [green]{len(owners)} owner(s)[/]"
    )
    console.print(
        f"→ Ranking by criticality ...... "
        f"[green]{len(customer_facing)} customer-facing surface(s) flagged[/]"
    )

    # optional: column-level blast radius
    col_paths = []
    if with_columns:
        console.print("→ Tracing column-level impact .", end=" ")
        col_paths = client.column_paths(urn, downstream=assets)
        console.print(f"[green]{len(col_paths)} column path(s)[/]")

    # 2. REASON — draft the narrative report
    console.print("→ Drafting incident report ....", end=" ")
    report_md = generate_report(config, urn, assets) + column_section(col_paths)
    console.print("[green]done[/]")

    # Generated reports may contain real owner names / asset paths, so they land
    # in the gitignored scratch dir. Copy a curated one into examples/ to commit.
    out_dir = Path(__file__).resolve().parent.parent / "examples" / "_scratch"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"incident_{_slug(urn)}.md"
    report_path.write_text(report_md, encoding="utf-8")

    # visual summary (tree + ranked table + severity)
    console.print()
    render_blast_radius(console, urn, assets, col_paths)

    # 3. WRITE — persist the incident back into DataHub
    if write_back:
        console.print("→ Writing incident record to DataHub ...", end=" ")
        try:
            client.tag_asset(urn, config.incident_tag)
            client.save_runbook(
                urn, title="Ripple incident triage", body_md=report_md
            )
            console.print("[green]✓ tagged + runbook saved[/]")
        except Exception as exc:
            console.print(f"[yellow]skipped ({exc})[/]")
            console.print(
                "  [dim]tip: check your token has write access, then re-run[/]"
            )

        if raise_incident:
            console.print("→ Raising native Incident entity ...", end=" ")
            try:
                inc = client.raise_incident(
                    urn,
                    title=f"Ripple: {len(assets)} assets affected",
                    description=report_md,
                )
                console.print(f"[green]✓ {inc}[/]")
            except Exception as exc:
                console.print(f"[yellow]skipped ({exc})[/]")

    console.print(f"→ Report: [bold]{report_path}[/]")
    return report_path


def run_root_cause(urn: str, *, client: DataHubClient | None = None) -> Path:
    """Trace UPSTREAM to rank the likely sources of a bad-data symptom."""
    config = Config.from_env()
    client = client or DataHubClient(config)

    suspects = client.upstream_lineage(urn)
    report_md = generate_root_cause_report(config, urn, suspects)

    # visual summary (rich)
    render_root_cause(console, urn, suspects)

    # Generated reports may contain real owner names / asset paths, so they land
    # in the gitignored scratch dir. Copy a curated one into examples/ to commit.
    out_dir = Path(__file__).resolve().parent.parent / "examples" / "_scratch"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"rootcause_{_slug(urn)}.md"
    report_path.write_text(report_md, encoding="utf-8")
    console.print(Text(f"→ report saved: {report_path}", style="dim"))
    return report_path
