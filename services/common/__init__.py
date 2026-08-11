"""Shared Glasslab v2 modules.

Common code lives outside any single service so the orchestrator, workflow-api,
and the workspace runner validate the same wire contracts without importing one
another's internals or duplicating schema definitions.
"""
