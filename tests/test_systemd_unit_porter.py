"""Tests pour linuxtools.systemd.unit_porter."""

# stdlib
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# third-party
import pytest

# local
from linuxtools.systemd.unit_porter import (
    SystemdUnitExporter,
    SystemdUnitRestorer,
    _toml_escape,
)


# ---------------------------------------------------------------------------
# Fixtures partagées
# ---------------------------------------------------------------------------

SERVICE_INI = """\
[Unit]
Description=Mon service de test
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/mon-binaire
Restart=on-failure
Environment=FOO=bar
Environment=BAZ=qux

[Install]
WantedBy=multi-user.target
"""

TIMER_INI = """\
[Unit]
Description=Timer de test

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
"""

MOUNT_INI = """\
[Unit]
Description=Montage NFS de test
After=network-online.target

[Mount]
What=192.168.1.10:/data
Where=/mnt/data
Type=nfs
Options=rw,soft

[Install]
WantedBy=remote-fs.target
"""


def _write_unit(tmp_path: Path, name: str, content: str) -> Path:
    """Écrit un fichier unit dans tmp_path et retourne son chemin."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_exporter(logger: MagicMock | None = None) -> SystemdUnitExporter:
    return SystemdUnitExporter(logger=logger or MagicMock())


def _make_restorer(
    executor: MagicMock | None = None,
    logger: MagicMock | None = None,
) -> SystemdUnitRestorer:
    return SystemdUnitRestorer(
        executor=executor,
        logger=logger or MagicMock(),
    )


# ---------------------------------------------------------------------------
# Tests _toml_escape
# ---------------------------------------------------------------------------


class TestTomlEscape:
    """Tests pour la fonction _toml_escape."""

    def test_echappe_guillemet(self) -> None:
        """Vérifie l'échappement des guillemets doubles."""
        assert _toml_escape('va"leur') == 'va\\"leur'

    def test_echappe_antislash(self) -> None:
        """Vérifie l'échappement de l'antislash."""
        assert _toml_escape("va\\leur") == "va\\\\leur"

    def test_chaine_vide(self) -> None:
        """Retourne une chaîne vide inchangée."""
        assert _toml_escape("") == ""

    def test_chaine_sans_caractere_special(self) -> None:
        """Retourne une chaîne ordinaire inchangée."""
        assert _toml_escape("/usr/bin/mon-binaire") == "/usr/bin/mon-binaire"

    def test_combinaison_guillemet_et_antislash(self) -> None:
        """Échappe les deux caractères spéciaux dans le bon ordre."""
        assert _toml_escape('C:\\path"') == 'C:\\\\path\\"'


# ---------------------------------------------------------------------------
# Tests SystemdUnitExporter.parse_ini
# ---------------------------------------------------------------------------


class TestParseIni:
    """Tests pour SystemdUnitExporter.parse_ini."""

    def test_parse_service_nominal(self, tmp_path: Path) -> None:
        """Parse un .service complet en dict correctement structuré."""
        p = _write_unit(tmp_path, "mon.service", SERVICE_INI)
        data = SystemdUnitExporter.parse_ini(p)

        assert "Unit" in data
        assert data["Unit"]["Description"] == ["Mon service de test"]
        assert data["Service"]["ExecStart"] == ["/usr/bin/mon-binaire"]

    def test_valeurs_multi_occurrence(self, tmp_path: Path) -> None:
        """Les clés dupliquées sont agrégées en liste."""
        p = _write_unit(tmp_path, "mon.service", SERVICE_INI)
        data = SystemdUnitExporter.parse_ini(p)

        assert data["Service"]["Environment"] == ["FOO=bar", "BAZ=qux"]

    def test_ignore_commentaires(self, tmp_path: Path) -> None:
        """Les lignes # et ; sont ignorées."""
        content = "[Unit]\n# Commentaire\n; Autre\nDescription=Test\n"
        p = _write_unit(tmp_path, "c.service", content)
        data = SystemdUnitExporter.parse_ini(p)

        assert list(data["Unit"].keys()) == ["Description"]

    def test_ignore_lignes_vides(self, tmp_path: Path) -> None:
        """Les lignes vides ne créent pas d'entrées parasites."""
        content = "[Unit]\n\nDescription=Test\n\n"
        p = _write_unit(tmp_path, "v.service", content)
        data = SystemdUnitExporter.parse_ini(p)

        assert list(data["Unit"].keys()) == ["Description"]

    def test_leve_oserror_si_fichier_absent(self, tmp_path: Path) -> None:
        """Lève OSError si le fichier n'existe pas."""
        with pytest.raises(OSError):
            SystemdUnitExporter.parse_ini(tmp_path / "absent.service")


