"""Test d'intégration de ConsumerBumper avec un vrai ``git`` (T9).

Origin nu et dépôt consommateur dans ``tmp_path``, ``uv`` bouchonné par
un script placé en tête du ``PATH`` : aucun accès réseau, aucun push
vers Forgejo. Vérifie ce qu'un exécuteur scripté ne peut pas prouver :

- le worktree est créé puis supprimé, le checkout de l'utilisateur
  (branche, fichiers modifiés) reste intact ;
- la branche distante existe avec le SHA du commit ;
- l'hypothèse de la conception : ``core.hooksPath=.githooks`` relatif se
  résout à la racine du **worktree** (les hooks versionnés y tournent) ;
- le dry-run n'écrit rien (ni dépôt, ni origin, ni dossier temporaire).

Écrit après T1-T8, sans TDD : test de bout en bout, pas un cycle
red-green sur du comportement nouveau.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandResult
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.devtools.bumper import ConsumerBumper
from linuxtools.devtools.discovery import Consumer
from linuxtools.devtools.report import Status

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.integration

_FORGEJO = "https://git.ricfasohel.fr/fred/app.git"
_BRANCH = "chore/pin-linuxtools-2-11-1"
_CO_AUTHOR = "Claude Sonnet 5.5 <noreply@anthropic.com>"
_PYPROJECT = """\
[project]
name = "app"
version = "1.0"
dependencies = [
    "linuxtools @ git+https://git.ricfasohel.fr/fred/linuxtools.git@v2.10.0",
]

[tool.linuxtools.consumer]
sync-args = ["--extra", "dev"]
checks = [["pytest"], ["mypy", "src/app/"]]
"""
# Hook versionné : consigne où il tourne (racine du worktree attendue).
_PRE_COMMIT = """\
#!/usr/bin/env bash
set -euo pipefail
{
  echo "toplevel=$(git rev-parse --show-toplevel)"
  echo "hookdir=$(cd "$(dirname "$0")" && pwd -P)"
} > "$HOOK_MARKER"
"""
# Comme le vrai post-commit, mais synchrone : test déterministe.
_POST_COMMIT = """\
#!/usr/bin/env bash
branch=$(git symbolic-ref --quiet --short HEAD) || exit 0
unset GIT_INDEX_FILE GIT_PREFIX
git push origin "$branch" >/dev/null 2>&1 || true
exit 0
"""
_UV_STUB = """\
#!/usr/bin/env bash
echo "uv $* NO_SOURCES=${UV_NO_SOURCES:-}" >> "$UV_STUB_LOG"
case "$1" in
  --version) echo "uv 0.0.0" ;;
  sync)
    mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"
    for tool in pytest mypy; do
      printf '#!/bin/sh\\nexit 0\\n' > "$UV_PROJECT_ENVIRONMENT/bin/$tool"
      chmod +x "$UV_PROJECT_ENVIRONMENT/bin/$tool"
    done ;;
  *) echo "uv: commande inattendue $*" >&2; exit 2 ;;
