"""Tests unitaires pour dotconf.spec (ConfigBlock + ConfigSpec)."""

from pathlib import Path

import pytest

from linux_python_utils.dotconf.spec import ConfigBlock, ConfigSpec


class TestConfigBlock:
    """Tests pour la dataclass ConfigBlock."""

    def test_config_block_stores_content(self) -> None:
        # Arrange / Act
        block = ConfigBlock(content="key = value")

        # Assert
        assert block.content == "key = value"

    def test_config_block_default_comment_is_empty(self) -> None:
        block = ConfigBlock(content="key = value")

        assert block.comment == ""

    def test_config_block_default_section_is_none(self) -> None:
        block = ConfigBlock(content="key = value")

        assert block.section is None

    def test_config_block_with_all_fields(self) -> None:
        block = ConfigBlock(
            content="fastestmirror = True",
            comment="# Speed",
            section="main",
        )

        assert block.content == "fastestmirror = True"
        assert block.comment == "# Speed"
        assert block.section == "main"

    @pytest.mark.parametrize(
        "content,comment,section",
        [
            ("-f best", "", None),
            ("key=val", "# note", None),
            ("opt=1", "# opt", "section_name"),
        ],
    )
    def test_config_block_parametrized_fields(
        self,
        content: str,
        comment: str,
        section: str | None,
    ) -> None:
        block = ConfigBlock(content=content, comment=comment, section=section)

        assert block.content == content
        assert block.comment == comment
        assert block.section == section


class TestConfigSpec:
    """Tests pour la dataclass ConfigSpec."""

    def test_config_spec_stores_file_path(self) -> None:
        path = Path("/etc/dnf/dnf.conf")

        spec = ConfigSpec(file_path=path)

        assert spec.file_path == path

    def test_config_spec_default_blocks_is_empty_list(self) -> None:
        spec = ConfigSpec(file_path=Path("/tmp/test.conf"))

        assert spec.blocks == []

    def test_config_spec_with_blocks(self) -> None:
        path = Path("/tmp/test.conf")
        blocks = [
            ConfigBlock(content="a = 1"),
            ConfigBlock(content="b = 2", section="main"),
        ]

        spec = ConfigSpec(file_path=path, blocks=blocks)

        assert spec.file_path == path
        assert len(spec.blocks) == 2
        assert spec.blocks[0].content == "a = 1"
        assert spec.blocks[1].section == "main"

    def test_config_spec_blocks_are_independent_per_instance(self) -> None:
        spec1 = ConfigSpec(file_path=Path("/tmp/a.conf"))
        spec2 = ConfigSpec(file_path=Path("/tmp/b.conf"))

        spec1.blocks.append(ConfigBlock(content="x = 1"))

        assert spec2.blocks == []
