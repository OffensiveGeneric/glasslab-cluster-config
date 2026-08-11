"""Stub fallback for search.run_spec.RunSpec.

A no-op constructor that satisfies the type when the search library is not
available. Properties (config, budget) are expected to be set by the caller
after construction; this stub does not enforce a schema.
"""

# Stub for search.run_spec.RunSpec
# This is needed for contrastive_runner.py but the actual implementation
# will be provided by the cluster runtime

class RunSpec:
    """Mock RunSpec for contrastive learning."""
    def __init__(self, *args, **kwargs):
        pass
