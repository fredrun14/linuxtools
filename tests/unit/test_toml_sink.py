"""Tests pour le module deploy.toml_sink."""

from pathlib import Path
from unittest.mock import MagicMock

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.toml_sink import (
    LocalDestination,
    RemoteDestination,
    TomlSink,
)


def _result(success: bool = True, stderr: str = "") -> CommandResult:
    """Construit un CommandResult scripté pour les tests."""
    return CommandResult(
        command=(),
        return_code=0 if success else 1,
        stdout="",
        stderr=stderr,
        success=success,
        duration=0.01,
    )


class TestTomlSinkLocal:
    """Tests pour TomlSink avec une destination locale."""

    def test_write_local_ecrit_le_contenu_effectif_cas_nominal(
        self, tmp_path: Path
    ) -> None:
        """Cas nominal : le TOML rendu à partir de `data` est écrit sur
        `path`, avec le mode demandé."""
        import os

        dest_path = tmp_path / "deployed.toml"
        sink = TomlSink(LocalDestination())

        result = sink.write(dest_path, {"port": 8080}, mode=0o640)

        assert result is True
        assert dest_path.read_text(encoding="utf-8") == "port = 8080\n"
        assert oct(os.stat(dest_path).st_mode)[-3:] == "640"

    def test_write_local_utilise_le_mode_par_defaut_cas_limite(
        self, tmp_path: Path
    ) -> None:
        """Cas limite : mode non renseigné -> 0o644 (défaut)."""
        import os

        dest_path = tmp_path / "deployed.toml"
        sink = TomlSink(LocalDestination())

        result = sink.write(dest_path, {"a": 1})

        assert result is True
        assert oct(os.stat(dest_path).st_mode)[-3:] == "644"

    def test_write_local_logue_un_succes(self, tmp_path: Path) -> None:
        """Un logger injecté reçoit un message informatif de succès."""
        logger = MagicMock()
        dest_path = tmp_path / "deployed.toml"
        sink = TomlSink(LocalDestination(), logger=logger)

        sink.write(dest_path, {"a": 1})

        logger.log_info.assert_called_once()
        assert str(dest_path) in logger.log_info.call_args.args[0]


class TestTomlSinkRemote:
    """Tests pour TomlSink avec une destination distante."""

    def test_write_remote_ecrit_via_tee_puis_chmod_cas_nominal(self) -> None:
        """Cas nominal distant : tee (stdin=TOML) puis chmod
        réussissent, executor mocké."""
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True), _result(True)]
        sink = TomlSink(RemoteDestination(executor))

        result = sink.write(dest_path, {"port": 8080}, mode=0o600)

        assert result is True
        assert executor.run.call_args_list[0] == (
            (["tee", str(dest_path)],),
            {"stdin": "port = 8080\n"},
        )
        assert executor.run.call_args_list[1] == (
            (["chmod", "600", str(dest_path)],),
            {},
        )

    def test_write_remote_echec_tee_retourne_false_et_logue(self) -> None:
        """Cas d'erreur distant : échec de tee -> False + log_warning."""
        logger = MagicMock()
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(False, stderr="no space left")
        sink = TomlSink(RemoteDestination(executor), logger=logger)

        result = sink.write(Path("/etc/app/config.toml"), {"a": 1})

        assert result is False
        executor.run.assert_called_once()
        logger.log_warning.assert_called_once()
        assert "no space left" in logger.log_warning.call_args.args[0]

    def test_write_remote_echec_chmod_retourne_false_et_logue(self) -> None:
        """Cas d'erreur distant : tee ok mais chmod échoue -> False."""
        logger = MagicMock()
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [
            _result(True),
            _result(False, stderr="not permitted"),
        ]
        sink = TomlSink(RemoteDestination(executor), logger=logger)

        result = sink.write(Path("/etc/app/config.toml"), {"a": 1})

        assert result is False
        assert executor.run.call_count == 2
        logger.log_warning.assert_called_once()
        assert "not permitted" in logger.log_warning.call_args.args[0]
