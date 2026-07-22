"""Auto-trigger loop: watch DataHub for broken assets and triage them.

Demo path polls for datasets carrying the `broken` tag. In production you'd
replace `find_broken_assets` with a subscription to DataHub Assertion-failure
events (or a webhook) — the loop below stays identical.

    python -m ripple watch --interval 15
"""
from __future__ import annotations

import time

from rich.console import Console

from .config import Config
from .datahub_client import DataHubClient
from .triage import run_triage

console = Console()


def watch(interval: int = 15, once: bool = False) -> None:
    config = Config.from_env()
    client = DataHubClient(config)
    seen: set[str] = set()

    console.print(
        f"[bold cyan]◉  Ripple — watching for broken assets[/] "
        f"(every {interval}s; tag='broken')"
    )
    while True:
        broken = client.find_broken_assets(tag="broken")
        new = [u for u in broken if u not in seen]
        if new:
            console.print(f"[yellow]⚠ {len(new)} newly broken asset(s)[/]")
            for urn in new:
                seen.add(urn)
                run_triage(
                    urn, write_back=True, raise_incident=True, client=client
                )
        else:
            console.print("[dim]· nothing broken[/]")
        if once:
            return
        time.sleep(interval)
