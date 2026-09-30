"""Tests pour le module deploy.models."""

from pathlib import Path

import pytest

from linuxtools.deploy.models import (
    CheckResult,
    DeployConfig,
    DeployPhase,
    DeployReport,
    DeployTarget,
    VerificationSpec,
)


class TestDeployTarget:
    """Tests pour la dataclass DeployTarget."""

    def test_is_remote_faux_par_defaut(self) -> None:
        """Une cible sans host est locale."""
        target = DeployTarget()
        assert target.is_remote is False

    def test_is_remote_vrai_avec_host(self) -> None:
        """Une cible avec host est distante."""
        target = DeployTarget(host="srv01")
        assert target.is_remote is True

    def test_ssh_destination_leve_erreur_si_locale(self) -> None:
        """ssh_destination lève ValueError sur une cible locale."""
        target = DeployTarget()
        with pytest.raises(ValueError, match="distante"):
            _ = target.ssh_destination

    def test_ssh_destination_sans_user(self) -> None:
        """ssh_destination retourne le host seul sans user."""
        target = DeployTarget(host="srv01")
        assert target.ssh_destination == "srv01"

    def test_ssh_destination_avec_user(self) -> None:
        """ssh_destination retourne user@host si user est renseigné."""
        target = DeployTarget(host="srv01", user="deploy")
        assert target.ssh_destination == "deploy@srv01"

    def test_ssh_options_par_defaut_vide(self) -> None:
        """ssh_options est un tuple vide par défaut."""
        target = DeployTarget()
        assert target.ssh_options == ()

    def test_frozen(self) -> None:
        """DeployTarget est immuable."""
        target = DeployTarget(host="srv01")
        with pytest.raises(AttributeError):
            target.host = "autre"  # type: ignore[misc]


class TestVerificationSpec:
    """Tests pour la dataclass VerificationSpec."""

    def test_valeurs_par_defaut(self) -> None:
        """Les listes sont vides et regression_command est None."""
        spec = VerificationSpec()
        assert spec.imports == ()
        assert spec.subcommands == ()
        assert spec.regression_command is None

    def test_frozen(self) -> None:
        """VerificationSpec est immuable."""
        spec = VerificationSpec(imports=("os",))
        with pytest.raises(AttributeError):
            spec.imports = ("sys",)  # type: ignore[misc]


class TestDeployConfig:
    """Tests pour la dataclass DeployConfig."""

    def test_source_dir_optionnel(self) -> None:
        """source_dir peut être None (auto-détection V1)."""
        config = DeployConfig(
            source_dir=None,
            venv_path=Path("/opt/app/venv"),
            remote_source_dir=Path("/opt/app/src"),
        )
        assert config.source_dir is None

    def test_valeurs_par_defaut(self) -> None:
        """target, verification et recreate_venv ont des défauts."""
        config = DeployConfig(
            source_dir=Path("/src"),
            venv_path=Path("/opt/app/venv"),
            remote_source_dir=Path("/opt/app/src"),
        )
        assert config.target == DeployTarget()
        assert config.verification == VerificationSpec()
        assert config.recreate_venv is False
        assert config.cli_bin is None

    def test_frozen(self) -> None:
        """DeployConfig est immuable."""
        config = DeployConfig(
            source_dir=Path("/src"),
            venv_path=Path("/opt/app/venv"),
            remote_source_dir=Path("/opt/app/src"),
        )
        with pytest.raises(AttributeError):
            config.venv_path = Path("/autre")  # type: ignore[misc]

    def test_atomic_swap_et_keep_versions_valeurs_par_defaut(self) -> None:
        """atomic_swap est opt-in (False) et keep_versions vaut 2."""
        config = DeployConfig(
            source_dir=Path("/src"),
            venv_path=Path("/opt/app/venv"),
            remote_source_dir=Path("/opt/app/src"),
        )
        assert config.atomic_swap is False
        assert config.keep_versions == 2

    def test_keep_versions_inferieur_a_un_leve_value_error(self) -> None:
        """keep_versions < 1 est rejeté à la construction."""
        with pytest.raises(ValueError, match="keep_versions"):
            DeployConfig(
                source_dir=Path("/src"),
                venv_path=Path("/opt/app/venv"),
                remote_source_dir=Path("/opt/app/src"),
                keep_versions=0,
            )


class TestCheckResult:
    """Tests pour la dataclass CheckResult."""

    def test_detail_vide_par_defaut(self) -> None:
        """detail est une chaîne vide par défaut."""
        check = CheckResult(label="import os", ok=True)
        assert check.detail == ""

    def test_frozen(self) -> None:
        """CheckResult est immuable."""
        check = CheckResult(label="import os", ok=True)
        with pytest.raises(AttributeError):
            check.ok = False  # type: ignore[misc]


