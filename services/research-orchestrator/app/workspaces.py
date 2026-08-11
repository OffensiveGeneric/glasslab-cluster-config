"""Per-run, per-agent isolated workspaces over git worktrees.

Each run gets its own root with separate Beaker and Honeydew worktrees (shared
repository object database, independent working trees and indices) plus durable
protocol, shared-artifact, report, and event directories. Everything an agent
can write is confined to its own workspace; authoritative copies and digests
are produced by the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import zipfile

from .schemas import AgentName


class WorkspaceError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunWorkspaces:
    root: Path
    protocol: Path
    beaker: Path
    honeydew: Path
    shared_artifacts: Path
    reports: Path
    events: Path


class WorkspaceManager:
    def __init__(
        self,
        *,
        workspace_root: str,
        approved_repo_path: str,
        approved_repo_ref: str,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.approved_repo_path = Path(approved_repo_path).resolve()
        self.approved_repo_ref = approved_repo_ref

    def paths(self, run_id: str) -> RunWorkspaces:
        root = self.workspace_root / run_id
        return RunWorkspaces(
            root=root,
            protocol=root / 'protocol',
            beaker=root / 'beaker-worktree',
            honeydew=root / 'honeydew-worktree',
            shared_artifacts=root / 'shared-artifacts',
            reports=root / 'reports',
            events=root / 'events',
        )

    def prepare(self, run_id: str) -> RunWorkspaces:
        paths = self.paths(run_id)
        for path in (
            paths.root,
            paths.protocol,
            paths.shared_artifacts,
            paths.reports,
            paths.events,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not (self.approved_repo_path / '.git').exists():
            raise WorkspaceError(
                f'approved repository is not a Git checkout: {self.approved_repo_path}'
            )
        self._ensure_worktree(paths.beaker)
        self._ensure_worktree(paths.honeydew)
        return paths

    def _ensure_worktree(self, destination: Path) -> None:
        # Worktrees give each agent an isolated working tree while sharing the
        # approved repository's objects; detached HEAD means agents never
        # advance a branch in the approved checkout.
        if destination.exists():
            if not (destination / '.git').exists():
                # An existing non-worktree workspace is treated as corruption
                # and fails the run rather than being silently recreated.
                raise WorkspaceError(
                    f'workspace exists but is not a Git worktree: {destination}'
                )
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                'git',
                '-C',
                str(self.approved_repo_path),
                'worktree',
                'add',
                '--detach',
                str(destination),
                self.approved_repo_ref,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise WorkspaceError(completed.stderr.strip() or 'git worktree add failed')

    def agent_workspace(self, run_id: str, agent: AgentName) -> Path:
        paths = self.paths(run_id)
        if agent == AgentName.BEAKER:
            return paths.beaker
        if agent == AgentName.HONEYDEW:
            return paths.honeydew
        raise WorkspaceError(f'no workspace for agent: {agent}')

    def copy_agent_output(
        self,
        *,
        run_id: str,
        agent: AgentName,
        relative_path: str,
        destination_kind: str,
    ) -> tuple[Path, str]:
        workspace = self.agent_workspace(run_id, agent).resolve()
        source = (workspace / relative_path).resolve()
        if not source.is_relative_to(workspace):
            raise WorkspaceError('agent output escapes isolated workspace')
        if source.is_symlink() or not source.is_file():
            raise WorkspaceError(f'agent output is not a real file: {relative_path}')
        # The source must be a real file inside the agent's own workspace, so
        # an agent can only hand over bytes it actually produced; the returned
        # digest becomes the authoritative record of what was copied.
        paths = self.paths(run_id)
        if destination_kind == 'protocol':
            destination = paths.protocol / 'program.md'
        elif destination_kind == 'report':
            destination = paths.reports / 'report.md'
        else:
            destination = paths.shared_artifacts / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        digest = sha256(destination.read_bytes()).hexdigest()
        return destination, digest

    def freeze_protocol(self, run_id: str) -> None:
        protocol = self.paths(run_id).protocol / 'program.md'
        if not protocol.is_file():
            raise WorkspaceError('program.md does not exist')
        protocol.chmod(0o444)
        # After approval the protocol is immutable everywhere (protocol dir and
        # both worktrees) so later phases cannot silently revise what was
        # approved.
        for workspace in (
            self.paths(run_id).beaker,
            self.paths(run_id).honeydew,
        ):
            target = workspace / 'program.md'
            shutil.copy2(protocol, target)
            target.chmod(0o444)

    def create_review_snapshot(
        self,
        *,
        run_id: str,
        relative_paths: list[str],
        maximum_files: int = 128,
        maximum_bytes: int = 4 * 1024 * 1024,
    ) -> tuple[Path, list[dict[str, object]]]:
        paths = self.paths(run_id)
        source_root = paths.beaker.resolve()
        destination_root = paths.honeydew / '.glasslab-review'
        if destination_root.is_symlink():
            raise WorkspaceError('review snapshot destination is a symlink')
        if destination_root.exists():
            shutil.rmtree(destination_root)
        destination_root.mkdir(parents=True)

        manifest: list[dict[str, object]] = []
        total_bytes = 0
        for relative in sorted(set(relative_paths)):
            relative_path = Path(relative)
            if relative_path.is_absolute() or '..' in relative_path.parts:
                raise WorkspaceError(
                    f'review snapshot path is not relative: {relative}'
                )
            unresolved_source = source_root / relative_path
            path_cursor = source_root
            contains_symlink = False
            for part in relative_path.parts:
                path_cursor /= part
                if path_cursor.is_symlink():
                    contains_symlink = True
                    break
            if contains_symlink:
                raise WorkspaceError(
                    f'review snapshot source traverses a symlink: {relative}'
                )
            # Every path component is checked for symlinks so a symlinked
            # intermediate directory cannot redirect the copy outside the
            # Beaker worktree; the snapshot is read-only and digest-manifested.
            source = unresolved_source.resolve()
            if not source.is_relative_to(source_root):
                raise WorkspaceError(
                    f'review snapshot path escapes Beaker workspace: {relative}'
                )
            if not source.is_file():
                raise WorkspaceError(
                    f'review snapshot source is not a real file: {relative}'
                )
            size = source.stat().st_size
            if len(manifest) >= maximum_files:
                raise WorkspaceError('review snapshot exceeds file limit')
            if total_bytes + size > maximum_bytes:
                raise WorkspaceError('review snapshot exceeds byte limit')

            destination = destination_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            destination.chmod(0o444)
            digest = sha256(destination.read_bytes()).hexdigest()
            manifest.append(
                {
                    'path': relative_path.as_posix(),
                    'size_bytes': size,
                    'sha256': digest,
                }
            )
            total_bytes += size

        manifest_path = destination_root / 'manifest.json'
        manifest_path.write_text(
            json.dumps(
                {
                    'schema_version': 'glasslab-review-snapshot-v1',
                    'source_agent': AgentName.BEAKER.value,
                    'files': manifest,
                    'total_bytes': total_bytes,
                },
                indent=2,
                sort_keys=True,
            )
            + '\n',
            encoding='utf-8',
        )
        manifest_path.chmod(0o444)
        return destination_root, manifest

    def write_recovery_checkpoint(
        self,
        *,
        run_id: str,
        agent: AgentName,
        payload: dict,
    ) -> Path:
        destination = self.paths(run_id).events / (
            f'{agent.value}-recovery-checkpoint.json'
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Temp-file plus atomic replace keeps the checkpoint durable and
        # complete; it lives under events so recovery replays from the same
        # ordered location as the rest of the log.
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )
        temporary.replace(destination)
        return destination

    def install_task_bundle(
        self,
        *,
        run_id: str,
        problem_path: str,
        evaluator_prompt_path: str,
    ) -> None:
        for workspace in (
            self.paths(run_id).beaker,
            self.paths(run_id).honeydew,
        ):
            destination = workspace / 'benchmark-task'
            destination.mkdir(parents=True, exist_ok=True)
            for source_name, destination_name in (
                (problem_path, 'problem.md'),
                (evaluator_prompt_path, 'eval_agent_prompt.md'),
            ):
                source = Path(source_name).resolve()
                if source.is_symlink() or not source.is_file():
                    raise WorkspaceError(
                        f'benchmark task file is unavailable: {source}'
                    )
                target = destination / destination_name
                shutil.copy2(source, target)
                target.chmod(0o444)
            # Task inputs land under a fixed, read-only location in both
            # workspaces: agents may read the task but cannot rewrite it.
            destination.chmod(0o555)

    def package_source_bundle(
        self,
        *,
        run_id: str,
        source_subdirectory: str,
    ) -> tuple[Path, str]:
        workspace = self.paths(run_id).beaker.resolve()
        source = (workspace / source_subdirectory).resolve()
        if not source.is_relative_to(workspace) or not source.is_dir():
            raise WorkspaceError(
                f'benchmark source directory is missing: {source_subdirectory}'
            )
        entrypoint = source / 'run.py'
        if entrypoint.is_symlink() or not entrypoint.is_file():
            raise WorkspaceError('benchmark source requires a real run.py')
        destination = self.paths(run_id).shared_artifacts / 'source.zip'
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Deterministic archive (fixed mtime, fixed mode, sorted entries) so
        # the same source tree always produces the same sha256, making the
        # bundle digest meaningful across submissions.
        with zipfile.ZipFile(
            destination,
            mode='w',
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for path in sorted(source.rglob('*')):
                if path.is_symlink():
                    raise WorkspaceError(
                        f'benchmark source cannot contain symlinks: {path}'
                    )
                if path.is_file():
                    info = zipfile.ZipInfo(path.relative_to(source).as_posix())
                    info.date_time = (1980, 1, 1, 0, 0, 0)
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, path.read_bytes())
        digest = sha256(destination.read_bytes()).hexdigest()
        return destination, digest

    def copy_contract_candidate_for_review(
        self,
        *,
        run_id: str,
        source: Path,
        contract_id: str,
        version: str,
        digest: str,
    ) -> Path:
        source = source.resolve()
        if source.is_symlink() or not source.is_dir():
            raise WorkspaceError('sealed contract candidate is not a directory')
        destination = (
            self.paths(run_id).honeydew
            / 'contract-candidate-review'
            / contract_id
            / version
            / digest
        )
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
        # The reviewer sees exactly the sealed bytes (digest-named path, made
        # read-only after copy), not a freshly copied tree that could diverge.
        for path in destination.rglob('*'):
            path.chmod(0o555 if path.is_dir() else 0o444)
        return destination
