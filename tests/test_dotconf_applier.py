"""Tests unitaires pour dotconf.applier (ConfigApplier)."""

from pathlib import Path
from unittest.mock import MagicMock

from linuxtools.dotconf.applier import ConfigApplier
from linuxtools.dotconf.spec import ConfigBlock, ConfigSpec


def _make_spec(
    tmp_path: Path,
    blocks: list[ConfigBlock],
    filename: str = "test.conf",
) -> ConfigSpec:
    """Construit un ConfigSpec pointant vers tmp_path."""
    return ConfigSpec(file_path=tmp_path / filename, blocks=blocks)


class TestConfigApplierCreateFile:
    """Tests pour la création d'un nouveau fichier."""

    def test_apply_creates_new_file_when_absent(
        self, tmp_path: Path
    ) -> None:
        spec = _make_spec(tmp_path, [ConfigBlock(content="key = value")])
        applier = ConfigApplier()

        actions = applier.apply(spec)

        assert spec.file_path.exists()
        assert len(actions) == 1
        assert "Created:" in actions[0]

    def test_apply_writes_block_content_to_new_file(
        self, tmp_path: Path
    ) -> None:
        spec = _make_spec(tmp_path, [ConfigBlock(content="opt = yes")])
        ConfigApplier().apply(spec)

        assert "opt = yes" in spec.file_path.read_text(encoding="utf-8")

    def test_apply_creates_parent_dirs_when_missing(
        self, tmp_path: Path
    ) -> None:
        deep = tmp_path / "a" / "b" / "c" / "config"
        spec = ConfigSpec(
            file_path=deep,
            blocks=[ConfigBlock(content="x = 1")],
        )

        ConfigApplier().apply(spec)

        assert deep.exists()

    def test_apply_sets_chmod_644_on_new_file(
        self, tmp_path: Path
    ) -> None:
        spec = _make_spec(tmp_path, [ConfigBlock(content="k = v")])
        ConfigApplier().apply(spec)

        mode = oct(spec.file_path.stat().st_mode)[-3:]
        assert mode == "644"

    def test_apply_action_message_contains_block_count(
        self, tmp_path: Path
    ) -> None:
        blocks = [
            ConfigBlock(content="a = 1"),
            ConfigBlock(content="b = 2"),
        ]
        spec = _make_spec(tmp_path, blocks)

        actions = ConfigApplier().apply(spec)

        assert "2 blocks" in actions[0]


