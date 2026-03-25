# Priority Classes

These manifests define the first explicit scheduling lanes for Glasslab v2.

- `glasslab-user-high`: reviewed or user-submitted jobs
- `glasslab-autonomous-low`: autonomous background jobs

The intent is simple:

- user-submitted work should outrank background work
- autonomous work should remain useful backfill, not the main claimant on cluster capacity
