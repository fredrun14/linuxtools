"""Tests pour linuxtools.cli.base."""

# stdlib
import argparse

# third-party
import pytest

from linuxtools.cli.base import CliApplication, CliCommand


class ConcreteCommand(CliCommand):
    """Commande concrète pour les tests."""

    def __init__(self, cmd_name: str = "test-cmd") -> None:
        self._name = cmd_name
        self.execute_called = False
        self.last_args: argparse.Namespace | None = None

    @property
    def name(self) -> str:
        return self._name

    def register(self, subparsers: object) -> None:
        p = subparsers.add_parser(self._name, help="Test command")  # type: ignore[union-attr]
        p.add_argument("--flag", default="default")

    def execute(self, args: argparse.Namespace) -> None:
        self.execute_called = True
        self.last_args = args


class TestCliCommand:
    """Tests pour l'interface abstraite CliCommand."""

    def test_cli_command_abc_ne_peut_pas_etre_instancie(self) -> None:
        """Vérifie que CliCommand ne peut pas être instanciée directement."""
        with pytest.raises(TypeError):
            CliCommand()  # type: ignore

    def test_concrete_command_a_un_nom(self) -> None:
        """Vérifie que la propriété name retourne le nom configuré."""
        cmd = ConcreteCommand("my-cmd")
        assert cmd.name == "my-cmd"

    def test_register_enregistre_la_commande_dans_subparsers(self) -> None:
        """Vérifie que register() déclare la commande dans argparse."""
        # Arrange
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        cmd = ConcreteCommand("sync")
        # Act
        cmd.register(subparsers)
        # Assert
        args = parser.parse_args(["sync"])
        assert args.command == "sync"

    def test_execute_est_appele_avec_le_namespace_correct(self) -> None:
        """Vérifie que execute() reçoit et conserve le Namespace fourni."""
        # Arrange
        cmd = ConcreteCommand("test-cmd")
        ns = argparse.Namespace(command="test-cmd")
        # Act
        cmd.execute(ns)
        # Assert
        assert cmd.execute_called is True
        assert cmd.last_args is ns

    def test_concrete_command_sans_register_ne_peut_etre_instanciee(
        self,
    ) -> None:
        """Vérifie que l'ABC rejette une sous-classe sans register()."""
        # Arrange
        class MissingRegister(CliCommand):
            @property
            def name(self) -> str:
                return "bad"

            def execute(self, args: argparse.Namespace) -> None:
                pass

        # Act / Assert
        with pytest.raises(TypeError):
            MissingRegister()  # type: ignore

    def test_concrete_command_sans_execute_ne_peut_etre_instanciee(
        self,
    ) -> None:
        """Vérifie que l'ABC rejette une sous-classe sans execute()."""
        # Arrange
        class MissingExecute(CliCommand):
            @property
            def name(self) -> str:
                return "bad"

            def register(self, subparsers: object) -> None:
                pass

        # Act / Assert
        with pytest.raises(TypeError):
            MissingExecute()  # type: ignore


class TestCliApplication:
    """Tests pour l'orchestrateur CliApplication."""

    def test_run_dispatche_vers_la_bonne_commande(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vérifie que run() appelle execute() sur la commande sélectionnée."""
        cmd_a = ConcreteCommand("cmd-a")
        cmd_b = ConcreteCommand("cmd-b")
        app = CliApplication("test", "Test app", [cmd_a, cmd_b])
        monkeypatch.setattr("sys.argv", ["test", "cmd-b"])
        app.run()
        assert cmd_b.execute_called
        assert not cmd_a.execute_called

    def test_run_passe_les_arguments_a_la_commande(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vérifie que les arguments CLI sont transmis au Namespace."""
        cmd = ConcreteCommand("cmd-a")
        app = CliApplication("test", "Test app", [cmd])
        monkeypatch.setattr("sys.argv", ["test", "cmd-a", "--flag", "valeur"])
        app.run()
        assert cmd.last_args is not None
        assert cmd.last_args.flag == "valeur"

    def test_run_sans_commande_leve_system_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vérifie que l'absence de sous-commande lève SystemExit."""
        cmd = ConcreteCommand("cmd-a")
        app = CliApplication("test", "Test app", [cmd])
        monkeypatch.setattr("sys.argv", ["test"])
        with pytest.raises(SystemExit):
            app.run()

    def test_run_commande_inconnue_leve_system_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vérifie qu'une commande non enregistrée lève SystemExit."""
        cmd = ConcreteCommand("cmd-a")
        app = CliApplication("test", "Test app", [cmd])
        monkeypatch.setattr("sys.argv", ["test", "inexistant"])
        with pytest.raises(SystemExit):
            app.run()

    def test_run_avec_liste_vide_leve_system_exit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vérifie que CliApplication sans commandes lève SystemExit."""
        # Arrange
        app = CliApplication("test", "desc", [])
        monkeypatch.setattr("sys.argv", ["test", "inexistant"])
        # Act / Assert
        with pytest.raises(SystemExit):
            app.run()

    def test_run_avec_une_seule_commande_dispatche_correctement(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vérifie le dispatch avec une seule commande enregistrée."""
        # Arrange
        cmd = ConcreteCommand("solo")
        app = CliApplication("test", "desc", [cmd])
        monkeypatch.setattr("sys.argv", ["test", "solo"])
        # Act
        app.run()
        # Assert
        assert cmd.execute_called is True

    def test_run_flag_avec_valeur_par_defaut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vérifie que args.flag vaut 'default' quand --flag est absent."""
        # Arrange
        cmd = ConcreteCommand("cmd-a")
        app = CliApplication("test", "desc", [cmd])
        monkeypatch.setattr("sys.argv", ["test", "cmd-a"])
        # Act
        app.run()
        # Assert
        assert cmd.last_args is not None
        assert cmd.last_args.flag == "default"

    def test_run_args_command_contient_le_nom_de_la_commande(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Vérifie que args.command est bien le nom de la commande appelée."""
        # Arrange
        cmd = ConcreteCommand("cmd-a")
        app = CliApplication("test", "desc", [cmd])
        monkeypatch.setattr("sys.argv", ["test", "cmd-a"])
        # Act
        app.run()
        # Assert
        assert cmd.last_args is not None
        assert cmd.last_args.command == "cmd-a"

    @pytest.mark.parametrize("name", ["alpha", "beta", "gamma"])
    def test_run_toutes_les_commandes_sont_enregistrees(
        self, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """Vérifie que chaque commande de la liste est dispatchable."""
        # Arrange
        names = ["alpha", "beta", "gamma"]
        commands = [ConcreteCommand(n) for n in names]
        app = CliApplication("test", "desc", commands)
        monkeypatch.setattr("sys.argv", ["test", name])
        # Act
        app.run()
        # Assert
        target = next(c for c in commands if c.name == name)
        others = [c for c in commands if c.name != name]
        assert target.execute_called is True
        assert all(not c.execute_called for c in others)