esac
"""


class _ForgejoView(LinuxCommandExecutor):
    """Exécuteur réel qui présente l'origine locale comme Forgejo.

    Le bumper refuse tout ``origin`` hors ``git.ricfasohel.fr`` ; seule
    la lecture de l'URL est réécrite, les push vont bien vers le dépôt
    nu de ``tmp_path``.
    """

    def run(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
        probe: bool = False,
        stdin: str | None = None,
    ) -> CommandResult:
        if command[:3] == ["git", "remote", "get-url"]:
            return CommandResult(
                tuple(command), 0, _FORGEJO + "\n", "", True, 0.0
            )
        return super().run(command, env, cwd, timeout, probe, stdin)


def _git(cwd: Path, *args: str) -> str:
    """Lance git (environnement du test) et retourne stdout."""
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@dataclass
class _Env:
    """Dépôts et chemins du scénario."""

    origin: Path
    app: Path
    sandbox: Path
    marker: Path
    uv_log: Path


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Env:
    """Origin nu + consommateur sur une feature branch sale + uv factice."""
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sandbox))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(_UV_STUB)
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    uv_log = tmp_path / "uv.log"
    marker = tmp_path / "hook.marker"
    monkeypatch.setenv("UV_STUB_LOG", str(uv_log))
    monkeypatch.setenv("HOOK_MARKER", str(marker))

    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    projets = tmp_path / "projets"
    app = projets / "app"
    app.mkdir(parents=True)
    _git(app, "init", "-b", "main")
    _git(app, "config", "user.name", "Test")
    _git(app, "config", "user.email", "test@example.com")
    _git(app, "remote", "add", "origin", str(origin))
    (app / "pyproject.toml").write_text(_PYPROJECT)
    hooks = app / ".githooks"
    hooks.mkdir()
    for nom, contenu in (
        ("pre-commit", _PRE_COMMIT),
        ("post-commit", _POST_COMMIT),
    ):
        (hooks / nom).write_text(contenu)
        (hooks / nom).chmod(0o755)
    _git(app, "add", ".")
    _git(app, "commit", "-m", "init")
    _git(app, "push", "origin", "main")
    _git(app, "fetch", "origin")
    _git(app, "config", "core.hooksPath", ".githooks")  # relatif
    # Checkout de l'utilisateur : feature branch avec travail en cours.
    _git(app, "switch", "-c", "feature/en-cours")
    (app / "pyproject.toml").write_text(_PYPROJECT + "# brouillon\n")
    (app / "notes.txt").write_text("non suivi\n")
    return _Env(origin, app, sandbox, marker, uv_log)


def _bumper(dry_run: bool, root: Path) -> ConsumerBumper:
    executor = _ForgejoView(dry_run=dry_run)
    return ConsumerBumper(
        executor,
        MagicMock(),
        tag="v2.11.1",
        root=root,
        dry_run=dry_run,
        push=True,
        co_author=_CO_AUTHOR,
    )


def _snapshot(app: Path) -> dict[str, str]:
    """État observable du checkout de l'utilisateur."""
    return {
        "branche": _git(app, "branch", "--show-current"),
        "head": _git(app, "rev-parse", "HEAD"),
        "status": _git(app, "status", "--porcelain"),
        "pyproject": (app / "pyproject.toml").read_text(),
        "branches": _git(app, "branch", "--format=%(refname:short)"),
        "worktrees": _git(app, "worktree", "list", "--porcelain"),
        "main": _git(app, "rev-parse", "main"),
    }


def test_montee_reelle_pousse_la_branche_sans_toucher_au_checkout(
    env: _Env,
) -> None:
    avant = _snapshot(env.app)
    bumper = _bumper(dry_run=False, root=env.app.parent)

    outcome = bumper.bump(Consumer("app", env.app))

    assert outcome.status is Status.POUSSE, outcome.detail
    assert outcome.old_pin == "v2.10.0"
    # Branche distante présente, au SHA du commit local.
    local_sha = _git(env.app, "rev-parse", _BRANCH)
    assert _git(env.origin, "rev-parse", f"refs/heads/{_BRANCH}") == local_sha
    # Contenu du commit : seul le pyproject, tag changé, base origin/main.
    assert _git(env.app, "diff", "--name-only", f"main..{_BRANCH}") == (
        "pyproject.toml"
    )
    pin = _git(env.app, "show", f"{_BRANCH}:pyproject.toml")
    assert "linuxtools.git@v2.11.1" in pin
    assert "brouillon" not in pin
    message = _git(env.app, "log", "-1", "--format=%B", _BRANCH)
    assert message.startswith("chore(deps): épingler linuxtools en v2.11.1")
    assert message.endswith(f"Co-Authored-By: {_CO_AUTHOR}")
    # Checkout de l'utilisateur : seule la branche chore/ est apparue.
    apres = _snapshot(env.app)
    assert apres["branches"].split() == sorted(
        [*avant["branches"].split(), _BRANCH]
    )
    for cle in ("branche", "head", "status", "pyproject", "worktrees", "main"):
        assert apres[cle] == avant[cle], cle
    # Worktree et dossier temporaire supprimés.
    assert list(env.sandbox.iterdir()) == []
    assert "linuxtools-bump" not in _git(env.app, "worktree", "list")


