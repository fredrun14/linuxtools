"""Tests du chemin réel de ConsumerBumper (T7), exécuteur scripté."""

from __future__ import annotations

import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandResult
from linuxtools.devtools.bumper import ConsumerBumper
from linuxtools.devtools.discovery import Consumer
from linuxtools.devtools.report import BumpOutcome, Status
from tests.unit.test_devtools_bumper_probes import (
    _BRANCHE,
    _CO_AUTHOR,
    _executor,
    _pyproject,
)

if TYPE_CHECKING:
    from tests.unit.scripted_executor import Call, ScriptedExecutor

_SHA = "0123456789abcdef0123456789abcdef01234567"
_LOCK_OLD = (
    "version = 1\nrevision = 3\n\n"
    '[[package]]\nname = "linuxtools"\nversion = "2.10.0"\n'
    'source = { git = "https://x/linuxtools.git?tag=v2.10.0#a" }\n\n'
    '[[package]]\nname = "pytest"\nversion = "9.0"\n'
    'source = { registry = "https://pypi.org/simple" }\n'
)
_LOCK_NEW = _LOCK_OLD.replace("v2.10.0", "v2.11.1").replace("2.10.0", "2.11.1")
_LOCK_BAD = _LOCK_NEW.replace('version = "9.0"', 'version = "9.1"')
_CHANGELOG = "# Changelog\n\n## [Non publié]\n\n## [1.0.0] - 2026-01-01\n"


@dataclass
class _Run:
    """Ce que le scénario observe pendant la montée."""

    ex: ScriptedExecutor
    bumper: ConsumerBumper
    consumer: Consumer
    wt: Path | None = None
    tmp: Path | None = None
    tmp_mode: int | None = None
    committed_pyproject: str = ""
    committed_changelog: str = ""
    commit_env: dict[str, str] | None = None
    commit_stdin: str | None = None
    check_env: dict[str, str] | None = None
    check_cwd: str | None = None
    logger: MagicMock = field(default_factory=MagicMock)
    extra: dict[str, object] = field(default_factory=dict)

    def outcome(self) -> BumpOutcome:
        return self.bumper.bump(self.consumer)

    def argvs(self) -> list[tuple[str, ...]]:
        return self.ex.argvs()

    def index(self, *prefix: str) -> int:
        for i, argv in enumerate(self.argvs()):
            if argv[: len(prefix)] == prefix:
                return i
        raise AssertionError(f"absent : {prefix}")

    def has(self, *prefix: str) -> bool:
        return any(a[: len(prefix)] == prefix for a in self.argvs())


