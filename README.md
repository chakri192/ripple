<div align="center">

<img src="assets/ripple-mark.svg" width="80" alt="ripple" />

# ripple

**A data-incident triage agent for DataHub.**

Given a broken asset, it traverses downstream lineage across every platform, ranks the affected assets by criticality, resolves the owners to notify, and records the incident back into the catalog.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-1c1c1e?style=flat-square&logo=python&logoColor=3776AB" />
  <img alt="DataHub" src="https://img.shields.io/badge/DataHub-acryl--datahub-1c1c1e?style=flat-square" />
  <img alt="Size" src="https://img.shields.io/badge/~1.3k-lines-1c1c1e?style=flat-square" />
  <img alt="Interfaces" src="https://img.shields.io/badge/CLI-%2B%20web%20dashboard-1c1c1e?style=flat-square" />
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-1c1c1e?style=flat-square" />
</p>

<br />

<img src="docs/blast-radius.svg" alt="The blast-radius view: severity banner, affected asset counts, and an interactive lineage graph" width="860">

</div>

---

## Overview

When a table breaks, the immediate questions are which downstream assets are affected, how serious the failure is, and who needs to be informed. Answering them manually means traversing lineage across several platforms and cross-referencing ownership metadata.

ripple performs that traversal in a single command and then writes the result back to the catalog, so the incident is recorded where the affected asset is documented rather than only in a terminal.

## Requirements

- A running DataHub instance. A local `datahub docker quickstart` deployment is sufficient.
- Python 3.10 or later.
- An API token, available from `~/.datahubenv`.

## Installation

```sh
uv pip install -e .
cp .env.example .env          # set DATAHUB_GMS_TOKEN
```

To evaluate it against a realistic scenario:

```sh
python demo/seed_incident_demo.py
python -m ripple triage "urn:li:dataset:(urn:li:dataPlatform:snowflake,prod.raw.orders_raw,PROD)"
```

> Without a DataHub instance available, the [browser-based simulator](https://chakri192.github.io/ripple/) demonstrates the same workflow — selecting any table breaks it and runs the triage locally.

## Commands

| Command | Description |
|---|---|
| `ripple triage <urn>` | Downstream blast radius, ranked, with catalog write-back |
| `ripple triage <urn> --no-write-back` | Report only; the catalog is not modified |
| `ripple triage <urn> --columns --incident` | Adds column-level impact and raises an Incident entity |
| `ripple root-cause <urn>` | Traverses upstream and ranks likely sources |
| `ripple watch --interval 15` | Polls for broken assets and triages them automatically |
| `ripple web` | Serves the read-only dashboard on port 8000 |

## Capabilities

**Blast radius.** A single URN yields the complete downstream set: every affected table, view, and dashboard across all lineage hops, ranked by criticality with an automatically assigned severity. A customer-facing dashboard entering the affected set raises the incident to SEV1.

**Root cause analysis.** Reversing the traversal ranks the probable sources of incorrect data, ordered from the nearest raw table outward, so investigation begins where data enters the system rather than where the symptom appeared.

**Column-level impact.** Fine-grained lineage identifies the specific column deriving from the broken field, rather than reporting only that a dashboard is affected.

**Ownership resolution.** Owners are resolved across the blast radius, with those responsible for customer-facing assets surfaced first.

**Catalog write-back.** The incident is recorded against the affected asset:

| Written | Aspect |
|---|---|
| `incident` tag on the broken asset | `GlobalTags` |
| Triage runbook in the documentation panel | `EditableDatasetProperties` |
| A first-class incident on the asset | `IncidentInfo` |

**Automatic triggering.** A `watch` loop polls for broken assets and triages them without intervention. Substituting DataHub assertion-failure events for the detector makes the process fully automatic.

**Two interfaces.** A terminal interface presenting a severity banner, lineage tree, ranked table, and recommended actions; and a read-only web dashboard with an interactive lineage graph and light and dark themes. The graph is hand-authored SVG with no charting library or CDN dependency.

## Architecture

```
  broken URN
      │
      ▼
  ┌── read ────────────────┐   searchAcrossLineage (MCP / SDK)
  │  downstream lineage,   │──▶ DataHub GMS
  │  owners, columns       │
  ├── reason ──────────────┤
  │  rank by criticality,  │──▶ severity (SEV1–3)
  │  draft the narrative   │──▶ LLM
  ├── write ───────────────┤
  │  tag · runbook ·       │──▶ DataHub GMS
  │  Incident entity       │
  └────────────────────────┘
```

The separation between stages is deliberate. **Lineage traversal, owner resolution, and ranking are implemented in code**, so the same input produces the same output on every run. A language model is used solely to compose the human-readable report.

No determination of what is affected, how severe the incident is, or who should be notified is produced by a model. This is what makes the output suitable to act on during an incident, and what makes the results reproducible.

## Project structure

```
ripple/
├── ripple/      The agent — client · triage · report · watch · ui · web
├── demo/        Seeds a source → 5 tables → 3 dashboards scenario
├── docs/        Landing page and in-browser simulator
├── examples/    Sample generated incident reports
└── skills/      Incident-triage skill definition
```

## License

Apache-2.0 — see [LICENSE](LICENSE).

## Contributors

| | |
|---|---|
| [chakri192](https://github.com/chakri192) | Author |
| [aider](https://github.com/Aider-AI/aider) | AI pair programmer |

Development assisted by aider using local models through [Ollama](https://ollama.com): `qwen2.5-coder:7b` for code and `llama3.1:8b` for prose.