def test_hooks_versionnes_tournent_a_la_racine_du_worktree(
    env: _Env,
) -> None:
    bumper = _bumper(dry_run=False, root=env.app.parent)

    outcome = bumper.bump(Consumer("app", env.app))

    assert outcome.status is Status.POUSSE, outcome.detail
    lignes = dict(
        ligne.split("=", 1) for ligne in env.marker.read_text().splitlines()
    )
    # `core.hooksPath=.githooks` relatif : résolu dans le worktree, pas
    # dans le dépôt principal (hypothèse de la conception).
    assert lignes["toplevel"].endswith("/wt")
    assert "linuxtools-bump-" in lignes["toplevel"]
    assert lignes["hookdir"] == f"{lignes['toplevel']}/.githooks"
    assert str(env.app) not in lignes["hookdir"]


def test_uv_appele_sans_sources_et_checks_dans_le_venv(env: _Env) -> None:
    bumper = _bumper(dry_run=False, root=env.app.parent)

    outcome = bumper.bump(Consumer("app", env.app))

    assert outcome.status is Status.POUSSE, outcome.detail
    assert env.uv_log.read_text().splitlines() == [
        "uv sync --no-sources --extra dev NO_SOURCES=1"
    ]
    assert outcome.checks == "pytest:ok mypy:ok"