# ---------------------------------------------------------------------------
# Tests SystemdUnitExporter.to_toml
# ---------------------------------------------------------------------------


class TestToToml:
    """Tests pour SystemdUnitExporter.to_toml."""

    def test_contient_section_meta(self) -> None:
        """Le TOML produit contient une section [meta]."""
        data: dict = {"Unit": {"Description": ["Test"]}}
        result = SystemdUnitExporter.to_toml(data, "service", enabled=True)
        assert "[meta]" in result
        assert 'unit_type = "service"' in result
        assert "enabled = true" in result

    def test_valeur_unique_devient_string(self) -> None:
        """Une valeur unique est sérialisée en string TOML."""
        data: dict = {"Service": {"ExecStart": ["/usr/bin/foo"]}}
        result = SystemdUnitExporter.to_toml(data, "service")
        assert 'ExecStart = "/usr/bin/foo"' in result

    def test_valeurs_multiples_deviennent_tableau(self) -> None:
        """Les valeurs multiples sont sérialisées en tableau TOML."""
        data: dict = {"Service": {"Environment": ["A=1", "B=2"]}}
        result = SystemdUnitExporter.to_toml(data, "service")
        assert 'Environment = ["A=1", "B=2"]' in result

    def test_requires_exec_dans_meta(self) -> None:
        """Le champ requires_exec est présent dans [meta]."""
        data: dict = {}
        result = SystemdUnitExporter.to_toml(
            data, "service", requires_exec="/usr/bin/foo"
        )
        assert 'requires_exec = "/usr/bin/foo"' in result

    def test_echappe_guillemets_dans_valeurs(self) -> None:
        """Les guillemets dans les valeurs sont échappés."""
        data: dict = {"Unit": {"Description": ['Va"leur']}}
        result = SystemdUnitExporter.to_toml(data, "service")
        assert 'Description = "Va\\"leur"' in result

    def test_enabled_false_par_defaut(self) -> None:
        """enabled = false par défaut."""
        data: dict = {}
        result = SystemdUnitExporter.to_toml(data, "service")
        assert "enabled = false" in result


# ---------------------------------------------------------------------------
# Tests SystemdUnitExporter.export
# ---------------------------------------------------------------------------


