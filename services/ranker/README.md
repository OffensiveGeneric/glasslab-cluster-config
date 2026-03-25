# Ranker

`ranker` is a bounded advisory service for candidate ranking tasks in Glasslab v2.

The first intended use is workflow-family ranking from a small backend-generated candidate set.

It is intentionally narrow:

- advisory only
- no run creation
- no workflow approval
- no direct cluster or backend mutation

`workflow-api` should remain the caller and system-of-record.

Live-host note:

- the canonical service shape in `app/` is FastAPI-based
- a self-contained Ruby runtime wrapper exists in `live_server.rb` for hosts such as the current Mac ranker box that do not yet have usable Python CLI tooling
- both paths expose the same minimal API:
  - `GET /healthz`
  - `POST /rank/workflow-family`
