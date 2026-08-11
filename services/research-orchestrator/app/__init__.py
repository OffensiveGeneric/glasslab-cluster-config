"""Glasslab research orchestrator.

Owns run state transitions, approvals, agent sessions, policy, recovery, job
watching, and the append-only event log. The orchestrator is the only process
that advances run state; Discord is an interface and the agents only propose
normalized, policy-checked actions.
"""
