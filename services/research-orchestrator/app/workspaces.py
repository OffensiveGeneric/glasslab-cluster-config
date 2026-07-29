from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess

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
        if destination.exists():
            if not (destination / '.git').exists():
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
        for workspace in (
            self.paths(run_id).beaker,
            self.paths(run_id).honeydew,
        ):
            target = workspace / 'program.md'
            shutil.copy2(protocol, target)
            target.chmod(0o444)