def _scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    push: bool = True,
    lock: tuple[str, str] | None = None,
    changelog: bool = False,
    check_rc: dict[str, int] | None = None,
    diff_tree: str | None = None,
    push_rc: int = 0,
    remote_sha: str = _SHA,
    commit_rc: int = 0,
    worktree_rc: int = 0,
    fetch_rc: int = 0,
) -> _Run:
    """Scénario nominal du chemin réel ; les paramètres le dégradent."""
    sandbox = tmp_path / "tmp"
    sandbox.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sandbox))
    ex = _executor()
    if lock:
        ex.on(
            "git",
            "ls-tree",
            "--name-only",
            "origin/main",
            "uv.lock",
            stdout="uv.lock\n",
        )
    if changelog:
        ex.on(
            "git",
            "ls-tree",
            "--name-only",
            "origin/main",
            "CHANGELOG.md",
            stdout="CHANGELOG.md\n",
        )
        ex.on("git", "show", "origin/main:CHANGELOG.md", stdout=_CHANGELOG)
    logger = MagicMock()
    bumper = ConsumerBumper(
        ex,
        logger,
        tag="v2.11.1",
        root=tmp_path,
        dry_run=False,
        push=push,
        co_author=_CO_AUTHOR,
    )
    run = _Run(ex, bumper, Consumer("app", tmp_path / "app"), logger=logger)
    rc = check_rc or {}

    def worktree_add(call: Call) -> None:
        if worktree_rc:
            return
        wt = Path(call.argv[6])
        run.wt = wt
        run.tmp = wt.parent
        run.tmp_mode = stat.S_IMODE(wt.parent.stat().st_mode)
        wt.mkdir()
        (wt / "pyproject.toml").write_text(_pyproject())
        if changelog:
            (wt / "CHANGELOG.md").write_text(_CHANGELOG)
        if lock:
            (wt / "uv.lock").write_text(lock[0])
        for name in ("pytest", "mypy"):

            def check(c: Call, name: str = name) -> None:
                run.check_env, run.check_cwd = c.env, c.cwd

            ex.on(
                str(wt.parent / "venv" / "bin" / name),
                rc=rc.get(name, 0),
                stderr=f"{name} KO\n" if rc.get(name) else "",
                handler=check,
            )

    def uv_lock(call: Call) -> None:
        assert run.wt is not None and lock is not None
        (run.wt / "uv.lock").write_text(lock[1])

    def commit(call: Call) -> None:
        assert run.wt is not None
        run.committed_pyproject = (run.wt / "pyproject.toml").read_text()
        if changelog:
            run.committed_changelog = (run.wt / "CHANGELOG.md").read_text()
        run.commit_env, run.commit_stdin = call.env, call.stdin

    ex.on("git", "fetch", rc=fetch_rc, stderr="réseau" if fetch_rc else "")
    ex.on(
        "git",
        "worktree",
        "add",
        rc=worktree_rc,
        stderr="pris" if worktree_rc else "",
        handler=worktree_add,
    )
    ex.on("git", "worktree", "remove")
    ex.on("git", "worktree", "prune")
    ex.on("git", "branch", "-D")
    ex.on("uv", "lock", handler=uv_lock if lock else None)
    ex.on("uv", "sync")
    ex.on("git", "add")
    ex.on(
        "git",
        "commit",
        rc=commit_rc,
        stderr="hook rouge" if commit_rc else "",
        handler=commit,
    )
    expected = ["pyproject.toml"]
    if changelog:
        expected.append("CHANGELOG.md")
    if lock:
        expected.append("uv.lock")
    ex.on(
        "git",
        "diff-tree",
        stdout=(
            diff_tree if diff_tree is not None else "\n".join(expected) + "\n"
        ).replace("\n", "\0"),
    )
    ex.on("git", "rev-parse", "HEAD", stdout=_SHA + "\n")
    ex.on("git", "push", rc=push_rc, stderr="refusé" if push_rc else "")
    ex.on(
        "git",
        "ls-remote",
        "origin",
        f"refs/heads/{_BRANCHE}",
        stdout=f"{remote_sha}\trefs/heads/{_BRANCHE}\n" if remote_sha else "",
    )
    return run


def test_chemin_nominal_pousse_apres_checks_verts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch)

    outcome = run.outcome()

    assert outcome.status is Status.POUSSE
    assert outcome.old_pin == "v2.10.0"
    assert "pytest" in outcome.checks
    assert "mypy" in outcome.checks
    assert run.wt is not None
    ordre = [
        run.index("git", "fetch", "--no-tags", "origin", "main"),
        run.index("git", "worktree", "add", "--no-track", "-b", _BRANCHE),
        run.index("uv", "sync"),
        run.index(str(run.wt.parent / "venv" / "bin" / "pytest")),
        run.index(str(run.wt.parent / "venv" / "bin" / "mypy")),
        run.index("git", "add"),
        run.index("git", "commit"),
        run.index("git", "diff-tree"),
        run.index("git", "push"),
        run.index("git", "worktree", "remove"),
    ]
    assert ordre == sorted(ordre)
    assert (
        "git",
        "push",
        "origin",
        f"refs/heads/{_BRANCHE}:refs/heads/{_BRANCHE}",
    ) in run.argvs()
    assert "linuxtools.git@v2.11.1" in run.committed_pyproject
    assert "v2.10.0" not in run.committed_pyproject
    assert run.tmp is not None and not run.tmp.exists()
    assert not run.has("git", "branch", "-D")


def test_worktree_cree_depuis_origin_dans_un_tmp_prive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch)

    run.outcome()

    assert run.tmp_mode == 0o700
    add = next(
        c for c in run.ex.calls if c.argv[:3] == ("git", "worktree", "add")
    )
    assert add.argv[-1] == "origin/main"
    assert add.cwd == str(run.consumer.path)
    assert not add.probe