def test_check_en_echec_nettoie_tout(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    avant = _snapshot(env.app)
    # Les contrôles factices du venv échouent (premier : pytest).
    stub = env.uv_log.parent / "bin" / "uv"
    stub.write_text(stub.read_text().replace("exit 0", "exit 1", 1))
    bumper = _bumper(dry_run=False, root=env.app.parent)

    outcome = bumper.bump(Consumer("app", env.app))

    assert outcome.status is Status.ECHEC
    assert _snapshot(env.app) == avant
    assert list(env.sandbox.iterdir()) == []
    assert (
        _git(
            env.origin,
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
        )
        == "main"
    )
    assert outcome.checks == "pytest:KO"
    assert not env.marker.exists()


def test_dry_run_sans_effet(env: _Env) -> None:
    avant = _snapshot(env.app)
    origin_avant = _git(env.origin, "for-each-ref")
    bumper = _bumper(dry_run=True, root=env.app.parent)

    outcome = bumper.bump(Consumer("app", env.app))

    assert outcome.status is Status.SIMULE, outcome.detail
    assert _BRANCH in outcome.detail
    assert _snapshot(env.app) == avant
    assert _git(env.origin, "for-each-ref") == origin_avant
    assert list(env.sandbox.iterdir()) == []
    assert not env.uv_log.exists()
    assert not env.marker.exists()


def _branch_sha(env: _Env) -> str:
    return _git(env.app, "rev-parse", _BRANCH)


def test_etat_apres_montee_peut_etre_rejoue_en_a_jour(env: _Env) -> None:
    """Une fois la branche mergée, la montée suivante est « À JOUR »."""
    bumper = _bumper(dry_run=False, root=env.app.parent)
    assert bumper.bump(Consumer("app", env.app)).status is Status.POUSSE
    # Simule le merge de la PR dans origin/main.
    _git(env.origin, "update-ref", "refs/heads/main", _branch_sha(env))
    _git(env.origin, "branch", "-D", _BRANCH)

    outcome = bumper.bump(Consumer("app", env.app))

    assert outcome.status is Status.A_JOUR


# --- T34/F25 : contrôle du contenu de la branche avec un vrai git -------


def _publier_branche_de_bump(
    env: _Env, tmp_path: Path, modifier: Callable[[Path], None]
) -> None:
    """Pousse sur origin une branche de bump que ``modifier`` altère.

    ``main`` reçoit d'abord ``src/x.py`` (contenu de CHANGELOG) pour que la
    branche puisse le renommer ; le pin passe à la version cible.
    """
    clone = tmp_path / "autre"
    _git(tmp_path, "clone", str(env.origin), str(clone))
    _git(clone, "config", "user.name", "Test")
    _git(clone, "config", "user.email", "test@example.com")
    (clone / "src").mkdir()
    (clone / "src" / "x.py").write_text("# Journal\n\ncontenu\n")
    _git(clone, "add", ".")
    _git(clone, "commit", "-m", "ajoute x")
    _git(clone, "push", "origin", "main")
    _git(env.app, "fetch", "origin")
    _git(clone, "switch", "-c", _BRANCH)
    pin = (clone / "pyproject.toml").read_text()
    (clone / "pyproject.toml").write_text(pin.replace("v2.10.0", "v2.11.1"))
    modifier(clone)
    _git(clone, "add", "-A")
    _git(clone, "commit", "-m", "bump")
    _git(clone, "push", "origin", _BRANCHE_REF)


_BRANCHE_REF = f"refs/heads/{_BRANCH}:refs/heads/{_BRANCH}"


def _rejouer(env: _Env) -> tuple[Status, str]:
    outcome = _bumper(dry_run=False, root=env.app.parent).bump(
        Consumer("app", env.app)
    )
    return outcome.status, outcome.detail


@pytest.mark.parametrize("cible", ["CHANGELOG.md", "uv.lock"])
def test_branche_distante_renommage_vers_fichier_attendu_refusee(
    env: _Env, tmp_path: Path, cible: str
) -> None:
    """``git mv src/x.py CHANGELOG.md`` masquait la suppression de x.py."""

    def renommer(clone: Path) -> None:
        _git(clone, "mv", "src/x.py", cible)

    _publier_branche_de_bump(env, tmp_path, renommer)

    status, detail = _rejouer(env)

    assert status is Status.REFUSE, detail
    assert "src/x.py" in detail


def test_branche_distante_nom_avec_espace_cite_en_entier(
    env: _Env, tmp_path: Path
) -> None:
    def ajouter(clone: Path) -> None:
        (clone / "src" / "a b.py").write_text("x\n")

    _publier_branche_de_bump(env, tmp_path, ajouter)

    status, detail = _rejouer(env)

    assert status is Status.REFUSE
    assert "src/a b.py" in detail


def test_branche_distante_suppression_simple_refusee(
    env: _Env, tmp_path: Path
) -> None:
    def supprimer(clone: Path) -> None:
        _git(clone, "rm", "src/x.py")

    _publier_branche_de_bump(env, tmp_path, supprimer)

    status, detail = _rejouer(env)

    assert status is Status.REFUSE
    assert "src/x.py" in detail


def test_branche_distante_fichiers_attendus_en_attente(
    env: _Env, tmp_path: Path
) -> None:
    def changelog(clone: Path) -> None:
        (clone / "CHANGELOG.md").write_text("# Journal\n")

    _publier_branche_de_bump(env, tmp_path, changelog)

    status, detail = _rejouer(env)

    assert status is Status.EN_ATTENTE, detail


def test_commit_avec_fichier_a_espace_inattendu_cite_en_entier(
    env: _Env, tmp_path: Path
) -> None:
    """Un hook qui ajoute « a b.txt » : le nom doit rester entier."""
    clone = tmp_path / "autre"
    _git(tmp_path, "clone", str(env.origin), str(clone))
    _git(clone, "config", "user.name", "Test")
    _git(clone, "config", "user.email", "test@example.com")
    hook = clone / ".githooks" / "pre-commit"
    hook.write_text(
        '#!/usr/bin/env bash\necho x > "a b.txt"\ngit add -- "a b.txt"\n'
    )
    _git(clone, "commit", "-am", "hook")
    _git(clone, "push", "origin", "main")
    _git(env.app, "fetch", "origin")

    status, detail = _rejouer(env)

    assert status is Status.ECHEC
    assert "a b.txt" in detail
