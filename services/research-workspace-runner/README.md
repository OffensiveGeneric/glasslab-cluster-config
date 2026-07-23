# Research Workspace Runner

This image executes one immutable research workspace under the generic
Glasslab run contract.

The runner:

- verifies SHA-256 digests for task, source, and every exposed dataset
- rejects archive path traversal and archive links
- exposes resolved, read-only dataset bindings to the workspace
- executes one declared command under a wall-clock timeout
- writes a terminal artifact bundle even when verification or execution fails
- fails a nominally successful command when required artifacts are absent
- rejects symlinks as artifact evidence and hashes emitted files

It does not generate research code. The research agent or researcher produces
the source bundle first; plan approval freezes that bundle before this runner
executes it.

The Kubernetes submitter mounts only the approved input files and the current
run's output subdirectory. The runner never needs the roots of the shared
datasets or artifacts volumes.
