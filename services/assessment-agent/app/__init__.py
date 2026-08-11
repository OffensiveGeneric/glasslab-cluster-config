"""assessment-agent package.

Stage-agent that maps an interpretation record onto approved workflows and emits
an execution-readiness assessment (proceed / needs_review / reject) with
unresolved fields kept explicit. Scaffold only: deterministic logic, no live
model calls yet. Consumed by workflow-api as one stage of the run-preparation
pipeline.
"""