class TestExport:
    """Tests pour SystemdUnitExporter.export."""

    def test_export_service_nominal(self, tmp_path: Path) -> None:
        """Exporte un .service complet avec toutes les sections."""
        p = _write_unit(tmp_path, "mon.service", SERVICE_INI)
        exporter = _make_exporter()
        result = exporter.export(p, enabled=True)

        assert result is not None
        assert "[meta]" in result
        assert 'unit_type = "service"' in result
        assert "[Unit]" in result
        assert "[Service]" in result
        assert "[Install]" in result

    def test_export_timer_nominal(self, tmp_path: Path) -> None:
        """Exporte un .timer avec unit_type = timer."""
        p = _write_unit(tmp_path, "mon.timer", TIMER_INI)
        exporter = _make_exporter()
        result = exporter.export(p)

        assert result is not None
        assert 'unit_type = "timer"' in result
        assert "[Timer]" in result

    def test_export_mount_nominal(self, tmp_path: Path) -> None:
        """Exporte un .mount avec unit_type = mount."""
        p = _write_unit(tmp_path, "mon.mount", MOUNT_INI)
        exporter = _make_exporter()
        result = exporter.export(p)

        assert result is not None
        assert 'unit_type = "mount"' in result
        assert "[Mount]" in result

    def test_export_type_non_supporte_retourne_none(
        self, tmp_path: Path
    ) -> None:
        """Retourne None pour un type non supporté (.socket)."""
        p = _write_unit(tmp_path, "mon.socket", "[Unit]\nDescription=X\n")
        logger = MagicMock()
        exporter = _make_exporter(logger)
        result = exporter.export(p)

        assert result is None
        logger.log_error.assert_called_once()

    def test_export_fichier_absent_retourne_none(
        self, tmp_path: Path
    ) -> None:
        """Retourne None si le fichier est illisible."""
        logger = MagicMock()
        exporter = _make_exporter(logger)
        result = exporter.export(tmp_path / "absent.service")

        assert result is None
        logger.log_error.assert_called_once()

    def test_export_sans_logger_utilise_console_logger(
        self, tmp_path: Path
    ) -> None:
        """L'export fonctionne sans logger explicite (ConsoleLogger par défaut)."""
        p = _write_unit(tmp_path, "mon.service", SERVICE_INI)
        exporter = SystemdUnitExporter()
        result = exporter.export(p)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests SystemdUnitRestorer.to_ini
# ---------------------------------------------------------------------------


class TestToIni:
    """Tests pour SystemdUnitRestorer.to_ini."""

    def test_reconstruit_service(self) -> None:
        """Reconstruit le contenu INI d'un service depuis le dict TOML."""
        data = {
            "meta": {"unit_type": "service"},
            "Unit": {"Description": "Mon service"},
            "Service": {"ExecStart": "/usr/bin/foo", "Type": "simple"},
            "Install": {"WantedBy": "multi-user.target"},
        }
        result = SystemdUnitRestorer.to_ini(data, "service")

        assert "[Unit]" in result
        assert "Description=Mon service" in result
        assert "[Service]" in result
        assert "ExecStart=/usr/bin/foo" in result
        assert "[Install]" in result

    def test_reconstruit_timer(self) -> None:
        """Reconstruit [Timer] pour un timer."""
        data = {
            "Unit": {"Description": "Timer"},
            "Timer": {"OnCalendar": "daily"},
            "Install": {"WantedBy": "timers.target"},
        }
        result = SystemdUnitRestorer.to_ini(data, "timer")

        assert "[Timer]" in result
        assert "OnCalendar=daily" in result

    def test_reconstruit_mount(self) -> None:
        """Reconstruit [Mount] pour un mount."""
        data = {
            "Unit": {"Description": "NFS"},
            "Mount": {"What": "10.0.0.1:/data", "Where": "/mnt/data"},
            "Install": {"WantedBy": "remote-fs.target"},
        }
        result = SystemdUnitRestorer.to_ini(data, "mount")

        assert "[Mount]" in result
        assert "What=10.0.0.1:/data" in result

    def test_valeurs_liste_produisent_plusieurs_lignes(self) -> None:
        """Les listes TOML produisent plusieurs lignes key=value."""
        data = {
            "Service": {"Environment": ["A=1", "B=2"]},
        }
        result = SystemdUnitRestorer.to_ini(data, "service")

        assert "Environment=A=1" in result
        assert "Environment=B=2" in result

    def test_sections_absentes_omises(self) -> None:
        """Les sections absentes du dict ne génèrent pas de lignes."""
        data = {
            "Unit": {"Description": "Test"},
        }
        result = SystemdUnitRestorer.to_ini(data, "service")

        assert "[Install]" not in result
        assert "[Service]" not in result


# ---------------------------------------------------------------------------
# Tests SystemdUnitRestorer.restore
# ---------------------------------------------------------------------------


