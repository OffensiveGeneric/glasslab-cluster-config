"""Glasslab v2 deterministic evaluator.

Reads the immutable runner records (manifest, metrics, status) for one or more
runs and writes comparison.json and summary.md. Deterministic code only: the
workload emits evidence and the runner records it; scoring and ranking happen
here, never inside a workload or an agent.
"""
