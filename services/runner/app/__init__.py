"""Glasslab runner: deterministic experiment-execution layer.

Produces a structured artifact bundle (metrics, config, manifest, status, report,
analysis notebook, artifact index) for a single experiment. The runner is a
leaf service: it consumes a frozen spec, runs one pipeline, and writes output
files. It does NOT schedule, orchestrate, or communicate with agents.
"""

__all__ = ['__version__']
__version__ = '0.1.0'
