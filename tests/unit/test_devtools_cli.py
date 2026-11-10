"""Tests de la CLI ``linuxtools-dev bump-consumers`` (T8)."""

from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.commands.runner import LinuxCommandExecutor
from linuxtools.devtools import cli
from linuxtools.devtools.cli import BumpConsumersCommand
from linuxtools.logging.console_logger import ConsoleLogger
from tests.unit.scripted_executor import Call, ScriptedExecutor
from tests.unit.test_devtools_bumper_probes import (
    _FORGEJO,
    _executor,
    _pyproject,
)

if TYPE_CHECKING:
    from linuxtools.logging.base import Logger

_PIN = "linuxtools @ git+https://git.ricfasohel.fr/fred/linuxtools.git@v1.0.0"


@pytest.fixture(autouse=True)
def _non_root_et_env_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les tests tournent en root en CI : geteuid est mocké."""
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    for name in cli.FORBIDDEN_ENV:
        monkeypatch.delenv(name, raising=False)


def _repos(root: Path, *noms: str) -> None:
    """Crée de faux dépôts consommateurs dans ``root``."""
    for nom in noms:
        (root / nom / ".git").mkdir(parents=True)
        (root / nom / "pyproject.toml").write_text(
            f'[project]\nname = "{nom}"\ndependencies = ["{_PIN}"]\n'
        )


def _base(root: Path, pyproject: str | None = None) -> ScriptedExecutor:
    """Exécuteur nominal : sondes de l'outil + sondes du bumper."""
    ex = _executor(pyproject)
    ex.on("git", "remote", "get-url", "origin", stdout=_FORGEJO + "\n")
    ex.on("git", "--version", stdout="git version 2.56.0\n")
    ex.on("uv", "--version", stdout="uv 0.13.5\n")
    ex.on("git", "ls-remote", "--tags", stdout="abc\trefs/tags/v2.11.1\n")
    return ex


def _commande(ex: CommandExecutor, tmp_path: Path) -> BumpConsumersCommand:
    """Commande dont l'exécuteur est injecté."""

    def factory(logger: Logger, dry_run: bool) -> CommandExecutor:
        return ex

    return BumpConsumersCommand(
        executor_factory=factory, linuxtools_dir=tmp_path / "lt"
    )


def _args(
    commande: BumpConsumersCommand, root: Path, *extra: str
) -> argparse.Namespace:
    """Parse les arguments comme le ferait CliApplication."""
    parser = argparse.ArgumentParser(prog="linuxtools-dev")
    sub = parser.add_subparsers(dest="command", required=True)
    commande.register(sub)
    return parser.parse_args(["bump-consumers", *extra, "--root", str(root)])


def _lancer(ex: CommandExecutor, tmp_path: Path, *argv: str) -> int:
    """Exécute la commande ; retourne le code de sortie."""
    commande = _commande(ex, tmp_path)
    args = _args(commande, tmp_path / "projets", *argv)
    with pytest.raises(SystemExit) as exc:
        commande.execute(args)
    assert isinstance(exc.value.code, int)
    return exc.value.code


@pytest.fixture
def projets(tmp_path: Path) -> Path:
    racine = tmp_path / "projets"
    racine.mkdir()
    return racine


