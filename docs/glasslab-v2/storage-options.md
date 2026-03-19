# Storage Options For Glasslab

This note exists to answer a practical question:

Where do `XFS`, `ZFS`, and `NFS` actually fit in the Glasslab stack?

The short answer is:

- `XFS` is a good local filesystem choice
- `ZFS` is a good durability and snapshot choice
- `NFS` is a good sharing mechanism

They solve different problems.

## Current Glasslab Storage Problem

Glasslab currently has several storage-related constraints:

- the cluster has no mature shared storage backend
- several services still depend on `emptyDir`
- some workloads are pinned because data and images are node-local
- the current platform needs clearer persistence for `glasslab-v2`
- the repo and docs are ahead of the actual storage primitives

That means storage decisions should be judged by whether they improve:

- durability
- repeatability
- backup and recovery
- multi-node accessibility
- operational simplicity

## The Three Technologies In Plain Language

### XFS

Think of `XFS` as:

- a strong default filesystem for Linux data disks
- good for large files and large directory trees
- good for local node storage
- simple compared to ZFS

What it does well:

- backing local PVs
- holding artifact directories
- holding dataset directories
- holding container and image-heavy workloads

What it does not do by itself:

- cross-node sharing
- snapshots and replication at the ZFS level
- integrity and recovery features beyond a normal filesystem

### ZFS

Think of `ZFS` as:

- filesystem plus volume manager
- stronger durability story
- snapshots
- rollback
- replication
- compression

What it does well:

- making one machine's storage more serious
- protecting important state
- enabling snapshot-based backup and rollback
- giving a better disaster-recovery story than plain ext4 or XFS alone

What it costs:

- more operational complexity
- more memory appetite
- more care around tuning and administration

### NFS

Think of `NFS` as:

- a way to share a directory tree over the network
- a simple cluster-wide access mechanism
- a useful bridge when there is no CSI-backed shared storage yet

What it does well:

- shared datasets
- shared artifacts
- shared PVC backing for less latency-sensitive workloads
- reducing some node-pinning pressure

What it does not magically solve:

- all durability problems
- all performance problems
- good database behavior by default

`NFS` is often best when exported from storage that is itself well-managed, such as `ZFS` or an intentionally provisioned local filesystem.

## How These Fit Glasslab

## Option 1: XFS On Local Disks

This is the simplest conservative path.

Use `XFS` on one or more local disks attached to the nodes that will hold:

- static local PVs
- artifacts
- dataset mirrors
- MinIO data
- Postgres data
- model cache areas

What this gives Glasslab:

- low complexity
- good local performance
- straightforward Kubernetes local PV usage
- fewer surprises than introducing a new storage stack immediately

Tradeoff:

- still node-local
- still requires deliberate backup and recovery
- does not help cross-node sharing by itself

Best fit:

- first durable pass for `glasslab-v2`
- `Postgres` and `MinIO` pinned to known nodes with explicit local PVs
- artifact and dataset storage on chosen worker nodes

## Option 2: ZFS On A Storage-Important Host

This is the stronger durability path.

Use `ZFS` on `.44` or on a dedicated storage-capable node if you want:

- snapshots
- rollback
- replication
- better integrity story
- easier off-host backup planning

What this gives Glasslab:

- a better home for important state
- a cleaner backup story for secrets, datasets, and service data
- more confidence when experimenting with storage-backed services

Tradeoff:

- more complexity than `XFS`
- probably not the best first change if the team does not want to operate ZFS yet

Best fit:

- important local state on a machine that will stay central
- backup staging on `.44`
- storage exported to others through `NFS`

## Option 3: NFS As Shared Storage

This is the sharing path.

Use `NFS` when you want multiple nodes or services to see the same backing data without committing yet to a more advanced shared storage platform.

What this gives Glasslab:

- shared datasets
- shared artifacts
- simpler cross-node reads
- a first answer to “how do I stop pinning everything to one node?”

Tradeoff:

- not every workload wants NFS
- databases need more care
- performance and locking behavior matter

Best fit:

- dataset distribution
- artifact access
- model cache sharing in some cases
- low-write or read-heavy shared paths

## Best Combined Pattern For Glasslab

The most sensible pattern for the current stack is probably:

- `XFS` or `ZFS` underneath
- `NFS` on top where sharing is actually needed

In other words:

- use a solid local filesystem for the actual disks
- export selected directories over `NFS` only when cluster-wide access is useful

That avoids pretending `NFS` is a filesystem strategy by itself.

## Recommendations By Service

### Postgres

Recommended:

- local durable storage first
- prefer `XFS` or `ZFS` under a pinned volume

Avoid as a first move:

- casual `NFS`-backed Postgres without careful validation

Reason:

- databases care about consistency and latency
- local storage is simpler and safer for the first durable version

### MinIO

Recommended:

- local durable storage first
- `XFS` is fine
- `ZFS` is attractive if snapshots and backup matter

Possible later option:

- shared storage only if the operational model is well understood

Reason:

- object storage benefits from durability and capacity planning more than from naive cross-node mounting

### NATS

Recommended:

- decide whether JetStream durability matters right now
- if it does, use local durable storage first

Reason:

- if NATS is just carrying ephemeral dev traffic, it does not need the same priority as `Postgres` and `MinIO`

### Workflow Artifacts

Recommended:

- `NFS` can make sense here
- local `XFS` also works if access stays node-pinned at first

Reason:

- artifacts are a good candidate for shared access
- they are generally less sensitive than database data

### Datasets

Recommended:

- `NFS` is a very reasonable fit
- alternatively, stage them locally on selected nodes with `XFS`

Reason:

- datasets are often read-heavy and shared
- this is one of the clearest good uses for NFS in Glasslab

### vLLM Model Cache

Recommended:

- keep local first unless there is a strong reason to share

Reason:

- model cache behavior is large, hot, and performance-sensitive
- simple local storage is usually easier than shared network storage here

Possible filesystem fit:

- `XFS` is fine
- `ZFS` can work if the host is already standardized on it

### Ignored Local Secrets And Backup Staging

Recommended:

- `ZFS` is the most attractive of the three

Reason:

- snapshots and replication are more relevant than cluster-wide sharing
- the secrets problem is about backup and recovery, not multi-node access

## Practical Recommendation Order

If the goal is to improve Glasslab without overengineering it, the order should probably be:

1. add explicit durable local storage for `Postgres` and `MinIO`
2. use `XFS` if you want the simplest path
3. use `ZFS` if you want stronger snapshot and backup behavior and are willing to operate it
4. introduce `NFS` for datasets and artifacts once shared access is worth the operational tradeoff
5. do not move everything to NFS just because it is available

## Conservative Near-Term Recommendation

If making a decision today, the conservative path would be:

- local durable storage for `Postgres` and `MinIO`
- `XFS` as the default filesystem for those data disks
- `NFS` later for shared dataset and artifact access

Why this is conservative:

- it solves the immediate `emptyDir` problem
- it does not force the team to learn ZFS immediately
- it avoids putting critical databases on shared network storage too early

## Stronger But More Ambitious Recommendation

If the team is comfortable operating ZFS, the stronger long-term path would be:

- `ZFS` on a storage-important machine
- snapshots and replication for important state
- `NFS` exports from that storage for shared datasets and artifacts

Why this is attractive:

- better DR story
- better snapshot story
- better answer to “what happens if `.44` dies?”

Why it is not automatically first:

- more operational burden
- should be intentional, not impulsive

## Decision Heuristic

Use this test:

- choose `XFS` when the problem is “I need reliable local storage”
- choose `ZFS` when the problem is “I need stronger durability, snapshots, and recovery”
- choose `NFS` when the problem is “multiple nodes need to access the same data”

If the problem is actually “image distribution is bad” or “the operator path is unclear,” none of these are the real fix.

## Recommended Next Glasslab Storage Questions

Before implementation, answer these:

1. Which node should hold durable `Postgres` data?
2. Which node should hold durable `MinIO` data?
3. Are datasets meant to be shared cluster-wide or staged locally?
4. Are artifacts meant to be shared cluster-wide or collected from one node?
5. Is `.44` supposed to become a serious storage/backup machine, or just stay a provisioner?
6. Do we want the simplest path now, or the strongest snapshot/DR path now?

Those answers will tell us whether the next step is mostly `XFS`, mostly `ZFS`, or a layered `ZFS + NFS` design.