def test_message_de_commit_par_stdin_sans_no_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch)

    run.outcome()

    commit = next(c for c in run.ex.calls if c.argv[:2] == ("git", "commit"))
    assert commit.argv == ("git", "commit", "-F", "-")
    assert run.commit_stdin == (
        "chore(deps): épingler linuxtools en v2.11.1\n\n"
        f"Co-Authored-By: {_CO_AUTHOR}\n"
    )
    assert run.commit_env is not None
    assert run.commit_env["UV_FROZEN"] == "1"
    assert not any("--no-verify" in argv for argv in run.argvs())


def test_checks_lances_dans_le_venv_jamais_uv_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch)

    run.outcome()

    assert run.wt is not None
    assert not run.has("uv", "run")
    mypy = next(
        c
        for c in run.ex.calls
        if c.argv[0] == str(run.wt.parent / "venv" / "bin" / "mypy")
    )
    assert mypy.argv[1:] == ("src/app/",)
    assert mypy.cwd == str(run.wt)
    sync = next(c for c in run.ex.calls if c.argv[:2] == ("uv", "sync"))
    assert sync.argv == ("uv", "sync", "--no-sources", "--extra", "dev")
    venv = str(run.wt.parent / "venv")
    for env in (sync.env, run.check_env):
        assert env is not None
        assert env["UV_PROJECT_ENVIRONMENT"] == venv
        assert env["VIRTUAL_ENV"] == venv
        assert env["UV_NO_SOURCES"] == "1"
        assert "UV_FROZEN" not in env


def test_check_en_echec_annule_et_supprime_la_branche(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, check_rc={"mypy": 1})

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    assert "mypy KO" in outcome.detail
    assert "pytest" in outcome.checks
    assert not run.has("git", "commit")
    assert not run.has("git", "push")
    assert ("git", "branch", "-D", _BRANCHE) in run.argvs()
    assert run.has("git", "worktree", "remove", "--force")
    assert run.tmp is not None and not run.tmp.exists()


def test_lock_hors_fermeture_echoue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, lock=(_LOCK_OLD, _LOCK_BAD))

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    assert "pytest" in outcome.detail
    assert not run.has("uv", "sync")
    assert ("git", "branch", "-D", _BRANCHE) in run.argvs()


def test_lock_suivi_regenere_et_commite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, lock=(_LOCK_OLD, _LOCK_NEW))

    outcome = run.outcome()

    assert outcome.status is Status.POUSSE
    assert ("uv", "lock", "--no-sources") in run.argvs()
    sync = next(a for a in run.argvs() if a[:2] == ("uv", "sync"))
    assert "--locked" in sync
    assert run.index("uv", "lock") < run.index("uv", "sync")
    assert ("git", "add", "--", "pyproject.toml", "uv.lock") in run.argvs()


def test_lock_non_suivi_ni_regenere_ni_ajoute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch)

    run.outcome()

    assert not run.has("uv", "lock")
    sync = next(a for a in run.argvs() if a[:2] == ("uv", "sync"))
    assert "--locked" not in sync
    assert ("git", "add", "--", "pyproject.toml") in run.argvs()


def test_changelog_modifie_et_ajoute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, changelog=True)

    run.outcome()

    assert (
        "- chore(deps): `linuxtools` épinglée en v2.11.1 (était v2.10.0)"
        in run.committed_changelog
    )
    assert (
        "git",
        "add",
        "--",
        "pyproject.toml",
        "CHANGELOG.md",
    ) in run.argvs()


def test_changement_d_en_tete_du_lock_journalise_un_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nouveau = _LOCK_NEW.replace("revision = 3", "revision = 4")
    run = _scenario(tmp_path, monkeypatch, lock=(_LOCK_OLD, nouveau))

    outcome = run.outcome()

    assert outcome.status is Status.POUSSE
    logger = run.bumper._logger  # noqa: SLF001
    assert isinstance(logger, MagicMock)
    assert "revision" in logger.log_warning.call_args[0][0]


def test_commit_ne_touche_que_les_fichiers_attendus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(
        tmp_path, monkeypatch, diff_tree="pyproject.toml\nsecret.txt\n"
    )

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    assert "secret.txt" in outcome.detail
    assert not run.has("git", "push")
    assert ("git", "branch", "-D", _BRANCHE) in run.argvs()
    assert not any(
        a[:3] in {("git", "add", "-A"), ("git", "add", ".")}
        for a in run.argvs()
    )


