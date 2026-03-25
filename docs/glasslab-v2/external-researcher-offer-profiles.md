# External Researcher Offer Profiles

This note turns the current outside-researcher discussion into explicit offer profiles.

The goal is to avoid offering vague "cluster access" when the actual near-term value is a bounded execution lane with better compute, longer runtimes, and backend artifact handling than a typical laptop setup.

## Profile A: Admin-Reviewed CPU Workflow Lane

This is the safest offer today.

What the researcher gets:

- a reviewed workflow run through Glasslab v2
- bounded approved workflow families only
- artifacts returned through the existing backend path
- no direct cluster credentials

Why it is stronger than a laptop:

- longer unattended execution
- stable backend artifact collection
- reproducible run records
- access to the existing workflow/evaluation/reporting structure

Likely placement:

- CPU-first on `node03`
- additional CPU workers only if needed and they do not conflict with core services

Good fit for:

- tabular benchmarks
- reviewed paper-to-experiment reproductions
- multi-run comparisons that benefit from backend artifact handling more than raw GPU throughput

## Profile B: Admin-Reviewed GPU Workflow Lane

This is potentially compelling, but it is not yet a clean default offer.

What the researcher gets:

- reviewed GPU-backed runs for approved workload classes
- bounded execution, not arbitrary shell access
- artifacts delivered through the normal backend path

Why it is stronger than a laptop:

- access to NVIDIA-backed workers
- longer unattended execution
- room for parameter sweeps or heavier replication workloads

Current blockers:

- `node02` still has the legacy `vllm` path occupying GPU resources
- GPU fairness and quota policy are not yet defined
- there is no polished guest-safe scheduling lane

Good fit for later:

- reviewed replication workloads
- bounded benchmark sweeps
- approved training/evaluation jobs that clearly exceed laptop practicality

## Profile C: Managed Research Service Lane

This is the most realistic "special thing the cluster can do" story for an outside researcher.

What the researcher gets:

- a bounded backend service rather than raw cluster access
- admin-mediated intake
- staged execution through `workflow-api`
- final artifacts and summaries

Why it is stronger than a laptop:

- combines cluster execution with the Glasslab orchestration path
- can use the Mac-backed inference/ranker services as part of the workflow
- supports unattended multi-stage processing instead of one manual local script

Good fit for:

- literature-to-experiment ingestion
- repeatable evaluation/reporting pipelines
- future bounded stage-agent workflows

## What Not To Offer Yet

These would overstate current maturity:

- a generic "here is your own worker node" promise
- self-service arbitrary namespace access
- unrestricted GPU tenancy
- direct access to internal backing services
- a claim that the lab is already a polished outside-user multi-tenant platform

## Recommendation

The near-term outside-researcher offer should be phrased as:

- reviewed workflow execution
- bounded workload classes
- artifact delivery
- optional later GPU-backed lane once `node02` and policy gaps are cleaned up

Do not phrase the offer as "renting out one worker node." That is the weaker value proposition and is less defensible operationally.

## References

- `external-researcher-what-we-can-offer-now.md`
- `external-researcher-hardening-gaps.md`
- `../machine-state-2026-03-24.md`
