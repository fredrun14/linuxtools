"""Tests de comportement complémentaires pour deploy.venv_release."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandExecutor
from linuxtools.deploy.venv_release import VenvReleaser
from tests.unit.couverture_helpers import cmd_result


@pytest.mark.parametrize("id_etranger", ["app2-20260901-000000-000000", "../x", "x"])
def test_purge_ignore_les_ids_etrangers_renvoyes_par_find(id_etranger: str) -> None:
    """Un id hors motif renvoyé par find n'est jamais supprimé, sans exception."""
    venv_path = Path("/opt/app/venv")
    version = Path("/opt/app/venvs/venv-20260920-000000-000000")
    ancien = "venv-20260901-000000-000000"
    executor = MagicMock(spec=CommandExecutor)
    executor.run.side_effect = [
        cmd_result(stdout=f"{version}\n"),  # readlink
        cmd_result(stdout=f"{id_etranger}\n{ancien}\n{version.name}\n"),  # find
        cmd_result(),  # rm -rf de l'ancienne version
    ]
    releaser = VenvReleaser(executor, installer=MagicMock())

    releaser._prune(venv_path, version, None, keep_versions=1)

    suppressions = [
        c.args[0] for c in executor.run.call_args_list if c.args[0][0] == "rm"
    ]
    assert suppressions == [["rm", "-rf", "--", str(Path("/opt/app/venvs") / ancien)]]