def test_refuse_root(
    tmp_path: Path,
    projets: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    ex = _base(projets)

    code = _lancer(ex, tmp_path, "--dry-run", "v2.11.1")

    assert code == 2
    assert "root" in capsys.readouterr().err
    assert ex.calls == []


# Liste littérale (plan, T8) : indépendante de `cli.FORBIDDEN_ENV`, sinon
# retirer une variable de la constante retirerait aussi son test.
@pytest.mark.parametrize(
    "nom",
    [
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "UV_FROZEN",
        "UV_LOCKED",
        "UV_NO_SYNC",
        "UV_PROJECT",
        "UV_PROJECT_ENVIRONMENT",
    ],
)
def test_refuse_variable_uv_frozen(
    tmp_path: Path,
    projets: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    nom: str,
) -> None:
    monkeypatch.setenv(nom, "1")
    ex = _base(projets)

    code = _lancer(ex, tmp_path, "--dry-run", "v2.11.1")

    assert code == 2
    assert nom in capsys.readouterr().err
    assert ex.calls == []


@pytest.mark.parametrize(
    "tag", ["v2.11", "2.11.1", "v2.11.1; rm", "v2.11.1\n", "v2.11.1-rc1"]
)
def test_refuse_tag_invalide(
    tmp_path: Path,
    projets: Path,
    capsys: pytest.CaptureFixture[str],
    tag: str,
) -> None:
    ex = _base(projets)

    code = _lancer(ex, tmp_path, "--dry-run", tag)

    assert code == 2
    assert "tag" in capsys.readouterr().err
    assert ex.calls == []


def test_refuse_tag_absent_du_depot_linuxtools(
    tmp_path: Path,
    projets: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ex = _base(projets)
    ex.on("git", "ls-remote", "--tags", stdout="")

    code = _lancer(ex, tmp_path, "--dry-run", "v2.11.1")

    assert code == 2
    assert "n'existe pas" in capsys.readouterr().err
    assert (
        "git",
        "ls-remote",
        "--tags",
        "origin",
        "refs/tags/v2.11.1",
    ) in ex.argvs()
    assert ex.calls[-1].cwd == str(tmp_path / "lt")


def test_refuse_origin_de_linuxtools_hors_forgejo(
    tmp_path: Path,
    projets: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ex = _base(projets)

    def miroir(call: Call) -> CommandResult | None:
        if call.cwd != str(tmp_path / "lt"):
            return None
        url = "https://github.com/fred/linuxtools.git"
        return CommandResult(call.argv, 0, url + "\n", "", True, 0.0)

    ex.on("git", "remote", "get-url", "origin", handler=miroir)

    code = _lancer(ex, tmp_path, "--dry-run", "v2.11.1")

    assert code == 2
    assert "git.ricfasohel.fr" in capsys.readouterr().err
    assert not any(a[:3] == ("git", "ls-remote", "--tags") for a in ex.argvs())


def test_option_linuxtools_dir_designe_le_depot_du_tag(
    tmp_path: Path, projets: Path
) -> None:
    ex = _base(projets)
    autre = tmp_path / "ailleurs"

    code = _lancer(
        ex, tmp_path, "--dry-run", "--linuxtools-dir", str(autre), "v2.11.1"
    )

    assert code == 0
    cwds = {
        c.cwd for c in ex.calls if c.argv[:3] == ("git", "ls-remote", "--tags")
    }
    assert cwds == {str(autre)}


def _faux_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pyproject: str | None,
    *,
    git: bool = True,
) -> Path:
    """Place `cli.__file__` dans un faux dépôt `tmp_path/depot`."""
    depot = tmp_path / "depot"
    fichier = depot / "src" / "linuxtools" / "devtools" / "cli.py"
    fichier.parent.mkdir(parents=True)
    if pyproject is not None:
        (depot / "pyproject.toml").write_text(pyproject)
    if git:
        (depot / ".git").mkdir()
    monkeypatch.setattr(cli, "__file__", str(fichier))
    return depot


def _sans_option(
    ex: ScriptedExecutor, projets: Path
) -> tuple[BumpConsumersCommand, argparse.Namespace]:
    """Commande sans `linuxtools_dir` injecté, ni option."""
    commande = BumpConsumersCommand(
        executor_factory=lambda logger, dry_run: ex
    )
    return commande, _args(commande, projets, "--dry-run", "v2.11.1")


def test_checkout_detecte_sert_de_depot_par_defaut(
    tmp_path: Path,
    projets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    depot = _faux_cli(
        tmp_path, monkeypatch, '[project]\nname = "linuxtools"\n'
    )
    ex = _base(projets)
    commande, args = _sans_option(ex, projets)

    with pytest.raises(SystemExit) as exc:
        commande.execute(args)

    assert exc.value.code == 0
    cwds = {
        c.cwd for c in ex.calls if c.argv[:3] == ("git", "ls-remote", "--tags")
    }
    assert cwds == {str(depot)}


@pytest.mark.parametrize(
    ("pyproject", "git"),
    [
        (None, True),
        ("[project\n", True),
        ('[project]\nname = "autre"\n', True),
        ('[project]\nname = "linuxtools"\n', False),
    ],
    ids=["sans-pyproject", "toml-invalide", "autre-nom", "sans-git"],
)
def test_hors_checkout_sans_option_erreur_claire(
    tmp_path: Path,
    projets: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pyproject: str | None,
    git: bool,
) -> None:
    _faux_cli(tmp_path, monkeypatch, pyproject, git=git)
    ex = _base(projets)
    commande, args = _sans_option(ex, projets)

    with pytest.raises(SystemExit) as exc:
        commande.execute(args)

    assert exc.value.code == 2
    assert "--linuxtools-dir" in capsys.readouterr().err
    assert not any(a[:3] == ("git", "ls-remote", "--tags") for a in ex.argvs())


def test_refuse_tag_si_ls_remote_echoue(tmp_path: Path, projets: Path) -> None:
    ex = _base(projets)
    ex.on("git", "ls-remote", "--tags", rc=128, stderr="réseau")

    assert _lancer(ex, tmp_path, "--dry-run", "v2.11.1") == 2


@pytest.mark.parametrize(
    "co_author",
    ["x\ny <a@b.c>", "sans-adresse", "<a@b.c>", "X <a@b.c> Y", "X <a b@c.d>"],
)
def test_refuse_co_author_invalide(
    tmp_path: Path,
    projets: Path,
    capsys: pytest.CaptureFixture[str],
    co_author: str,
) -> None:
    ex = _base(projets)

    code = _lancer(
        ex, tmp_path, "--dry-run", "--co-authored-by", co_author, "v2.11.1"
    )

    assert code == 2
    assert "co-auteur" in capsys.readouterr().err


@pytest.mark.parametrize(
    "version", ["git version 2.31.9", "git version 1.9", "bizarre"]
)
def test_refuse_git_trop_ancien_ou_illisible(
    tmp_path: Path, projets: Path, version: str
) -> None:
    ex = _base(projets)
    ex.on("git", "--version", stdout=version + "\n")

    assert _lancer(ex, tmp_path, "--dry-run", "v2.11.1") == 2


def test_accepte_git_2_32(tmp_path: Path, projets: Path) -> None:
    ex = _base(projets)
    ex.on("git", "--version", stdout="git version 2.32.0\n")

    assert _lancer(ex, tmp_path, "--dry-run", "v2.11.1") == 0


def test_refuse_git_absent(tmp_path: Path, projets: Path) -> None:
    ex = _base(projets)
    ex.on("git", "--version", rc=-1, stderr="introuvable")

    assert _lancer(ex, tmp_path, "--dry-run", "v2.11.1") == 2


def test_refuse_uv_absent(
    tmp_path: Path,
    projets: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ex = _base(projets)
    ex.on("uv", "--version", rc=-1, stderr="introuvable")

    code = _lancer(ex, tmp_path, "--dry-run", "v2.11.1")

    assert code == 2
    assert "uv" in capsys.readouterr().err


def test_refuse_racine_inexistante(tmp_path: Path) -> None:
    ex = _base(tmp_path)

    commande = _commande(ex, tmp_path)
    args = _args(commande, tmp_path / "absent", "--dry-run", "v2.11.1")
    with pytest.raises(SystemExit) as exc:
        commande.execute(args)

    assert exc.value.code == 2


def test_nom_inconnu_donne_exit_2(
    tmp_path: Path,
    projets: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repos(projets, "a")
    ex = _base(projets)

    code = _lancer(ex, tmp_path, "--dry-run", "--only", "fantome", "v2.11.1")

    assert code == 2
    assert "fantome" in capsys.readouterr().err


def test_only_et_exclude_exclusifs_par_argparse(
    tmp_path: Path, projets: Path
) -> None:
    commande = _commande(_base(projets), tmp_path)

    with pytest.raises(SystemExit) as exc:
        _args(commande, projets, "--only", "a", "--exclude", "b", "v2.11.1")

    assert exc.value.code == 2


def test_un_echec_n_arrete_pas_les_suivants_et_exit_1(
    tmp_path: Path,
    projets: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repos(projets, "a", "b")
    ex = _base(projets)

    def origine(call: Call) -> CommandResult | None:
        if call.cwd is not None and call.cwd.endswith("/a"):
            return CommandResult(
                call.argv, 0, "https://github.com/f/a.git\n", "", True, 0.0
            )
        return None

    ex.on(
        "git",
        "remote",
        "get-url",
        "--all",
        "origin",
        stdout=_FORGEJO + "\n",
        handler=origine,
    )

    code = _lancer(ex, tmp_path, "--dry-run", "v2.11.1")

    sortie = capsys.readouterr().out
    assert code == 1
    assert "REFUSÉ" in sortie
    assert "SIMULÉ" in sortie
    lignes = {ligne.split()[0]: ligne for ligne in sortie.splitlines()[2:4]}
    assert "REFUSÉ" in lignes["a"]
    assert "SIMULÉ" in lignes["b"]


def test_aucun_consommateur_exit_0(
    tmp_path: Path,
    projets: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _lancer(_base(projets), tmp_path, "--dry-run", "v2.11.1")

    assert code == 0
    assert "aucun consommateur" in capsys.readouterr().out


def test_dry_run_sans_journal_fichier(
    tmp_path: Path,
    projets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs = tmp_path / "logs"
    monkeypatch.setattr(cli, "default_log_dir", lambda _app: logs)
    _repos(projets, "a")

    code = _lancer(_base(projets), tmp_path, "--dry-run", "v2.11.1")

    assert code == 0
    assert not logs.exists()


def test_execution_reelle_ecrit_un_journal(
    tmp_path: Path,
    projets: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs = tmp_path / "logs"
    monkeypatch.setattr(cli, "default_log_dir", lambda _app: logs)
    _repos(projets, "a")
    ex = _base(projets, _pyproject("v2.11.1"))
    ex.on("git", "fetch")

    code = _lancer(ex, tmp_path, "v2.11.1")

    assert code == 0
    journaux = list(logs.glob("bump-consumers-*.log"))
    assert len(journaux) == 1


def test_options_par_defaut_et_no_push(tmp_path: Path) -> None:
    commande = _commande(ScriptedExecutor(), tmp_path)

    defaut = _args(commande, tmp_path, "v2.11.1")
    explicite = _args(
        commande, tmp_path, "--no-push", "--only", "a", "v2.11.1"
    )

    assert defaut.no_push is False
    assert defaut.dry_run is False
    assert defaut.co_author == "Claude Sonnet 5.5 <noreply@anthropic.com>"
    assert explicite.no_push is True
    assert explicite.only == ["a"]


def test_racine_par_defaut_dans_le_home() -> None:
    commande = BumpConsumersCommand()
    parser = argparse.ArgumentParser()
    commande.register(parser.add_subparsers(dest="command"))

    args = parser.parse_args(["bump-consumers", "v2.11.1"])

    assert args.root == Path("~/PycharmProjects").expanduser()


def test_nom_de_la_commande() -> None:
    assert BumpConsumersCommand().name == "bump-consumers"


def test_executeur_par_defaut_est_un_linuxcommandexecutor() -> None:
    commande = BumpConsumersCommand()

    executor = commande.make_executor(ConsoleLogger(), True)

    assert isinstance(executor, LinuxCommandExecutor)


def test_main_affiche_l_aide(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["linuxtools-dev", "--help"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    assert "bump-consumers" in capsys.readouterr().out


def test_python_m_linuxtools_devtools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["linuxtools-dev", "--help"])

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("linuxtools.devtools", run_name="__main__")

    assert exc.value.code == 0
