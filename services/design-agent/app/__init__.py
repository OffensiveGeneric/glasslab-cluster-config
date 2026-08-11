"""Glasslab design-agent.

Stage-agent that derives a workflow-bound design draft (declared inputs,
candidate models, resource profile, expected artifacts) from a normalized
intake record. Scaffold only: deterministic logic, with UNRESOLVED_ sentinels
keeping unmapped inputs explicit; no live model calls yet. Consumed by
workflow-api as one stage of the run-preparation pipeline.
"""
