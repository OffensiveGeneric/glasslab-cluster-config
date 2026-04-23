# Artifact Contract Audit 2026-04

**Date:** 2026-04-22  
**Repository:** cluster-config  
**Scope:** workflow-api, evaluator, reporter, and docs/glasslab-v2

## Executive Summary

This audit examines artifact contracts across the Glasslab v2 repository. The system has matured from a literature-first research assistant toward a runner-first experiment platform with explicit workflow families and deterministic run bundles.

**Key finding:** The artifact contract is largely stabilized around "run bundles" but retains historical artifacts with conflicting names and overlapping semantics. There are three distinct artifact categories:

1. **Run bundles** - Complete output directories from run execution
2. **Workflow registry artifacts** - Expected outputs declared per workflow family  
3. **Metadata artifacts** - State and records stored separately from bundles

## Artifact Contract Overview

### Current Target State

```
Postgres (metadata/state)
    ↓
Shared filesystem / MinIO (artifacts)
    ↓
Run bundles (immutable outputs)
```

### Canonical Artifact Locations

| Location | Purpose | Persistence |
|----------|---------|-------------|
| `/mnt/artifacts/{run_id}/` | Per-run output directory | Shared PVC |
| `glasslab-shared-artifacts` PVC | Artifacts storage | Durable (NFS) |
| `MinIO` (bucket: `research-artifacts`) | Future artifacts target | Durable |
| `Postgres` | Metadata and state | Durable (local PV) |
| `/mnt/artifacts/source-documents/` | Source document storage | Shared PVC |
| `/mnt/artifacts/workflow-api/state/` | Workflow API state | Shared PVC |

## Enumerated Artifacts

### 1. Run Bundle Artifacts (Per-Run Outputs)

#### Required Artifacts (All Workflows)

| Name | Path | Type | Purpose | Status |
|------|------|------|---------|--------|
| `run_manifest.json` | `{run_id}/run_manifest.json` | JSON | Run definition and metadata | ✅ Required |
| `config.json` | `{run_id}/config.json` | JSON | Runner configuration | ✅ Required |
| `metrics.json` | `{run_id}/metrics.json` | JSON | Run metrics and results | ✅ Required |
| `artifacts_index.json` | `{run_id}/artifacts_index.json` | JSON | Artifact manifest | ✅ Required |
| `report.md` | `{run_id}/report.md` | Markdown | Human-readable summary | ✅ Required |
| `status.json` | `{run_id}/status.json` | JSON | Run status (queued/running/succeeded/failed) | ✅ Required |
| `logs/` | `{run_id}/logs/` | Directory | Runner logs | ✅ Required |

#### Optional Artifacts

| Name | Path | Type | Purpose | Status |
|------|------|------|---------|--------|
| `analysis_notebook.ipynb` | `{run_id}/analysis_notebook.ipynb` | Notebook | Analysis notebook | ✅ Optional |
| `submission.csv` | `{run_id}/submission.csv` | CSV | Prediction submission | ✅ Optional |
| `feature_importance.csv` | `{run_id}/feature_importance.csv` | CSV | Feature importance | ✅ Optional |
| `checkpoint_manifest.json` | `{run_id}/checkpoint_manifest.json` | JSON | Model checkpoints | ✅ Optional |
| `model_card.md` | `{run_id}/model_card.md` | Markdown | Model documentation | ✅ Optional |
| `method_spec.json` | `{run_id}/method_spec.json` | JSON | Method specification | ✅ Optional |
| `design_notes.md` | `{run_id}/design_notes.md` | Markdown | Design documentation | ✅ Optional |
| `replication_delta.json` | `{run_id}/replication_delta.json` | JSON | Replication comparison | ✅ Optional |
| `environment_snapshot.txt` | `{run_id}/environment_snapshot.txt` | Text | Environment snapshot | ✅ Optional |

### 2. Workflow-Specific Artifacts

#### `generic-tabular-benchmark`

| Name | Required | Purpose |
|------|----------|---------|
| `submission.csv` | ❌ Optional | Tabular predictions output |
| `feature_importance.csv` | ❌ Optional | Feature importance output |

#### `gpu-experiment`

| Name | Required | Purpose |
|------|----------|---------|
| `checkpoint_manifest.json` | ❌ Optional | GPU model checkpoint manifests |
| `model_card.md` | ❌ Optional | GPU model documentation |

#### `literature-to-experiment`

| Name | Required | Purpose |
|------|----------|---------|
| `method_spec.json` | ❌ Optional | Method specification from literature |
| `design_notes.md` | ❌ Optional | Design documentation from paper |

#### `replication-lite`

| Name | Required | Purpose |
|------|----------|---------|
| `replication_delta.json` | ❌ Optional | Replication comparison |
| `environment_snapshot.txt` | ❌ Optional | Reproducibility environment |

### 3. State and Metadata Artifacts (Non-Bundle)

