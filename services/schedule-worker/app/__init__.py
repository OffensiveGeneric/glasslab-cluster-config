"""The schedule worker is an externally-triggered cron driver that calls the
workflow API's due-digest and approved-rerun endpoints on every invocation.

It does no scheduling itself: the actual periodicity is driven by a
Kubernetes CronJob that POSTs /run-once. Each invocation processes all
currently-due items and returns execution records so the caller can log
or monitor the cycle.
"""
