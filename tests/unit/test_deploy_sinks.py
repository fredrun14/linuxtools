"""Tests pour le module deploy.sinks."""

import os
from pathlib import Path
from unittest.mock import MagicMock

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.destinations import (
    LocalDestination,
    RemoteDestination,
    WriteOutcome,
)
from linuxtools.deploy.sinks import ContentSink, TomlSink


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


def _assert_no_secret_leaked(logger: MagicMock, *secret_values: str) -> None:
    """Vérifie qu'aucune valeur secrète n'apparaît dans les appels
    du logger mocké (arguments positionnels et nommés confondus)."""
    for mock_call in logger.mock_calls:
        rendered = str(mock_call)
        for value in secret_values:
            assert value not in rendered, (
                f"Valeur secrète {value!r} trouvée dans un appel "
                f"logger : {rendered}"
            )


class TestContentSink:
    """Tests de ContentSink.write."""

    def test_content_sink_logue_un_succes_avec_le_label_destination(
        self,
    ) -> None:
        """Un dépôt réussi logue un message informatif mentionnant le
        label de la destination."""
        destination = MagicMock()
        destination.label = "local"
        destination.write.return_value = WriteOutcome(True)
        logger = MagicMock()
        sink = ContentSink(destination, logger=logger)
        dest_path = Path("/etc/app/config")

        result = sink.write(dest_path, "contenu", mode=0o640)

        assert result is True
        logger.log_info.assert_called_once()
        message = logger.log_info.call_args.args[0]
        assert "local" in message
        assert str(dest_path) in message

    def test_content_sink_echec_logue_en_log_error(self) -> None:
        """Un dépôt en échec logue en log_error (pas log_warning) —
        changement de comportement assumé : le dépôt en échec fait
        abandonner la phase de déploiement, c'est une erreur."""
        destination = MagicMock()
        destination.label = "distant"
        destination.write.return_value = WriteOutcome(
            False, "Échec du dépôt distant de /tmp/x : boom"
        )
        logger = MagicMock()
        sink = ContentSink(destination, logger=logger)

        result = sink.write(Path("/tmp/x"), "contenu")

        assert result is False
        logger.log_error.assert_called_once()
        assert "boom" in logger.log_error.call_args.args[0]
        logger.log_warning.assert_not_called()

    def test_content_sink_sans_logger_ne_leve_pas(self) -> None:
        """Cas limite : logger=None n'entraîne aucune exception, en
        succès comme en échec."""
        destination_ok = MagicMock()
        destination_ok.label = "local"
        destination_ok.write.return_value = WriteOutcome(True)
        sink_ok = ContentSink(destination_ok, logger=None)

        assert sink_ok.write(Path("/tmp/x"), "contenu") is True

        destination_ko = MagicMock()
        destination_ko.label = "distant"
        destination_ko.write.return_value = WriteOutcome(False, "boom")
        sink_ko = ContentSink(destination_ko, logger=None)

        assert sink_ko.write(Path("/tmp/x"), "contenu") is False

    def test_content_sink_utilise_le_mode_par_defaut_cas_limite(
        self, tmp_path: Path
    ) -> None:
        """Cas limite : mode non renseigné -> 0o644 (défaut).

        Complète le cas limite de `TomlSink.write` (cf.
        `TestTomlSink`) : `TomlSink.write` transmet toujours un mode
        explicite à `ContentSink.write`, donc le défaut propre de
        `ContentSink.write` n'est jamais exercé via `TomlSink` — il
        faut ce test dédié pour tuer le mutant sur son propre
        défaut."""
        dest_path = tmp_path / "deployed.txt"
        sink = ContentSink(LocalDestination())

        assert sink.write(dest_path, "contenu") is True
        assert oct(os.stat(dest_path).st_mode)[-3:] == "644"

    def test_content_sink_en_echec_ne_logue_jamais_le_contenu(self) -> None:
        """Sécurité A09, chemin échec : le contenu (potentiellement
        un secret) ne doit apparaître dans aucun appel du logger.
        RemoteDestination réelle avec un CommandResult scripté en
        échec, pour que la sentinelle traverse réellement le code
        qui construit WriteOutcome.detail."""
        sentinelle = "SECRET_SENTINELLE"
        executor = MagicMock(spec=CommandExecutor)
        executor.run.return_value = _result(
            False, stderr="permission denied"
        )
        destination = RemoteDestination(executor)
        logger = MagicMock()
        sink = ContentSink(destination, logger=logger)

        result = sink.write(Path("/tmp/x"), sentinelle)

        assert result is False
        logger.log_error.assert_called_once()
        _assert_no_secret_leaked(logger, sentinelle)

    def test_content_sink_en_succes_ne_logue_jamais_le_contenu(
        self, tmp_path: Path
    ) -> None:
        """Sécurité A09, chemin succès : le contenu ne doit
        apparaître dans aucun appel du logger (log d'information).
        LocalDestination réelle sur tmp_path."""
        sentinelle = "SECRET_SENTINELLE"
        dest_path = tmp_path / "x"
        destination = LocalDestination()
        logger = MagicMock()
        sink = ContentSink(destination, logger=logger)

        result = sink.write(dest_path, sentinelle)

        assert result is True
        logger.log_info.assert_called_once()
        _assert_no_secret_leaked(logger, sentinelle)


class TestTomlSink:
    """Tests de TomlSink.write (rendu TOML puis délégation)."""

    def test_toml_sink_delegue_le_rendu_puis_le_depot(
        self, tmp_path: Path
    ) -> None:
        """Le mapping est rendu en TOML puis déposé via ContentSink,
        local comme distant."""
        dest_path = tmp_path / "deployed.toml"
        sink = TomlSink(LocalDestination())

        result = sink.write(dest_path, {"port": 8080}, mode=0o640)

        assert result is True
        assert dest_path.read_text(encoding="utf-8") == "port = 8080\n"
        assert oct(os.stat(dest_path).st_mode)[-3:] == "640"

    def test_toml_sink_utilise_le_mode_par_defaut_cas_limite(
        self, tmp_path: Path
    ) -> None:
        """Cas limite : mode non renseigné -> 0o644 (défaut)."""
        dest_path = tmp_path / "deployed.toml"
        assert TomlSink(LocalDestination()).write(dest_path, {"a": 1}) is True
        assert oct(os.stat(dest_path).st_mode)[-3:] == "644"

    def test_toml_sink_distant_rend_puis_depose_via_install(self) -> None:
        """Chemin distant : le TOML rendu transite par stdin d'`install`."""
        dest_path = Path("/etc/app/config.toml")
        executor = MagicMock(spec=CommandExecutor)
        executor.run.side_effect = [_result(True)]
        sink = TomlSink(RemoteDestination(executor))

        result = sink.write(dest_path, {"port": 8080}, mode=0o600)

        assert result is True
        assert executor.run.call_args_list[0] == (
            (
                [
                    "install",
                    "-m",
                    "600",
                    "-T",
                    "/dev/stdin",
                    str(dest_path),
                ],
            ),
            {"stdin": "port = 8080\n"},
        )