| Name | Path | Purpose | Owner |
|------|------|---------|-------|
| `state/run-store.json` | `/mnt/artifacts/workflow-api/state/run-store.json` | Workflow API session/state | workflow-api |
| `source-documents/` | `/mnt/artifacts/source-documents/` | Source paper storage | workflow-api |
| `comparison.json` | `{evaluator_output_dir}/comparison.json` | Run comparison results | evaluator |
| `summary.md` | `{evaluator_output_dir}/summary.md` | Human-readable comparison | evaluator |
| `report.md` | `{runner_output_dir}/report.md` | Single-run report (also bundle) | reporter |

## Conflicting Names and Overlaps

### Artifact Naming Inconsistencies

| Concept | Current Name | Historical/Confusing Name | Recommendation |
|---------|--------------|---------------------------|----------------|
| Run output directory | `{run_id}/` | "run bundle", "artifact bundle" | Keep `{run_id}/` |
| Artifact manifest | `artifacts_index.json` | "artifact index", "artifact manifest" | Keep `artifacts_index.json` |
| Single-run report | `report.md` | "run report", "run memo" | Keep `report.md` |
| Comparison output | `comparison.json` | "evaluator output", "comparison results" | Keep `comparison.json` |
| State store | `run-store.json` | "workflow state", "session store" | Keep `run-store.json` |

### Duplicate Concepts

#### 1. "Bundle" vs "Artifacts" vs "Output Directory"

**Issue:** The term "bundle" appears inconsistently across code and docs:

- `run bundle` (evaluator input)
- `artifact bundle` (input type in schemas)
- `{run_id}/` directory (actual on-disk structure)

**Analysis:** These refer to the same conceptual entity: the complete output of a run execution. The term "bundle" should be reserved for evaluator inputs; the on-disk structure should be "run directory" or just "run output".

**Recommendation:**
- ✅ Keep `{run_id}/` as the canonical on-disk directory
- ✅ Keep "run bundle" for evaluator input semantics
- ❌ Deprecate "artifact bundle" as an input type name (use "run_id" or "run directory" instead)

#### 2. "Report" vs "Summary"

**Issue:** Multiple report-like artifacts exist:

- `report.md` (per-run, generated by reporter)
- `summary.md` (per-comparison, generated by evaluator)
- "run memo" (legacy term for report)

**Analysis:** The distinction is intentional but poorly documented:

- `report.md` = Single run summary (who ran what, what were results)
- `summary.md` = Multi-run comparison (which won, why)

**Recommendation:**
- ✅ Keep both, document distinction in runbooks
- ❌ Deprecate "run memo" term in favor of "report"

### Metadata Mixed with Files

#### Current Pattern

```
Run Directory ({run_id}/)
├── metadata_files (JSON)         → machine-readable
│   ├── run_manifest.json
│   ├── config.json
│   ├── metrics.json
│   ├── artifacts_index.json
│   ├── status.json
├── documentation_files (Markdown) → human-readable
│   └── report.md
└── logs/                          → machine-generated
    └── runner.log
```

#### State Store (Separate from Run Directory)

```
/mnt/artifacts/workflow-api/state/
└── run-store.json                 → Postgres backup if using JSON backend
```

#### Issue: Dual-State Storage

**Problem:** Run metadata exists in two places:

1. **Run bundle** (`run_manifest.json`, `config.json`, etc.)
2. **Workflow API state** (`run-store.json` or Postgres)

**Impact:**
- Synchronization complexity
- Potential divergence
- Confusion about "source of truth"

**Analysis:**
- The run bundle contains the *execution* metadata
- The workflow API state contains the *workflow* metadata (sessions, designs, campaigns)
- These serve different purposes but share some data (run_id, status)

**Recommendation:**
- ✅ Keep run bundle as source of truth for *execution* (what ran, what were inputs/outputs)
- ✅ Keep workflow API state as source of truth for *workflow* (sessions, campaigns, designs)
- ⚠️ Clarify boundary: execution metadata belongs in bundles; workflow metadata belongs in state store

## Proposed Normalized Artifact List

### Keep (Stable, Well-Defined)

| Artifact | Location | Purpose | Rationale |
|----------|----------|---------|-----------|
| `run_manifest.json` | `{run_id}/` | Run definition | Core execution record; immutable |
| `config.json` | `{run_id}/` | Runner config | Reproducibility |
| `metrics.json` | `{run_id}/` | Results | Core output |
| `artifacts_index.json` | `{run_id}/` | Artifact manifest | Discoverability |
| `report.md` | `{run_id}/` | Human summary | Operator interface |
| `status.json` | `{run_id}/` | Run status | Lifecycle tracking |
| `logs/runner.log` | `{run_id}/logs/` | Execution log | Debugging |
| `comparison.json` | `{evaluator_output}/` | Comparison results | Multi-run analysis |
| `summary.md` | `{evaluator_output}/` | Comparison summary | Operator comparison |

### Rename (Clarify Semantics)

| Current Name | Rename To | Rationale |
|--------------|-----------|-----------|
| `run bundle` (concept) | `{run_id}/` (directory) | "Bundle" is ambiguous; use explicit directory path |
| `artifact bundle` (input type) | `run_id` | Input should reference run ID, not "bundle" |
| `analysis_notebook.ipynb` | `{run_id}/analysis.ipynb` | Shorter, clearer name |
| `submission.csv` | `{run_id}/predictions.csv` | More specific |
| `feature_importance.csv` | `{run_id}/features.csv` | Shorter, clearer |
| `checkpoint_manifest.json` | `{run_id}/checkpoints.json` | More specific |