class TestRestore:
    """Tests pour SystemdUnitRestorer.restore."""

    def _make_toml(
        self,
        tmp_path: Path,
        name: str,
        unit_type: str = "service",
        enabled: bool = False,
        requires_exec: str = "",
        extra_sections: str = "",
    ) -> Path:
        """Génère un fichier TOML minimal dans tmp_path (crée le dossier)."""
        content = (
            "[meta]\n"
            f'unit_type = "{unit_type}"\n'
            f"enabled = {str(enabled).lower()}\n"
            f'requires_exec = "{requires_exec}"\n'
            "\n"
            "[Unit]\n"
            'Description = "Test"\n'
            "\n"
            f"[{unit_type.capitalize()}]\n"
            'ExecStart = "/usr/bin/foo"\n'
            "\n"
            "[Install]\n"
            'WantedBy = "multi-user.target"\n'
            "\n"
            + extra_sections
        )
        tmp_path.mkdir(parents=True, exist_ok=True)
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_ecrit_fichier_ini_dans_dest(
        self, tmp_path: Path
    ) -> None:
        """Écrit le fichier INI reconstruit dans dest_dir."""
        toml_path = self._make_toml(
            tmp_path / "src", "mon-service.toml"
        )
        dest_dir = tmp_path / "dest"
        restorer = _make_restorer()
        with (
            patch("subprocess.run"),
        ):
            ok, name = restorer.restore(toml_path, dest_dir)

        assert ok is True
        assert name == "mon.service"
        assert (dest_dir / "mon.service").exists()

    def test_active_si_enabled_true(self, tmp_path: Path) -> None:
        """Appelle enable sur l'executor si enabled=true."""
        toml_path = self._make_toml(
            tmp_path / "src", "mon-service.toml", enabled=True
        )
        dest_dir = tmp_path / "dest"
        executor = MagicMock()
        restorer = _make_restorer(executor=executor)
        ok, _ = restorer.restore(toml_path, dest_dir)

        assert ok is True
        executor.enable_unit.assert_called_once_with("mon.service")

    def test_pas_enable_si_enabled_false(self, tmp_path: Path) -> None:
        """Ne pas appeler enable si enabled=false."""
        toml_path = self._make_toml(
            tmp_path / "src", "mon-service.toml", enabled=False
        )
        dest_dir = tmp_path / "dest"
        executor = MagicMock()
        restorer = _make_restorer(executor=executor)
        restorer.restore(toml_path, dest_dir)

        executor.enable_unit.assert_not_called()

    def test_daemon_reload_apres_ecriture(self, tmp_path: Path) -> None:
        """daemon-reload est appelé après écriture réussie."""
        toml_path = self._make_toml(
            tmp_path / "src", "mon-service.toml"
        )
        dest_dir = tmp_path / "dest"
        executor = MagicMock()
        restorer = _make_restorer(executor=executor)
        restorer.restore(toml_path, dest_dir)

        executor.reload_systemd.assert_called_once()

    def test_requires_exec_absent_retourne_false(
        self, tmp_path: Path
    ) -> None:
        """Retourne False si requires_exec pointe vers un binaire absent."""
        toml_path = self._make_toml(
            tmp_path / "src",
            "mon-service.toml",
            requires_exec="/usr/bin/binaire-inexistant-xyz",
        )
        dest_dir = tmp_path / "dest"
        restorer = _make_restorer()
        ok, name = restorer.restore(toml_path, dest_dir)

        assert ok is False
        assert name == ""

    def test_requires_exec_present_accepte(
        self, tmp_path: Path
    ) -> None:
        """Accepte si requires_exec pointe vers un binaire existant."""
        toml_path = self._make_toml(
            tmp_path / "src",
            "mon-service.toml",
            requires_exec="/usr/bin/python3",
        )
        dest_dir = tmp_path / "dest"
        executor = MagicMock()
        restorer = _make_restorer(executor=executor)
        with patch.object(
            SystemdUnitRestorer,
            "_exec_present",
            return_value=True,
        ):
            ok, _ = restorer.restore(toml_path, dest_dir)

        assert ok is True

    def test_dry_run_ne_cree_pas_fichier(
        self, tmp_path: Path
    ) -> None:
        """En dry_run, aucun fichier n'est créé."""
        toml_path = self._make_toml(
            tmp_path / "src", "mon-service.toml"
        )
        dest_dir = tmp_path / "dest"
        restorer = _make_restorer()
        ok, name = restorer.restore(toml_path, dest_dir, dry_run=True)

        assert ok is True
        assert name == ""
        assert not (dest_dir / "mon.service").exists()

    def test_unit_type_invalide_retourne_false(
        self, tmp_path: Path
    ) -> None:
        """Retourne False si unit_type est invalide."""
        content = (
            "[meta]\n"
            'unit_type = "socket"\n'
            "enabled = false\n"
            'requires_exec = ""\n'
        )
        toml_path = tmp_path / "mon-socket.toml"
        toml_path.write_text(content)
        dest_dir = tmp_path / "dest"
        logger = MagicMock()
        restorer = _make_restorer(logger=logger)
        ok, _ = restorer.restore(toml_path, dest_dir)

        assert ok is False
        logger.log_error.assert_called_once()

    def test_toml_illisible_retourne_false(
        self, tmp_path: Path
    ) -> None:
        """Retourne False si le fichier TOML est illisible."""
        toml_path = tmp_path / "absent-service.toml"
        dest_dir = tmp_path / "dest"
        logger = MagicMock()
        restorer = _make_restorer(logger=logger)
        ok, _ = restorer.restore(toml_path, dest_dir)

        assert ok is False
        logger.log_error.assert_called_once()

    def test_toml_invalide_retourne_false(
        self, tmp_path: Path
    ) -> None:
        """Retourne False si le contenu TOML est malformé."""
        toml_path = tmp_path / "broken-service.toml"
        toml_path.write_text("ceci n'est pas du TOML valide [[[")
        dest_dir = tmp_path / "dest"
        logger = MagicMock()
        restorer = _make_restorer(logger=logger)
        ok, _ = restorer.restore(toml_path, dest_dir)

        assert ok is False

    def test_sans_executor_appelle_subprocess(
        self, tmp_path: Path
    ) -> None:
        """Sans executor, subprocess.run est appelé pour enable et reload."""
        toml_path = self._make_toml(
            tmp_path / "src", "mon-service.toml", enabled=True
        )
        dest_dir = tmp_path / "dest"
        restorer = SystemdUnitRestorer(logger=MagicMock())
        with patch("subprocess.run") as mock_run:
            restorer.restore(toml_path, dest_dir)

        calls = [c.args[0] for c in mock_run.call_args_list]
        assert any("enable" in c for c in calls)
        assert any("daemon-reload" in c for c in calls)

    def test_user_true_sans_executor_ajoute_flag_user(
        self, tmp_path: Path
    ) -> None:
        """Avec user=True sans executor, --user est ajouté aux commandes."""
        toml_path = self._make_toml(
            tmp_path / "src", "mon-service.toml", enabled=True
        )
        dest_dir = tmp_path / "dest"
        restorer = SystemdUnitRestorer(logger=MagicMock())
        with patch("subprocess.run") as mock_run:
            restorer.restore(toml_path, dest_dir, user=True)

        all_args = [a for c in mock_run.call_args_list for a in c.args[0]]
        assert "--user" in all_args

    def test_sans_logger_utilise_console_logger(
        self, tmp_path: Path
    ) -> None:
        """Fonctionne sans logger explicite (ConsoleLogger par défaut)."""
        toml_path = tmp_path / "absent-service.toml"
        dest_dir = tmp_path / "dest"
        restorer = SystemdUnitRestorer()
        ok, _ = restorer.restore(toml_path, dest_dir)
        assert ok is False

    def test_deduit_nom_unit_depuis_nom_fichier(
        self, tmp_path: Path
    ) -> None:
        """Déduit correctement le nom de l'unit depuis le nom TOML."""
        toml_path = self._make_toml(
            tmp_path / "src", "thermal-monitor-service.toml"
        )
        dest_dir = tmp_path / "dest"
        executor = MagicMock()
        restorer = _make_restorer(executor=executor)
        ok, name = restorer.restore(toml_path, dest_dir)

        assert ok is True
        assert name == "thermal-monitor.service"
        assert (dest_dir / "thermal-monitor.service").exists()

    def test_rejette_stem_incoherent_avec_unit_type(
        self, tmp_path: Path
    ) -> None:
        """Retourne False si le stem TOML ne se termine pas par -{unit_type}."""
        content = (
            "[meta]\n"
            'unit_type = "service"\n'
            "enabled = false\n"
            'requires_exec = ""\n'
        )
        # nom = "mon-timer.toml" mais unit_type = "service"
        toml_path = tmp_path / "mon-timer.toml"
        toml_path.write_text(content)
        logger = MagicMock()
        restorer = _make_restorer(logger=logger)
        ok, _ = restorer.restore(toml_path, tmp_path / "dest")

        assert ok is False
        logger.log_error.assert_called_once()

    def test_rejette_unit_name_traversal(
        self, tmp_path: Path
    ) -> None:
        """Retourne False si le nom déduit tente un path traversal."""
        content = (
            "[meta]\n"
            'unit_type = "service"\n'
            "enabled = false\n"
            'requires_exec = ""\n'
        )
        # stem = "../etc/cron.d/x-service" → unit_name = "../etc/cron.d/x.service"
        toml_path = tmp_path / "..etc.cron.d.x-service.toml"
        toml_path.write_text(content)
        logger = MagicMock()
        restorer = _make_restorer(logger=logger)
        ok, _ = restorer.restore(toml_path, tmp_path / "dest")

        assert ok is False

    def test_refuse_symlink_dans_dest(
        self, tmp_path: Path
    ) -> None:
        """write_text_secure lève OSError si dest est un symlink."""
        toml_path = self._make_toml(
            tmp_path / "src", "mon-service.toml"
        )
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        target = dest_dir / "mon.service"
        cible = tmp_path / "autre_fichier"
        cible.write_text("")
        target.symlink_to(cible)

        restorer = _make_restorer()
        ok, _ = restorer.restore(toml_path, dest_dir)

        assert ok is False

    def test_to_ini_rejette_newline_dans_valeur(self) -> None:
        """to_ini lève ValueError si une valeur contient un \\n."""
        data = {
            "Unit": {"Description": "légitime\nExecStart=/bin/evil"},
            "Service": {"ExecStart": "/usr/bin/foo"},
        }
        with pytest.raises(ValueError, match="contrôle"):
            SystemdUnitRestorer.to_ini(data, "service")


# ---------------------------------------------------------------------------
# Tests d'import depuis la racine du package
# ---------------------------------------------------------------------------


class TestImportDepuisRacine:
    """Vérifie que les nouvelles classes sont accessibles depuis la racine."""

    def test_import_exporter_depuis_systemd(self) -> None:
        """SystemdUnitExporter est importable depuis linuxtools.systemd."""
        from linuxtools.systemd import SystemdUnitExporter  # noqa: F401

    def test_import_restorer_depuis_systemd(self) -> None:
        """SystemdUnitRestorer est importable depuis linuxtools.systemd."""
        from linuxtools.systemd import SystemdUnitRestorer  # noqa: F401

    def test_import_exporter_depuis_racine(self) -> None:
        """SystemdUnitExporter est importable depuis linuxtools."""
        from linuxtools import SystemdUnitExporter  # noqa: F401

    def test_import_restorer_depuis_racine(self) -> None:
        """SystemdUnitRestorer est importable depuis linuxtools."""
        from linuxtools import SystemdUnitRestorer  # noqa: F401