class TestDeployPhase:
    """Tests pour l'énumération DeployPhase."""

    def test_valeurs_dans_l_ordre_attendu(self) -> None:
        """Vérifie les valeurs textuelles de chaque phase."""
        assert DeployPhase.TRANSPORT.value == "transport"
        assert DeployPhase.BACKUP.value == "backup"
        assert DeployPhase.INSTALL.value == "install"
        assert DeployPhase.VERIFY.value == "verify"
        assert DeployPhase.ROLLBACK.value == "rollback"
        assert DeployPhase.DONE.value == "done"

    def test_activate_est_entre_verify_et_rollback(self) -> None:
        """ACTIVATE existe et se situe entre VERIFY et ROLLBACK."""
        assert DeployPhase.ACTIVATE.value == "activate"
        members = list(DeployPhase)
        assert members.index(DeployPhase.VERIFY) < members.index(
            DeployPhase.ACTIVATE
        )
        assert members.index(DeployPhase.ACTIVATE) < members.index(
            DeployPhase.ROLLBACK
        )


class TestDeployReportFormatSummary:
    """Tests pour DeployReport.format_summary()."""

    def test_succes_sans_checks(self) -> None:
        """Un succès sans checks affiche le statut et la phase."""
        report = DeployReport(success=True, phase_reached=DeployPhase.DONE)
        summary = report.format_summary()
        assert "Succès" in summary
        assert "done" in summary

    def test_echec_affiche_croix(self) -> None:
        """Un échec affiche le symbole d'échec."""
        report = DeployReport(
            success=False, phase_reached=DeployPhase.TRANSPORT
        )
        summary = report.format_summary()
        assert "Échec" in summary
        assert "transport" in summary

    def test_checks_affiches_avec_symboles(self) -> None:
        """Les checks OK/KO sont listés avec leur symbole."""
        report = DeployReport(
            success=False,
            phase_reached=DeployPhase.VERIFY,
            checks=(
                CheckResult(label="import os", ok=True),
                CheckResult(
                    label="import bad", ok=False, detail="ModuleError"
                ),
            ),
        )
        summary = report.format_summary()
        assert "✓ import os" in summary
        assert "✗ import bad (ModuleError)" in summary
        assert "1/2" in summary

    def test_rollback_affiche_backup_path(self) -> None:
        """Le rollback mentionne le chemin de backup."""
        report = DeployReport(
            success=False,
            phase_reached=DeployPhase.ROLLBACK,
            rolled_back=True,
            backup_path=Path("/opt/app/venv.bak-20260719-120000"),
        )
        summary = report.format_summary()
        assert "Rollback effectué" in summary
        assert "venv.bak-20260719-120000" in summary

    def test_messages_inclus_dans_le_resume(self) -> None:
        """Les messages du journal apparaissent dans le résumé."""
        report = DeployReport(
            success=True,
            phase_reached=DeployPhase.DONE,
            messages=("Source auto-détecté : /home/user/app",),
        )
        summary = report.format_summary()
        assert "Source auto-détecté : /home/user/app" in summary

    def test_frozen(self) -> None:
        """DeployReport est immuable."""
        report = DeployReport(success=True, phase_reached=DeployPhase.DONE)
        with pytest.raises(AttributeError):
            report.success = False  # type: ignore[misc]

    def test_active_version_affichee_dans_le_resume(self) -> None:
        """La version active est affichée si renseignée."""
        report = DeployReport(
            success=True,
            phase_reached=DeployPhase.DONE,
            active_version=Path("/opt/app/venvs/app-20260929-120000-000000"),
        )
        summary = report.format_summary()
        assert (
            "Version active : /opt/app/venvs/app-20260929-120000-000000"
            in summary
        )

    def test_fallback_version_affichee_dans_le_resume(self) -> None:
        """La version de repli est affichée si renseignée."""
        report = DeployReport(
            success=True,
            phase_reached=DeployPhase.DONE,
            fallback_version=Path("/opt/app/venvs/app-20260928-000000-000000"),
        )
        summary = report.format_summary()
        assert (
            "Version de repli : /opt/app/venvs/app-20260928-000000-000000"
            in summary
        )

    def test_versions_absentes_ne_sont_pas_affichees(self) -> None:
        """Sans active_version/fallback_version, rien n'est affiché."""
        report = DeployReport(success=True, phase_reached=DeployPhase.DONE)
        summary = report.format_summary()
        assert "Version active" not in summary
        assert "Version de repli" not in summary