### Deprecate (Duplicate, Ambiguous, or Obsolete)

| Artifact | Reason | Migration Path |
|----------|--------|----------------|
| `artifact bundle` (input type name) | Confusing; duplicate of "run_id" | Use `run_id` string instead |
| "run memo" (term) | Duplicate of "report"; ambiguous | Use "report" consistently |
| `latest` (alias for session/run) | Underspecified; breaks reproducibility | Use explicit session_id/run_id |
| JSON-on-artifacts-share (state store) | Duplicates Postgres | Migrate to Postgres; JSON is backup only |

## Artifact Path Conventions

### Canonical Paths

| Purpose | Path | Notes |
|---------|------|-------|
| Run output directory | `/mnt/artifacts/{run_id}/` | Shared PVC |
| Source documents | `/mnt/artifacts/source-documents/{document_id}/` | Shared PVC |
| Workflow API state | `/mnt/artifacts/workflow-api/state/run-store.json` | Shared PVC, fallback to Postgres |
| Evaluator output | `/mnt/artifacts/evaluator/{comparison_id}/` | Per-comparison |
| Runner logs | `{run_id}/logs/runner.log` | In run directory |

### Future Paths (MinIO)

| Purpose | Path | Notes |
|---------|------|-------|
| Run outputs | `s3://research-artifacts/{run_id}/` | Pending MinIO migration |
| Source documents | `s3://research-sources/{document_id}/` | Pending MinIO migration |

## Contract Requirements by Artifact

### Required by All Workflows

Every run *must* produce:

- `run_manifest.json` with: `run_id`, `workflow_id`, `objective`, `submitted_by`, `submitted_at`, `requested_models`, `inputs`
- `config.json` with: runner configuration
- `metrics.json` with: primary metric, values, runtime_seconds
- `artifacts_index.json` with: list of artifact entries
- `report.md` with: single-run summary
- `status.json` with: `run_id`, `status`, `updated_at`, `detail`
- `logs/runner.log` with: structured log entries

### Required by Specific Workflows

| Workflow | Additional Required | Notes |
|----------|---------------------|-------|
| None | N/A | All workflows share the same required artifacts |

### Optional Artifacts by Workflow

| Workflow | Optional Artifacts |
|----------|-------------------|
| `generic-tabular-benchmark` | `submission.csv`, `feature_importance.csv` |
| `gpu-experiment` | `checkpoint_manifest.json`, `model_card.md` |
| `literature-to-experiment` | `method_spec.json`, `design_notes.md` |
| `replication-lite` | `replication_delta.json`, `environment_snapshot.txt` |

## Artifact Lifecycle

### Production

1. **Run execution** → produces run bundle
2. **Reporter service** → produces `report.md`
3. **Evaluator service** (when multiple runs) → produces `comparison.json` + `summary.md`

### Consumption

1. **Operator** → reads `report.md`, `comparison.json`, `summary.md`
2. **UI/dashboard** → reads `artifacts_index.json`, `metrics.json`
3. **Autonomous agents** → reads `run_manifest.json`, `metrics.json`
4. **Debug tools** → reads `logs/runner.log`, `config.json`

### Retention

- **Run bundles:** Retain until session/campaign completion + retention policy
- **State store:** Retain per Postgres retention policy
- **Source documents:** Retain indefinitely or per session scope
- **Evaluator outputs:** Retain until session/campaign completion

## Recommendations

### Immediate Actions

1. ✅ **Document artifact contract** (this document)
2. ✅ **Standardize run bundle structure** (already in place)
3. ⚠️ **Clarify state vs execution metadata** (current split is intentional but undocumented)
4. ❌ **Deprecate `latest` alias** (use explicit IDs)
5. ❌ **Deprecate "artifact bundle" input type** (use `run_id`)

### Medium-Term Actions

1. ⚠️ **Migrate to MinIO** for artifact storage (from shared PVC)
2. ⚠️ **Document artifact consumption contracts** (who reads what)
3. ⚠️ **Add artifact validation** (schema checking for required artifacts)

### Long-Term Actions

1. ⚠️ **Decouple execution metadata from workflow state** (separate services)
2. ⚠️ **Version artifact contracts** (backward compatibility)
3. ⚠️ **Add artifact compression** (store large artifacts efficiently)

## References

- `docs/glasslab-v2/canonical-stack-2026-04.md` - Canonical stack definition
- `docs/glasslab-v2/storage-and-state.md` - Storage strategy
- `docs/glasslab-v2/runbooks/` - Runbooks
- `services/common/schemas/run_artifacts.py` - Artifact schemas
- `services/common/schemas/workflow_registry.py` - Workflow registry
- `services/workflow-api/app/run_artifacts.py` - Artifact processing
- `services/workflow-registry/definitions/` - Workflow definitions
