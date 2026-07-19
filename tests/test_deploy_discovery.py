"""Tests pour le module deploy.discovery."""

import json
from importlib import metadata
from pathlib import Path
from unittest.mock import MagicMock, patch

from linuxtools.deploy.discovery import (
    find_editable_source,
    find_project_source,
)


class TestFindProjectSource:
    """Tests pour find_project_source()."""

    def test_trouve_pyproject_dans_le_repertoire_de_depart(
        self, tmp_path
    ):
        """Détecte pyproject.toml directement dans start."""
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        result = find_project_source(tmp_path)
        assert result == tmp_path.resolve()

    def test_remonte_jusqu_a_trouver_pyproject(self, tmp_path):
        """Remonte plusieurs niveaux jusqu'à pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        nested = tmp_path / "src" / "pkg" / "sub"
        nested.mkdir(parents=True)
        result = find_project_source(nested)
        assert result == tmp_path.resolve()

    def test_retourne_none_si_aucun_pyproject(self, tmp_path):
        """Retourne None si aucun ancêtre ne contient pyproject.toml.

        S'appuie sur le fait qu'aucun ancêtre de tmp_path (sous /tmp)
        ne contient de pyproject.toml jusqu'à la racine du système.
        """
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        result = find_project_source(nested)
        assert result is None

    def test_utilise_cwd_par_defaut(self, tmp_path, monkeypatch):
        """Sans start, utilise Path.cwd()."""
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        monkeypatch.chdir(tmp_path)
        result = find_project_source()
        assert result == tmp_path.resolve()

    def test_pyproject_a_la_racine_du_systeme(self):
        """Cas limite : pyproject.toml directement à la racine '/'.

        La boucle while s'arrête dès que candidate == candidate.parent
        (la racine) sans avoir testé la racine elle-même : une
        dernière vérification explicite est donc nécessaire.
        """
        with patch(
            "linuxtools.deploy.discovery.Path.is_file",
            return_value=True,
        ):
            result = find_project_source(Path("/"))
        assert result == Path("/")


class TestFindEditableSource:
    """Tests pour find_editable_source()."""

    def test_retourne_none_si_distribution_absente(self):
        """Retourne None si la distribution n'est pas installée."""
        with patch(
            "linuxtools.deploy.discovery.metadata.distribution",
            side_effect=metadata.PackageNotFoundError,
        ):
            result = find_editable_source("inexistant")
        assert result is None

    def test_retourne_none_si_direct_url_absent(self):
        """Retourne None si direct_url.json n'existe pas."""
        mock_dist = MagicMock()
        mock_dist.read_text.return_value = None
        with patch(
            "linuxtools.deploy.discovery.metadata.distribution",
            return_value=mock_dist,
        ):
            result = find_editable_source("linuxtools")
        assert result is None

    def test_retourne_none_si_json_malforme(self):
        """Retourne None (best-effort) si direct_url.json est invalide."""
        mock_dist = MagicMock()
        mock_dist.read_text.return_value = "{invalide"
        with patch(
            "linuxtools.deploy.discovery.metadata.distribution",
            return_value=mock_dist,
        ):
            result = find_editable_source("linuxtools")
        assert result is None

    def test_retourne_none_si_non_editable(self):
        """Retourne None si l'install n'est pas éditable."""
        mock_dist = MagicMock()
        mock_dist.read_text.return_value = json.dumps(
            {
                "dir_info": {"editable": False},
                "url": "file:///home/user/linuxtools",
            }
        )
        with patch(
            "linuxtools.deploy.discovery.metadata.distribution",
            return_value=mock_dist,
        ):
            result = find_editable_source("linuxtools")
        assert result is None

    def test_retourne_none_si_url_non_file(self):
        """Retourne None si l'url n'est pas un file://."""
        mock_dist = MagicMock()
        mock_dist.read_text.return_value = json.dumps(
            {
                "dir_info": {"editable": True},
                "url": "https://example.com/linuxtools",
            }
        )
        with patch(
            "linuxtools.deploy.discovery.metadata.distribution",
            return_value=mock_dist,
        ):
            result = find_editable_source("linuxtools")
        assert result is None

    def test_retourne_le_chemin_si_editable_et_file(self):
        """Retourne le Path local si l'install est éditable via file://."""
        mock_dist = MagicMock()
        mock_dist.read_text.return_value = json.dumps(
            {
                "dir_info": {"editable": True},
                "url": "file:///home/user/linuxtools",
            }
        )
        with patch(
            "linuxtools.deploy.discovery.metadata.distribution",
            return_value=mock_dist,
        ):
            result = find_editable_source("linuxtools")
        assert result == Path("/home/user/linuxtools")
