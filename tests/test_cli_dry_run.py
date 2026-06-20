"""Tests pour linux_python_utils.cli.dry_run."""

# stdlib
import argparse

# third-party
import pytest

from linux_python_utils.cli.dry_run import DryRunContext, add_dry_run_argument


class TestDryRunContext:
    """Tests pour la classe DryRunContext."""

    def test_default_dry_run_is_false(self) -> None:
        # Arrange / Act
        ctx = DryRunContext()
        # Assert
        assert ctx.dry_run is False

    def test_dry_run_true_when_flag_set(self) -> None:
        # Arrange / Act
        ctx = DryRunContext(dry_run=True)
        # Assert
        assert ctx.dry_run is True

    def test_would_write_prints_path_and_content(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=True)
        # Act
        ctx.would_write("/etc/foo.conf", "key=value")
        # Assert
        captured = capsys.readouterr()
        assert "/etc/foo.conf" in captured.out
        assert "key=value" in captured.out

    def test_would_write_includes_dry_run_prefix(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=True)
        # Act
        ctx.would_write("/tmp/test.conf", "line")
        # Assert
        assert "[DRY-RUN]" in capsys.readouterr().out

    def test_would_create_prints_path(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=True)
        # Act
        ctx.would_create("/tmp/new_file.conf")
        # Assert
        captured = capsys.readouterr()
        assert "[DRY-RUN]" in captured.out
        assert "/tmp/new_file.conf" in captured.out

    def test_would_modify_prints_path_and_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=True)
        # Act
        ctx.would_modify("/etc/dnf/dnf.conf", "max_parallel_downloads=5")
        # Assert
        captured = capsys.readouterr()
        assert "[DRY-RUN]" in captured.out
        assert "/etc/dnf/dnf.conf" in captured.out
        assert "max_parallel_downloads=5" in captured.out


    def test_would_write_silencieux_si_dry_run_false(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=False)
        # Act
        ctx.would_write("/etc/foo.conf", "key=value")
        # Assert
        assert capsys.readouterr().out == ""

    def test_would_create_silencieux_si_dry_run_false(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=False)
        # Act
        ctx.would_create("/tmp/new_file.conf")
        # Assert
        assert capsys.readouterr().out == ""

    def test_would_modify_silencieux_si_dry_run_false(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=False)
        # Act
        ctx.would_modify("/etc/dnf/dnf.conf", "max_parallel_downloads=5")
        # Assert
        assert capsys.readouterr().out == ""

    def test_would_delete_prints_path(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=True)
        # Act
        ctx.would_delete("/usr/local/bin/mon-outil")
        # Assert
        captured = capsys.readouterr()
        assert "[DRY-RUN]" in captured.out
        assert "/usr/local/bin/mon-outil" in captured.out

    def test_would_delete_silencieux_si_dry_run_false(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=False)
        # Act
        ctx.would_delete("/usr/local/bin/mon-outil")
        # Assert
        assert capsys.readouterr().out == ""

    def test_would_run_command_prints_cmd(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=True)
        # Act
        ctx.would_run_command("systemctl enable mon-service")
        # Assert
        captured = capsys.readouterr()
        assert "[DRY-RUN]" in captured.out
        assert "systemctl enable mon-service" in captured.out

    def test_would_run_command_silencieux_si_dry_run_false(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Arrange
        ctx = DryRunContext(dry_run=False)
        # Act
        ctx.would_run_command("systemctl enable mon-service")
        # Assert
        assert capsys.readouterr().out == ""


class TestAddDryRunArgument:
    """Tests pour la fonction add_dry_run_argument."""

    @pytest.fixture
    def parser(self) -> argparse.ArgumentParser:
        """Fixture fournissant un ArgumentParser vierge."""
        return argparse.ArgumentParser()

    def test_dry_run_default_is_false(
        self, parser: argparse.ArgumentParser
    ) -> None:
        # Arrange
        add_dry_run_argument(parser)
        # Act
        args = parser.parse_args([])
        # Assert
        assert args.dry_run is False

    def test_long_flag_sets_dry_run_true(
        self, parser: argparse.ArgumentParser
    ) -> None:
        # Arrange
        add_dry_run_argument(parser)
        # Act
        args = parser.parse_args(["--dry-run"])
        # Assert
        assert args.dry_run is True

    def test_short_flag_n_sets_dry_run_true(
        self, parser: argparse.ArgumentParser
    ) -> None:
        # Arrange
        add_dry_run_argument(parser)
        # Act
        args = parser.parse_args(["-n"])
        # Assert
        assert args.dry_run is True
