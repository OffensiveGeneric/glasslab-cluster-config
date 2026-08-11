"""Glasslab v2 ranker service.

Deterministically ranks a small backend-generated candidate set (initially
workflow families) against a request. Advisory only: no run creation, no
approval, no cluster or backend mutation; workflow-api remains the caller and
system of record.
"""
