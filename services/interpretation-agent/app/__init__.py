"""Glasslab v2 interpretation stage agent.

Accepts one workflow-api intake-shaped request and returns one bounded
interpretation draft (a deterministic scaffold, optionally refined by a model
backend). The agent never creates runs, approves execution, or mutates cluster
state; it is advisory only and owns no durable workflow state.
"""