def test_commit_refuse_par_un_hook_echoue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, commit_rc=1)

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    assert "hook rouge" in outcome.detail
    assert ("git", "branch", "-D", _BRANCHE) in run.argvs()


def test_push_en_erreur_mais_sha_correct_vaut_pousse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, push_rc=1)

    outcome = run.outcome()

    assert outcome.status is Status.POUSSE
    assert not run.has("git", "branch", "-D")


@pytest.mark.parametrize(
    ("push_rc", "remote_sha"),
    [(1, ""), (1, "f" * 40), (0, "f" * 40)],
)
def test_push_non_verifie_donne_push_echoue_et_garde_la_branche(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    push_rc: int,
    remote_sha: str,
) -> None:
    run = _scenario(
        tmp_path, monkeypatch, push_rc=push_rc, remote_sha=remote_sha
    )

    outcome = run.outcome()

    assert outcome.status is Status.PUSH_ECHOUE
    assert not run.has("git", "branch", "-D")
    assert run.has("git", "worktree", "remove", "--force")
    assert run.tmp is not None and not run.tmp.exists()


def test_no_push_donne_commite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, push=False)

    outcome = run.outcome()

    assert outcome.status is Status.COMMITE
    assert not run.has("git", "push")
    assert not run.has("git", "branch", "-D")


def test_fetch_en_echec_ne_cree_rien(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, fetch_rc=1)

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    assert "réseau" in outcome.detail
    assert not run.has("git", "worktree")
    assert not run.has("git", "branch")


def test_worktree_add_en_echec_ne_supprime_pas_de_branche(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, worktree_rc=128)

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    assert "pris" in outcome.detail
    assert not run.has("git", "branch", "-D")
    assert list((tmp_path / "tmp").iterdir()) == []


def test_worktree_add_en_echec_apres_creation_de_branche_la_supprime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, worktree_rc=128)

    def branch_exists_after_add(call: Call) -> CommandResult:
        # `worktree add -b` crée la branche avant d'échouer au checkout.
        added = any(a[:3] == ("git", "worktree", "add") for a in run.argvs())
        rc = 0 if added else 1
        return CommandResult(call.argv, rc, "", "", rc == 0, 0.0)

    run.ex.on(
        "git",
        "rev-parse",
        "--verify",
        "--quiet",
        handler=branch_exists_after_add,
    )

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    assert ("git", "branch", "-D", _BRANCHE) in run.argvs()


def test_echec_du_nettoyage_est_journalise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, check_rc={"mypy": 1})
    run.ex.on("git", "worktree", "remove", rc=1, stderr="wt verrouillé")
    run.ex.on("git", "branch", "-D", rc=1, stderr="branche tenue")

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    messages = " ".join(str(c) for c in run.logger.log_warning.mock_calls)
    assert "wt verrouillé" in messages
    assert "branche tenue" in messages


def test_worktree_prune_avant_la_suppression_de_la_branche(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`worktree remove` raté puis rmtree : le worktree est « prunable »."""
    run = _scenario(tmp_path, monkeypatch, check_rc={"mypy": 1})
    run.ex.on("git", "worktree", "remove", rc=1, stderr="wt verrouillé")

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    remove = run.index("git", "worktree", "remove")
    prune = run.index("git", "worktree", "prune")
    delete = run.index("git", "branch", "-D")
    assert remove < prune < delete


def test_pas_de_prune_quand_la_branche_est_conservee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch, push_rc=1, remote_sha="")

    run.outcome()

    assert not run.has("git", "worktree", "prune")


def test_nettoyage_worktree_meme_en_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _scenario(tmp_path, monkeypatch)

    def boom(call: Call) -> None:
        raise OSError("disque plein")

    run.ex.on("uv", "sync", handler=boom)

    outcome = run.outcome()

    assert outcome.status is Status.ECHEC
    assert "disque plein" in outcome.detail
    assert run.has("git", "worktree", "remove", "--force")
    assert ("git", "branch", "-D", _BRANCHE) in run.argvs()
    assert run.tmp is not None and not run.tmp.exists()