class TestConfigApplierExistingFile:
    """Tests pour l'application sur un fichier existant."""

    def test_apply_appends_missing_block_to_existing_file(
        self, tmp_path: Path
    ) -> None:
        conf = tmp_path / "app.conf"
        conf.write_text("existing = yes\n", encoding="utf-8")
        spec = ConfigSpec(
            file_path=conf,
            blocks=[ConfigBlock(content="new_opt = 1")],
        )

        actions = ConfigApplier().apply(spec)

        assert len(actions) == 1
        assert "Appended:" in actions[0]
        assert "new_opt = 1" in conf.read_text(encoding="utf-8")

    def test_apply_uncomments_commented_block(
        self, tmp_path: Path
    ) -> None:
        conf = tmp_path / "app.conf"
        conf.write_text("# key = value\n", encoding="utf-8")
        spec = ConfigSpec(
            file_path=conf,
            blocks=[ConfigBlock(content="key = value")],
        )

        actions = ConfigApplier().apply(spec)

        assert len(actions) == 1
        assert "Uncommented:" in actions[0]
        content = conf.read_text(encoding="utf-8")
        assert "# key = value" not in content
        assert "key = value" in content

    def test_apply_skips_already_present_block(
        self, tmp_path: Path
    ) -> None:
        conf = tmp_path / "app.conf"
        conf.write_text("key = value\n", encoding="utf-8")
        spec = ConfigSpec(
            file_path=conf,
            blocks=[ConfigBlock(content="key = value")],
        )

        actions = ConfigApplier().apply(spec)

        assert actions == []

    def test_apply_returns_empty_list_when_no_changes(
        self, tmp_path: Path
    ) -> None:
        conf = tmp_path / "app.conf"
        conf.write_text("a = 1\nb = 2\n", encoding="utf-8")
        spec = ConfigSpec(
            file_path=conf,
            blocks=[
                ConfigBlock(content="a = 1"),
                ConfigBlock(content="b = 2"),
            ],
        )

        actions = ConfigApplier().apply(spec)

        assert actions == []

    def test_apply_adds_block_to_ini_section(
        self, tmp_path: Path
    ) -> None:
        conf = tmp_path / "dnf.conf"
        conf.write_text("[main]\ncleanreqs = yes\n", encoding="utf-8")
        spec = ConfigSpec(
            file_path=conf,
            blocks=[
                ConfigBlock(content="fastestmirror = True", section="main")
            ],
        )

        actions = ConfigApplier().apply(spec)

        assert len(actions) == 1
        assert "Added to [main]:" in actions[0]
        assert "fastestmirror = True" in conf.read_text(encoding="utf-8")

    def test_apply_sets_chmod_644_after_modification(
        self, tmp_path: Path
    ) -> None:
        conf = tmp_path / "app.conf"
        conf.write_text("", encoding="utf-8")
        conf.chmod(0o600)
        spec = ConfigSpec(
            file_path=conf,
            blocks=[ConfigBlock(content="x = 1")],
        )

        ConfigApplier().apply(spec)

        mode = oct(conf.stat().st_mode)[-3:]
        assert mode == "644"

    def test_apply_does_not_change_permissions_when_no_modification(
        self, tmp_path: Path
    ) -> None:
        conf = tmp_path / "app.conf"
        conf.write_text("x = 1\n", encoding="utf-8")
        conf.chmod(0o600)
        spec = ConfigSpec(
            file_path=conf,
            blocks=[ConfigBlock(content="x = 1")],
        )

        ConfigApplier().apply(spec)

        mode = oct(conf.stat().st_mode)[-3:]
        assert mode == "600"

    def test_apply_idempotent_second_call_returns_empty(
        self, tmp_path: Path
    ) -> None:
        spec = _make_spec(tmp_path, [ConfigBlock(content="opt = 1")])
        applier = ConfigApplier()
        applier.apply(spec)

        actions = applier.apply(spec)

        assert actions == []


class TestConfigApplierLogger:
    """Tests pour l'intégration du logger."""

    def test_apply_calls_logger_when_provided(
        self, tmp_path: Path
    ) -> None:
        mock_logger = MagicMock()
        spec = _make_spec(tmp_path, [ConfigBlock(content="k = v")])

        ConfigApplier(logger=mock_logger).apply(spec)

        mock_logger.log_info.assert_called_once()

    def test_apply_no_logger_does_not_raise(
        self, tmp_path: Path
    ) -> None:
        spec = _make_spec(tmp_path, [ConfigBlock(content="k = v")])

        actions = ConfigApplier(logger=None).apply(spec)

        assert len(actions) == 1

    def test_apply_logger_message_contains_action(
        self, tmp_path: Path
    ) -> None:
        mock_logger = MagicMock()
        spec = _make_spec(tmp_path, [ConfigBlock(content="k = v")])

        ConfigApplier(logger=mock_logger).apply(spec)

        call_args = mock_logger.log_info.call_args[0][0]
        assert "Created:" in call_args


class TestConfigApplierBlocVide:
    """Tests défensifs pour bloc à contenu vide."""

    def test_apply_block_contenu_vide_ne_crashe_pas(
        self, tmp_path: Path
    ) -> None:
        """Un bloc vide dans apply() ne lève pas IndexError."""
        spec = _make_spec(tmp_path, [ConfigBlock(content="")])
        actions = ConfigApplier().apply(spec)
        assert actions == []

    def test_apply_block_contenu_espaces_ne_crashe_pas(
        self, tmp_path: Path
    ) -> None:
        """Un bloc contenant uniquement des espaces retourne None."""
        conf = tmp_path / "test.conf"
        conf.write_text("existing = true\n", encoding="utf-8")
        spec = ConfigSpec(
            file_path=conf, blocks=[ConfigBlock(content="   ")]
        )
        actions = ConfigApplier().apply(spec)
        assert actions == []
