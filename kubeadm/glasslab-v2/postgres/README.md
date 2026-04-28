# Postgres

Postgres is the canonical record store for `workflow-api` state and the v0
vector index.

The StatefulSet uses `pgvector/pgvector:pg16` so the same database can store
workflow metadata and embedding vectors. Large artifacts remain on the `.207`
g-nas shared artifacts PVC; Postgres stores records, summaries, vector rows, and
references to those files.
