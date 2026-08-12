"""Glasslab v2 reporter.

Turns run manifests, metrics, and optional evaluator comparison output into
deterministic Markdown memos for operators. Rendering is a pure function of
its inputs, so identical records always produce byte-identical memos.
"""
