"""Tests pour le module deploy.venv_release."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import CheckResult, DeployPhase
from linuxtools.deploy.venv_installer import VenvInstaller
from linuxtools.deploy.venv_release import (
    VenvReleaser,
    _ensure_managed_link_target,
    _managed_version_path,
    _new_version_id,
    _validate_venv_path,
    _version_id_pattern,
    _versions_dir,
    select_versions_to_prune,
)


def _result(
    success: bool = True,
    stdout: str = "",
    stderr: str = "",
    return_code: int | None = None,
) -> CommandResult:
    """Construit un CommandResult scripté pour les tests.

    Args:
        success: Statut de réussite simulé.
        stdout: Sortie standard simulée.
        stderr: Sortie d'erreur simulée.
        return_code: Code de retour explicite (par défaut, dérivé de
            success : 0 si succès, 1 sinon). Permet de distinguer un
            échec "confirmé" (ex. readlink return_code=1) d'un échec
            de transport (ex. return_code=255) — F10.
    """
    if return_code is None:
        return_code = 0 if success else 1
    return CommandResult(
        command=(),
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        success=success,
        duration=0.01,
    )


def _make_executor() -> MagicMock:
    """Crée un mock de CommandExecutor cible."""
    return MagicMock(spec=CommandExecutor)


class TestValidateVenvPath:
    """Tests pour _validate_venv_path (validation pure, T2/SEC)."""

    def test_chemin_absolu_normalise_ne_leve_pas(self) -> None:
        """Un chemin absolu normalisé, non racine, ne lève rien."""
        _validate_venv_path(Path("/opt/app/venv"))

    def test_chemin_relatif_leve_deploy_error(self) -> None:
        """Un chemin relatif est refusé."""
        with pytest.raises(DeployError, match="absolu"):
            _validate_venv_path(Path("venv"))

    def test_chemin_avec_parent_relatif_leve_deploy_error(self) -> None:
        """Un chemin contenant '..' (non normalisé) est refusé."""
        with pytest.raises(DeployError, match="normalisé"):
            _validate_venv_path(Path("/opt/../venv"))

    def test_chemin_avec_parent_racine_leve_deploy_error(self) -> None:
        """Un venv directement sous la racine est refusé (pas de
        répertoire 'venvs' fiable à côté)."""
        with pytest.raises(DeployError, match="racine"):
            _validate_venv_path(Path("/venv"))


class TestVersionsDir:
    """Tests pour _versions_dir (emplacement des versions, Q-02)."""

    def test_repertoire_venvs_a_cote_du_venv(self) -> None:
        """venvs/ est un frère de venv_path, sous son parent."""
        assert _versions_dir(Path("/opt/app/venv")) == Path("/opt/app/venvs")


class TestNewVersionId:
    """Tests pour _new_version_id (id horodaté, horloge injectable)."""

    def test_id_combine_nom_et_horodatage(self) -> None:
        """L'id combine <name>-<YYYYmmdd-HHMMSS-ffffff>."""
        now = datetime(2026, 9, 29, 16, 49, 0, 123456)
        assert _new_version_id("app", now) == "app-20260929-164900-123456"


class TestVersionIdPattern:
    """Tests pour _version_id_pattern (namespacage par nom, SEC)."""

    def test_id_conforme_matche(self) -> None:
        """Un id bien formé pour ce nom matche le motif."""
        pattern = _version_id_pattern("app")
        assert pattern.fullmatch("app-20260929-164900-123456")

    def test_id_legacy_matche(self) -> None:
        """Le suffixe -legacy est accepté."""
        pattern = _version_id_pattern("app")
        assert pattern.fullmatch("app-20260929-164900-123456-legacy")

    def test_id_d_un_autre_outil_ne_matche_pas(self) -> None:
        """Un id d'un autre outil partageant le parent ne matche pas
        (protection contre la purge d'un outil voisin)."""
        pattern = _version_id_pattern("app")
        assert not pattern.fullmatch("autre-outil-20260929-164900-123456")

    def test_nom_avec_metacaractere_regex_est_echappe(self) -> None:
        """Un nom d'outil contenant un métacaractère regex (ex. '.')
        est traité littéralement (re.escape) : le motif ne doit pas
        matcher un id où ce caractère a été substitué (mutation
        contrôlée — sans re.escape, '.' matcherait n'importe quel
        caractère, ouvrant une purge sur un id d'un autre outil)."""
        pattern = _version_id_pattern("app.bak")
        assert not pattern.fullmatch("appXbak-20260929-164900-123456")
        assert pattern.fullmatch("app.bak-20260929-164900-123456")


class TestManagedVersionPath:
    """Tests pour _managed_version_path (reconstruction, SEC)."""

    def test_id_conforme_reconstruit_le_chemin(self) -> None:
        """Un id conforme (basé sur venv_path.name) est reconstruit
        sous versions_dir."""
        path = _managed_version_path(
            Path("/opt/app/venv"), "venv-20260929-164900-123456"
        )
        assert path == Path("/opt/app/venvs/venv-20260929-164900-123456")

    def test_id_etranger_leve_deploy_error(self) -> None:
        """Un id ne matchant pas le nom de l'outil est refusé (pas de
        purge d'un outil voisin partageant le même parent)."""
        with pytest.raises(DeployError):
            _managed_version_path(Path("/opt/app/venv"), "../etc/passwd")


class TestEnsureManagedLinkTarget:
    """Tests pour _ensure_managed_link_target (F07 : dédup validation)."""

    def test_cible_geree_sous_expected_dir_ne_leve_pas(self) -> None:
        """Une cible conforme au motif namespacé, sous expected_dir,
        ne lève rien."""
        _ensure_managed_link_target(
            venv_path=Path("/opt/app/venv"),
            expected_dir=Path("/opt/app/venvs"),
            target=Path("/opt/app/venvs/venv-20260901-000000-000000"),
        )

    def test_cible_hors_expected_dir_leve_deploy_error(self) -> None:
        """Une cible hors expected_dir (même motif) est refusée."""
        with pytest.raises(DeployError, match="non géré"):
            _ensure_managed_link_target(
                venv_path=Path("/opt/app/venv"),
                expected_dir=Path("/opt/app/venvs"),
                target=Path("/usr/venv-20260901-000000-000000"),
            )

    def test_cible_ne_matchant_pas_le_motif_leve_deploy_error(self) -> None:
        """Une cible sous expected_dir mais ne matchant pas le motif
        namespacé de venv_path.name est refusée."""
        with pytest.raises(DeployError, match="non géré"):
            _ensure_managed_link_target(
                venv_path=Path("/opt/app/venv"),
                expected_dir=Path("/opt/app/venvs"),
                target=Path(
                    "/opt/app/venvs/autre-outil-20260901-000000-000000"
                ),
            )


class TestVenvReleaserClockParDefaut:
    """Tests pour l'horloge par défaut de VenvReleaser (F08)."""

    def test_horloge_par_defaut_est_utc(self) -> None:
        """Sans argument clock, l'horloge par défaut est en UTC (pas
        l'heure locale, non monotone au changement d'heure été/hiver)."""
        releaser = VenvReleaser(_make_executor(), installer=MagicMock())

        assert releaser._clock().tzinfo is UTC  # noqa: SLF001


class TestSelectVersionsToPrune:
    """Tests pour select_versions_to_prune (politique de rétention)."""

    def test_liste_vide_ne_purge_rien(self) -> None:
        """Une liste vide de versions ne produit aucune purge."""
        result = select_versions_to_prune(
            version_ids=(),
            name="app",
            active_id="app-3",
            previous_id=None,
            keep=2,
        )
        assert result == ()

    def test_ids_etrangers_ignores(self) -> None:
        """Un id d'un autre outil partageant le parent n'est jamais
        purgé (ni conservé) : il est simplement ignoré."""
        result = select_versions_to_prune(
            version_ids=(
                "app-20260901-000000-000000",
                "autre-outil-20260901-000000-000000",
            ),
            name="app",
            active_id="app-20260910-000000-000000",
            previous_id=None,
            keep=1,
        )
        assert "autre-outil-20260901-000000-000000" not in result

    def test_id_etranger_lexicographiquement_anterieur_jamais_purge(
        self,
    ) -> None:
        """Un id étranger dont la chaîne trie avant l'id actif
        (mutation contrôlée : sans le filtre par motif, il serait
        pris pour une version plus ancienne et purgé à tort) n'est
        jamais retourné."""
        result = select_versions_to_prune(
            version_ids=(
                "app-20260910-000000-000000",
                "aaa-tool-20260901-000000-000000",
            ),
            name="app",
            active_id="app-20260910-000000-000000",
            previous_id=None,
            keep=1,
        )
        assert "aaa-tool-20260901-000000-000000" not in result
        assert result == ()

    def test_legacy_le_plus_ancien_purge_en_premier(self) -> None:
        """Le suffixe -legacy n'influe pas sur l'ordre chronologique :
        un legacy plus ancien est purgé avant une version plus récente."""
        result = select_versions_to_prune(
            version_ids=(
                "app-20260901-000000-000000-legacy",
                "app-20260910-000000-000000",
                "app-20260920-000000-000000",
            ),
            name="app",
            active_id="app-20260920-000000-000000",
            previous_id="app-20260910-000000-000000",
            keep=2,
        )
        assert result == ("app-20260901-000000-000000-legacy",)

    def test_keep_un_protege_quand_meme_la_precedente(self) -> None:
        """keep=1 : previous_id reste protégé (avenant CDC Q-05) —
        l'hôte conserve donc en pratique 2 versions (active + previous),
        comme avec keep=2 (F01/F02)."""
        result = select_versions_to_prune(
            version_ids=(
                "app-20260901-000000-000000",
                "app-20260910-000000-000000",
            ),
            name="app",
            active_id="app-20260910-000000-000000",
            previous_id="app-20260901-000000-000000",
            keep=1,
        )
        assert result == ()

    def test_keep_deux_conserve_la_precedente(self) -> None:
        """keep=2 : active + previous_id sont conservées, previous_id
        étant protégé explicitement (pas seulement parce qu'il serait
        le plus récent antérieur — ici il ne l'est pas)."""
        result = select_versions_to_prune(
            version_ids=(
                "app-20260901-000000-000000",  # previous_id, pas le +récent
                "app-20260905-000000-000000",  # plus récent, purgé
                "app-20260920-000000-000000",  # active
            ),
            name="app",
            active_id="app-20260920-000000-000000",
            previous_id="app-20260901-000000-000000",
            keep=2,
        )
        assert result == ("app-20260905-000000-000000",)

    def test_previous_toujours_protege_meme_si_chronologiquement_ancien(
        self,
    ) -> None:
        """Après un rollback vers v1 puis un nouveau déploiement v3,
        previous_id=v1 est protégé même si v2 (non actif, non repli)
        est chronologiquement plus récent (F01/F02)."""
        result = select_versions_to_prune(
            version_ids=(
                "app-20260901-000000-000000",  # v1 = previous (repli rollback)
                "app-20260910-000000-000000",  # v2 = ni actif ni repli
                "app-20260920-000000-000000",  # v3 = active
            ),
            name="app",
            active_id="app-20260920-000000-000000",
            previous_id="app-20260901-000000-000000",
            keep=2,
        )
        assert "app-20260901-000000-000000" not in result
        assert result == ("app-20260910-000000-000000",)

    def test_nom_explicite_evite_le_bug_rsplit_sur_active_id_legacy(
        self,
    ) -> None:
        """active_id se terminant par -legacy : avec l'ancienne
        dérivation par `active_id.rsplit("-", 3)[0]`, le nom extrait
        était tronqué ("app-20260920" au lieu de "app"), le motif ne
        matchait donc plus aucun id — le nom est désormais reçu
        explicitement, indépendant de la forme d'active_id (F07)."""
        result = select_versions_to_prune(
            version_ids=(
                "app-20260901-000000-000000",
                "app-20260920-000000-000000-legacy",
            ),
            name="app",
            active_id="app-20260920-000000-000000-legacy",
            previous_id=None,
            keep=1,
        )
        assert result == ("app-20260901-000000-000000",)

    def test_id_futur_jamais_purge(self) -> None:
        """Un id postérieur à active_id (déploiement concurrent)
        n'est jamais purgé."""
        result = select_versions_to_prune(
            version_ids=(
                "app-20260901-000000-000000",
                "app-20260930-000000-000000",
            ),
            name="app",
            active_id="app-20260910-000000-000000",
            previous_id=None,
            keep=1,
        )
        assert "app-20260930-000000-000000" not in result


class TestVenvReleaserCurrentState:
    """Tests pour VenvReleaser._current_state (F16, avenant CONCEPTION §61)."""

    def test_readlink_ambigu_leve_deploy_error(self) -> None:
        """readlink échoue avec un return_code différent de 1 (ex. 255 :
        échec de transport ssh) : état indéterminé, DeployError est
        levée, aucun test -d/test -e n'est tenté (F16 — test -d/test -e
        suivent les liens symboliques et classeraient à tort un lien
        géré en "dir"/"other")."""
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False, return_code=255),  # échec de transport
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        with pytest.raises(DeployError, match="indéterminé"):
            releaser._current_state(Path("/opt/app/venv"))  # noqa: SLF001

        assert executor.run.call_count == 1


class TestVenvReleaserActivate:
    """Tests pour VenvReleaser.activate (T5, SEC)."""

    def test_activate_vers_version_legacy_refuse_par_deploy_error(
        self,
    ) -> None:
        """version_path suffixé -legacy est refusé quand venv_path est
        encore un répertoire réel (état "dir") : la migration n'a pas
        encore eu lieu, il n'y a pas de version antérieure à
        re-horodater (F12/F14 — ce refus ne s'applique plus qu'à
        l'état "dir", jamais à un rollback légitime en état "link")."""
        # Nom conforme au motif namespacé de venv_path (name="venv"),
        # suffixe -legacy inclus : la version_path est donc reconnue
        # comme "gérée" par la validation générique — seul le nouveau
        # garde-fou explicite sur le suffixe -legacy doit la refuser.
        legacy_version = Path(
            "/opt/app/venvs/venv-20260901-000000-000000-legacy"
        )
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False, return_code=1),  # readlink échoue
            _result(success=True),  # test -d venv_path réussit -> dir
        ]

        with pytest.raises(DeployError, match="legacy"):
            VenvReleaser(executor, installer=MagicMock()).activate(
                Path("/opt/app/venv"), legacy_version
            )

        assert executor.run.call_count == 3

    def test_activate_vers_version_legacy_en_etat_link_bascule(self) -> None:
        """version_path suffixé -legacy est accepté quand venv_path est
        déjà un lien (état "link") : c'est exactement le scénario de
        rollback vers fallback_version après une migration (F14,
        régression du correctif F12 de la passe 2 — le refus ne doit
        s'appliquer qu'à l'état "dir")."""
        legacy_version = Path(
            "/opt/app/venvs/venv-20260901-000000-000000-legacy"
        )
        current_target = "/opt/app/venvs/venv-20260929-164900-000000"
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=True, stdout=current_target + "\n"),  # readlink
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # mv -T tmp -> venv_path
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        previous = releaser.activate(Path("/opt/app/venv"), legacy_version)

        assert previous == Path(current_target)
        mv_call = executor.run.call_args_list[-1].args[0]
        assert mv_call[0] == "mv"

    def test_bascule_lien_vers_lien_retourne_ancienne_cible(self) -> None:
        """venv_path est déjà un lien géré : ln -sfn puis mv -T,
        retourne l'ancienne cible."""
        old_target = "/opt/app/venvs/venv-20260901-000000-000000"
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=True, stdout=old_target + "\n"),  # readlink
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # mv -T tmp -> venv_path
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        previous = releaser.activate(Path("/opt/app/venv"), new_version)

        assert previous == Path(old_target)

    def test_venv_path_absent_retourne_none(self) -> None:
        """venv_path absent : bascule directe, retourne None."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False),  # readlink échoue
            _result(success=False),  # test -d venv_path échoue
            _result(success=False),  # test -e échoue -> absent
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # mv -T tmp -> venv_path
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        previous = releaser.activate(Path("/opt/app/venv"), new_version)

        assert previous is None

    def test_lien_vers_cible_non_geree_leve_deploy_error(self) -> None:
        """venv_path est un lien vers une cible hors venvs/ : refus,
        aucune commande de bascule n'est tentée."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=True, stdout="/usr\n"),  # readlink
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        with pytest.raises(DeployError, match="non géré"):
            releaser.activate(Path("/opt/app/venv"), new_version)

        assert executor.run.call_count == 2

    def test_venv_path_est_un_fichier_leve_deploy_error(self) -> None:
        """venv_path existe mais n'est ni un lien ni un répertoire."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False),  # readlink échoue
            _result(success=False),  # test -d venv_path échoue
            _result(success=True),  # test -e réussit -> other
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        with pytest.raises(DeployError, match="ni un lien ni un"):
            releaser.activate(Path("/opt/app/venv"), new_version)

    def test_etat_lien_sans_cible_leve_deploy_error(self) -> None:
        """État incohérent ("link", None) : DeployError explicite, pas
        un AttributeError (F06 : l'invariant survit à python -O)."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        releaser = VenvReleaser(_make_executor(), installer=MagicMock())
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                releaser, "_current_state", lambda _venv_path: ("link", None)
            )

            with pytest.raises(DeployError, match="incohérent"):
                releaser.activate(Path("/opt/app/venv"), new_version)

    def test_version_path_hors_venvs_leve_deploy_error(self) -> None:
        """version_path qui n'est pas sous versions_dir est refusé
        avant toute commande."""
        executor = _make_executor()
        releaser = VenvReleaser(executor, installer=MagicMock())

        with pytest.raises(DeployError, match="version gérée"):
            releaser.activate(Path("/opt/app/venv"), Path("/opt/app/autre"))

        executor.run.assert_not_called()

    def test_echec_ln_leve_deploy_error_sans_mv(self) -> None:
        """Échec de ln -sfn : DeployError, mv jamais tenté."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False),
            _result(success=False),
            _result(success=False),  # absent
            _result(success=False, stderr="ln error"),  # ln échoue
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        with pytest.raises(DeployError, match="lien temporaire"):
            releaser.activate(Path("/opt/app/venv"), new_version)

        assert executor.run.call_count == 5

    def test_echec_mv_nettoie_le_tmp_et_leve_deploy_error(self) -> None:
        """Échec de mv -T : le lien temporaire est nettoyé (rm -f)
        puis DeployError est levée."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False),
            _result(success=False),
            _result(success=False),  # absent
            _result(success=True),  # ln réussit
            _result(success=False, stderr="mv error"),  # mv échoue
            _result(success=True),  # rm -f tmp
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        with pytest.raises(DeployError, match="bascule"):
            releaser.activate(Path("/opt/app/venv"), new_version)

        last_call = executor.run.call_args_list[-1].args[0]
        assert last_call[0] == "rm"

    def test_migration_repertoire_reel_retourne_le_legacy(self) -> None:
        """venv_path est un répertoire réel : migration en un seul
        processus <version>/bin/python -I -c, retourne le chemin
        legacy."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False),  # readlink échoue
            _result(success=True),  # test -d venv_path réussit -> dir
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # migration (python -I -c)
        ]
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 49, 0, 0))
        releaser = VenvReleaser(executor, installer=MagicMock(), clock=clock)

        previous = releaser.activate(Path("/opt/app/venv"), new_version)

        assert previous is not None
        assert previous.name.startswith("venv-")
        assert previous.name.endswith("-legacy")
        migrate_call = executor.run.call_args_list[4].args[0]
        assert migrate_call[0] == str(new_version / "bin" / "python")
        assert migrate_call[1] == "-I"
        assert migrate_call[2] == "-c"

    def test_migration_logue_le_chemin_du_legacy(self) -> None:
        """Le message de log de la migration inclut le chemin du
        legacy, pas seulement version_path (F11 : traçabilité)."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False),  # readlink échoue
            _result(success=True),  # test -d venv_path réussit -> dir
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # migration (python -I -c)
        ]
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 49, 0, 0))
        logger = MagicMock()
        releaser = VenvReleaser(
            executor, installer=MagicMock(), logger=logger, clock=clock
        )

        legacy = releaser.activate(Path("/opt/app/venv"), new_version)

        assert legacy is not None
        logger.log_info.assert_called_once()
        message = logger.log_info.call_args.args[0]
        assert str(legacy) in message
        assert str(new_version) in message

    def test_legacy_trie_toujours_avant_la_nouvelle_version(self) -> None:
        """Le legacy issu d'une migration trie toujours avant la
        version qu'il précède, même si l'horloge injectée avance
        entre-temps (F01 : reproduit la course constatée par la
        revue)."""
        new_version = Path("/opt/app/venvs/venv-20260929-164900-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False),  # readlink échoue
            _result(success=True),  # test -d venv_path réussit -> dir
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # migration (python -I -c)
        ]
        # Horloge qui a avancé entre la génération de version_id (dans
        # release(), non appelé ici) et l'appel à activate() : si
        # legacy_ts était dérivé d'une nouvelle lecture d'horloge, il
        # trierait APRÈS new_version (bug F01 reproduit).
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 50, 0, 0))
        releaser = VenvReleaser(executor, installer=MagicMock(), clock=clock)

        legacy = releaser.activate(Path("/opt/app/venv"), new_version)

        assert legacy is not None
        from linuxtools.deploy.venv_release import _version_sort_key

        assert _version_sort_key(legacy.name) < _version_sort_key(
            new_version.name
        )

    def test_activate_version_path_inexistante_refuse_avant_ln(self) -> None:
        """version_path absente sur l'hôte (test -d échoue) : refus par
        DeployError avant toute tentative de bascule (F18 — un rollback
        manuel vers un chemin erroné ne doit pas basculer le lien actif
        vers une cible absente)."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False),  # test -d version_path échoue
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        with pytest.raises(DeployError, match="n'existe pas"):
            releaser.activate(Path("/opt/app/venv"), new_version)

        assert not any(
            call.args[0][0] == "ln" for call in executor.run.call_args_list
        )

    def test_migration_echouee_nettoie_le_tmp_et_leve_deploy_error(
        self,
    ) -> None:
        """Échec de la migration : le tmp est nettoyé (rm -f), le
        script a déjà remis le répertoire d'origine en place."""
        new_version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=False),  # readlink échoue
            _result(success=True),  # test -d venv_path réussit -> dir
            _result(success=True),  # ln -sfn tmp
            _result(success=False, stderr="migration error"),
            _result(success=True),  # rm -f tmp
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        with pytest.raises(DeployError, match="migration"):
            releaser.activate(Path("/opt/app/venv"), new_version)

        last_call = executor.run.call_args_list[-1].args[0]
        assert last_call[0] == "rm"


class TestVenvReleaserDiscard:
    """Tests pour VenvReleaser._discard (garde-fou readlink, F10/T4)."""

    def test_readlink_return_code_un_confirme_absence_rm_est_appele(
        self,
    ) -> None:
        """readlink échoue avec return_code=1 (la commande s'est bien
        exécutée et confirme que venv_path n'est pas/plus un lien) :
        rm est appelé normalement (F10). Plus aucun appel à test -e :
        il suivait les liens symboliques et ne distinguait pas un lien
        géré d'un répertoire réel — c'était la source du bug."""
        venv_path = Path("/opt/app/venv")
        version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False, return_code=1),  # readlink confirme
            _result(success=True),  # rm -rf
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        releaser._discard(version, venv_path)  # noqa: SLF001

        last_call = executor.run.call_args_list[-1].args[0]
        assert last_call[:2] == ["rm", "-rf"]

    @pytest.mark.parametrize(
        "return_code",
        [-1, 127, 255],
        ids=[
            "timeout_ou_oserror_locale",
            "binaire_distant_absent",
            "echec_transport_ssh",
        ],
    )
    def test_readlink_echec_ssh_return_code_255_rm_jamais_appele(
        self, return_code: int
    ) -> None:
        """readlink échoue avec un return_code plausible différent de 1
        (-1 : timeout/OSError locale ; 127 : binaire distant absent ;
        255 : échec de transport ssh) : état indéterminé, rm n'est
        jamais appelé, un message d'erreur est loggué (F10/F17)."""
        venv_path = Path("/opt/app/venv")
        version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False, return_code=return_code),
        ]
        logger = MagicMock()
        releaser = VenvReleaser(executor, installer=MagicMock(), logger=logger)

        releaser._discard(version, venv_path)  # noqa: SLF001

        assert not any(
            call.args[0][0] == "rm" for call in executor.run.call_args_list
        )
        logger.log_error.assert_called_once()
        assert "indéterminé" in logger.log_error.call_args.args[0]

    def test_rm_reussi_logue_la_version_supprimee(self) -> None:
        """Un rm -rf réussi pendant _discard est loggué (F11 :
        traçabilité — jusque-là seuls les échecs étaient loggués)."""
        venv_path = Path("/opt/app/venv")
        version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False),  # readlink échoue, confirme (F15 : plus
            # de réponse test -e mockée ici, retirée par F10 — elle était
            # consommée à tort par le rm -rf réel ci-dessous)
            _result(success=True),  # rm -rf réussit
        ]
        logger = MagicMock()
        releaser = VenvReleaser(executor, installer=MagicMock(), logger=logger)

        releaser._discard(version, venv_path)  # noqa: SLF001

        managed = Path("/opt/app/venvs/venv-20260929-000000-000000")
        logger.log_info.assert_called_once()
        assert str(managed) in logger.log_info.call_args.args[0]

    def test_readlink_reussit_cible_geree_rm_jamais_appele(self) -> None:
        """readlink réussit et pointe vers la version à supprimer :
        c'est la cible actuelle du lien, jamais supprimée (T5, distinct
        du cas readlink en échec couvert par T4)."""
        venv_path = Path("/opt/app/venv")
        version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(version) + "\n"),  # readlink
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        releaser._discard(version, venv_path)  # noqa: SLF001

        assert not any(
            call.args[0][0] == "rm" for call in executor.run.call_args_list
        )


class TestVenvReleaserRelease:
    """Tests pour VenvReleaser.release (T6, SEC).

    VenvInstaller est réel (sur un exécuteur mocké), pas de seam
    supplémentaire — cf. conception §2.
    """

    def test_release_current_state_ambigu_retourne_outcome_install(
        self,
    ) -> None:
        """_current_state lève DeployError (readlink ambigu, F16) :
        release() ne propage pas l'exception, elle retourne un
        ReleaseOutcome d'échec en phase INSTALL (même pattern que pour
        _validate_venv_path juste au-dessus)."""
        venv_path = Path("/opt/app/venv")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False, return_code=255),  # readlink ambigu
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())
        verify = MagicMock()

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.INSTALL
        verify.assert_not_called()

    def test_release_succes_complet(self) -> None:
        """Build → verify OK → bascule → purge : outcome DONE avec
        active_version et fallback_version."""
        venv_path = Path("/opt/app/venv")
        old_version = Path("/opt/app/venvs/venv-20260901-000000-000000")
        new_version = Path("/opt/app/venvs/venv-20260929-164900-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=False),  # test -L venvs
            _result(success=True),  # mkdir -p venvs
            _result(success=True, stdout="Python 3.11.9"),  # version
            _result(success=True),  # rm -rf version
            _result(success=True),  # python3 -m venv version
            _result(success=True),  # pip install
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # mv -T tmp -> venv_path
            _result(success=True, stdout=str(new_version) + "\n"),
            _result(
                success=True,
                stdout=f"{old_version.name}\n{new_version.name}\n",
            ),  # find (purge)
        ]
        installer = VenvInstaller(executor)
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 49, 0, 0))
        releaser = VenvReleaser(executor, installer, clock=clock)
        verify = MagicMock(
            return_value=(CheckResult(label="import app", ok=True),)
        )

        outcome = releaser.release(
            venv_path, Path("/src"), verify, keep_versions=2
        )

        assert outcome.success is True
        assert outcome.phase_reached == DeployPhase.DONE
        assert outcome.active_version == new_version
        assert outcome.fallback_version == old_version
        verify.assert_called_once_with(new_version)

    def test_verify_ko_discard_la_version_et_laisse_le_lien_intact(
        self,
    ) -> None:
        """Vérification KO : la version est supprimée, le venv actif
        n'est jamais touché (aucun ln/mv)."""
        venv_path = Path("/opt/app/venv")
        old_version = Path("/opt/app/venvs/venv-20260901-000000-000000")
        new_version = Path("/opt/app/venvs/venv-20260929-164900-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=False),  # test -L venvs
            _result(success=True),  # mkdir -p venvs
            _result(success=True, stdout="Python 3.11.9"),
            _result(success=True),  # rm -rf version
            _result(success=True),  # python3 -m venv version
            _result(success=True),  # pip install
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=True),  # rm -rf version (discard)
        ]
        installer = VenvInstaller(executor)
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 49, 0, 0))
        releaser = VenvReleaser(executor, installer, clock=clock)
        verify = MagicMock(
            return_value=(
                CheckResult(label="import app", ok=False, detail="boom"),
            )
        )

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.VERIFY
        assert outcome.active_version is None
        discard_call = executor.run.call_args_list[-1].args[0]
        assert discard_call[:2] == ["rm", "-rf"]
        assert str(new_version) in discard_call

    def test_install_echoue_discard_et_outcome_install(self) -> None:
        """Échec d'installation : discard de la version, outcome
        INSTALL, verify jamais appelée."""
        venv_path = Path("/opt/app/venv")
        old_version = Path("/opt/app/venvs/venv-20260901-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=False),  # test -L venvs
            _result(success=True),  # mkdir -p venvs
            _result(success=True, stdout="Python 3.11.9"),
            _result(success=False, stderr="rm error"),  # rm -rf échoue
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=True),  # rm -rf version (discard)
        ]
        installer = VenvInstaller(executor)
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 49, 0, 0))
        releaser = VenvReleaser(executor, installer, clock=clock)
        verify = MagicMock()

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.INSTALL
        verify.assert_not_called()
        # La version ratée doit être discardée (rm -rf) : sans ce
        # discard, aucun appel supplémentaire n'aurait lieu après
        # l'échec de rm -rf dans install() (mutation contrôlée).
        assert executor.run.call_count == 7
        last_call = executor.run.call_args_list[-1].args[0]
        assert last_call[:2] == ["rm", "-rf"]

    def test_venvs_est_un_lien_refuse_avant_build(self) -> None:
        """venvs/ est un lien : refus avant tout build (pas de
        redirection de la purge)."""
        venv_path = Path("/opt/app/venv")
        old_version = Path("/opt/app/venvs/venv-20260901-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=True),  # test -L venvs -> succès -> refus
        ]
        installer = VenvInstaller(executor)
        releaser = VenvReleaser(executor, installer)
        verify = MagicMock()

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.INSTALL
        verify.assert_not_called()

    def test_etat_lien_sans_cible_refuse_sans_lever(self) -> None:
        """État incohérent ("link", None) : ReleaseOutcome d'échec,
        jamais d'AttributeError (F06 — release() ne lève jamais)."""
        venv_path = Path("/opt/app/venv")
        installer = VenvInstaller(_make_executor())
        releaser = VenvReleaser(_make_executor(), installer)
        verify = MagicMock()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                releaser, "_current_state", lambda _venv_path: ("link", None)
            )

            outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.INSTALL
        verify.assert_not_called()

    def test_venv_path_lien_non_gere_refuse_avant_build(self) -> None:
        """venv_path pointe vers une cible hors venvs/ : refus avant
        tout build."""
        venv_path = Path("/opt/app/venv")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout="/usr\n"),
        ]
        installer = VenvInstaller(executor)
        releaser = VenvReleaser(executor, installer)
        verify = MagicMock()

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.INSTALL
        verify.assert_not_called()
        assert executor.run.call_count == 1

    def test_purge_ignoree_si_lien_change_entre_temps(self) -> None:
        """Le lien a changé depuis la bascule (déploiement
        concurrent) : aucune purge n'est tentée."""
        venv_path = Path("/opt/app/venv")
        old_version = Path("/opt/app/venvs/venv-20260901-000000-000000")
        new_version = Path("/opt/app/venvs/venv-20260929-164900-000000")
        concurrent = Path("/opt/app/venvs/venv-20260930-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=False),  # test -L venvs
            _result(success=True),  # mkdir -p venvs
            _result(success=True, stdout="Python 3.11.9"),
            _result(success=True),  # rm -rf version
            _result(success=True),  # python3 -m venv version
            _result(success=True),  # pip install
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # mv -T tmp -> venv_path
            _result(success=True, stdout=str(concurrent) + "\n"),
        ]
        installer = VenvInstaller(executor)
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 49, 0, 0))
        releaser = VenvReleaser(executor, installer, clock=clock)
        verify = MagicMock(
            return_value=(CheckResult(label="import app", ok=True),)
        )

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is True
        assert outcome.active_version == new_version
        assert executor.run.call_count == 12
        # Le lien est relu (readlink) avant toute purge : sans cette
        # relecture, le code enchaînerait directement sur `find`/`rm`
        # (mutation contrôlée).
        calls = [c.args[0] for c in executor.run.call_args_list]
        assert calls[11] == ["readlink", "--", str(venv_path)]
        assert not any(call[0] == "find" for call in calls)

    def test_venv_path_invalide_refuse_avant_toute_commande(self) -> None:
        """venv_path invalide (relatif) : outcome INSTALL immédiat,
        aucune commande exécutée (F09 : branche non couverte)."""
        installer = VenvInstaller(_make_executor())
        releaser = VenvReleaser(_make_executor(), installer)
        verify = MagicMock()

        outcome = releaser.release(Path("venv"), Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.INSTALL
        verify.assert_not_called()

    def test_venv_path_est_un_fichier_refuse_avant_build(self) -> None:
        """venv_path existe mais n'est ni un lien ni un répertoire :
        refus avant tout build (F09 : branche non couverte)."""
        venv_path = Path("/opt/app/venv")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False),  # readlink échoue
            _result(success=False),  # test -d échoue
            _result(success=True),  # test -e réussit -> other
        ]
        installer = VenvInstaller(executor)
        releaser = VenvReleaser(executor, installer)
        verify = MagicMock()

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.INSTALL
        verify.assert_not_called()

    def test_echec_mkdir_versions_dir_outcome_install(self) -> None:
        """Échec de mkdir -p sur le répertoire des versions : outcome
        INSTALL, aucune installation tentée (F09 : branche non
        couverte)."""
        venv_path = Path("/opt/app/venv")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False),  # readlink échoue
            _result(success=False),  # test -d échoue
            _result(success=False),  # test -e échoue -> absent
            _result(success=False),  # test -L venvs
            _result(success=False, stderr="mkdir error"),  # mkdir -p échoue
        ]
        installer = VenvInstaller(executor)
        releaser = VenvReleaser(executor, installer)
        verify = MagicMock()

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.INSTALL
        verify.assert_not_called()

    def test_echec_activate_discard_et_outcome_activate(self) -> None:
        """Échec d'activate() (DeployError) : discard de la version,
        outcome ACTIVATE, success False (F09 : branche non couverte)."""
        venv_path = Path("/opt/app/venv")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False),  # readlink échoue
            _result(success=False),  # test -d échoue
            _result(success=False),  # test -e échoue -> absent
            _result(success=False),  # test -L venvs
            _result(success=True),  # mkdir -p venvs
            _result(success=True, stdout="Python 3.11.9"),  # version
            _result(success=True),  # rm -rf version (recreate)
            _result(success=True),  # python3 -m venv version
            _result(success=True),  # pip install
            # activate() : readlink -> test -d -> test -e -> absent
            _result(success=False),
            _result(success=False),
            _result(success=False),
            _result(success=False, stderr="ln error"),  # ln -sfn échoue
            # _discard : readlink puis rm -rf
            _result(success=True, stdout=""),
            _result(success=True),  # rm -rf version (discard)
        ]
        installer = VenvInstaller(executor)
        releaser = VenvReleaser(executor, installer)
        verify = MagicMock(
            return_value=(CheckResult(label="import app", ok=True),)
        )

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is False
        assert outcome.phase_reached == DeployPhase.ACTIVATE
        last_call = executor.run.call_args_list[-1].args[0]
        assert last_call[:2] == ["rm", "-rf"]

    def test_migration_de_bout_en_bout_via_release(self) -> None:
        """release() avec venv_path répertoire réel (migration), pas
        seulement via activate() direct (F09 : branche non couverte)."""
        venv_path = Path("/opt/app/venv")
        new_version = Path("/opt/app/venvs/venv-20260929-164900-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False),  # readlink échoue
            _result(success=True),  # test -d réussit -> dir (migration)
            _result(success=False),  # test -L venvs
            _result(success=True),  # mkdir -p venvs
            _result(success=True, stdout="Python 3.11.9"),
            _result(success=True),  # rm -rf version (recreate)
            _result(success=True),  # python3 -m venv version
            _result(success=True),  # pip install
            _result(success=True),  # test -d version_path réussit (F18)
            # activate() : readlink échoue -> test -d réussit -> dir
            _result(success=False),
            _result(success=True),
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # migration (python -I -c)
            # _prune : readlink puis find
            _result(success=True, stdout=str(new_version) + "\n"),
            _result(success=True, stdout=f"{new_version.name}\n"),
        ]
        installer = VenvInstaller(executor)
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 49, 0, 0))
        releaser = VenvReleaser(executor, installer, clock=clock)
        verify = MagicMock(
            return_value=(CheckResult(label="import app", ok=True),)
        )

        outcome = releaser.release(venv_path, Path("/src"), verify)

        assert outcome.success is True
        assert outcome.phase_reached == DeployPhase.DONE
        assert outcome.active_version == new_version
        assert outcome.fallback_version is not None
        assert outcome.fallback_version.name.endswith("-legacy")


class TestVenvReleaserDiscardBranchesSupplementaires:
    """Tests pour _discard (branches manquantes, F09/T5)."""

    def test_id_etranger_ne_leve_pas_et_ne_fait_rien(self) -> None:
        """version.name ne matche pas le motif namespacé de
        venv_path.name : retour anticipé, aucune commande exécutée
        (F09 : branche non couverte)."""
        venv_path = Path("/opt/app/venv")
        version = Path("/opt/app/venvs/../etc/passwd")
        executor = _make_executor()
        releaser = VenvReleaser(executor, installer=MagicMock())

        releaser._discard(version, venv_path)  # noqa: SLF001

        executor.run.assert_not_called()

    def test_echec_rm_loggue_sans_logger_ne_leve_pas(self) -> None:
        """Échec du rm -rf pendant le discard : loggué (non bloquant),
        aucune exception, même sans logger configuré (F09 : branche
        non couverte)."""
        venv_path = Path("/opt/app/venv")
        version = Path("/opt/app/venvs/venv-20260929-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=False),  # readlink échoue, confirme (F15 : plus
            # de réponse test -e mockée ici, retirée par F10 — elle était
            # consommée à tort par le rm -rf réel ci-dessous, masquant
            # cette branche « rm échoue »)
            _result(success=False, stderr="rm error"),  # rm -rf échoue
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        releaser._discard(version, venv_path)  # noqa: SLF001

        last_call = executor.run.call_args_list[-1].args[0]
        assert last_call[:2] == ["rm", "-rf"]


class TestVenvReleaserPruneBranchesSupplementaires:
    """Tests pour _prune (branches manquantes, F09/T5)."""

    def test_echec_find_aucun_rm_tente(self) -> None:
        """Échec de la commande find : aucun rm n'est tenté, purge
        ignorée en best-effort (F09 : complète la couverture)."""
        venv_path = Path("/opt/app/venv")
        version = Path("/opt/app/venvs/venv-20260920-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(version) + "\n"),  # readlink
            _result(success=False, stderr="find error"),  # find échoue
        ]
        releaser = VenvReleaser(executor, installer=MagicMock())

        messages = releaser._prune(  # noqa: SLF001
            venv_path, version, None, keep_versions=2
        )

        assert messages == ()
        assert not any(
            call.args[0][0] == "rm" for call in executor.run.call_args_list
        )

    def test_purge_reussie_logue_les_versions_supprimees(self) -> None:
        """Purge avec au moins une version supprimée : un log
        informatif récapitule les ids purgés (F11 : traçabilité)."""
        venv_path = Path("/opt/app/venv")
        version = Path("/opt/app/venvs/venv-20260920-000000-000000")
        purged = Path("/opt/app/venvs/venv-20260901-000000-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(version) + "\n"),  # readlink
            _result(
                success=True,
                stdout=f"{purged.name}\n{version.name}\n",
            ),  # find
            _result(success=True),  # rm -rf purged
        ]
        logger = MagicMock()
        releaser = VenvReleaser(executor, installer=MagicMock(), logger=logger)

        releaser._prune(  # noqa: SLF001
            venv_path, version, None, keep_versions=1
        )

        logger.log_info.assert_called_once()
        assert purged.name in logger.log_info.call_args.args[0]

    def test_echec_rm_pendant_purge_best_effort(self) -> None:
        """Échec d'un rm -rf pendant la purge : loggué, non bloquant
        (best-effort) — release() reste un succès malgré cet échec.

        previous_id (old_version) est désormais protégé à vie (F01/F02) :
        avec keep_versions=1, il ne reste rien à purger si `find` ne
        connaît que previous et active. Une 3e version, ni active ni
        repli (purgeable_version), est donc listée par `find` pour que
        la purge ait effectivement une cible sur laquelle `rm` échoue.
        """
        venv_path = Path("/opt/app/venv")
        purgeable_version = Path("/opt/app/venvs/venv-20260810-000000-000000")
        old_version = Path("/opt/app/venvs/venv-20260901-000000-000000")
        new_version = Path("/opt/app/venvs/venv-20260929-164900-000000")
        executor = _make_executor()
        executor.run.side_effect = [
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=False),  # test -L venvs
            _result(success=True),  # mkdir -p venvs
            _result(success=True, stdout="Python 3.11.9"),
            _result(success=True),  # rm -rf version (recreate)
            _result(success=True),  # python3 -m venv version
            _result(success=True),  # pip install
            _result(success=True),  # test -d version_path réussit (F18)
            _result(success=True, stdout=str(old_version) + "\n"),
            _result(success=True),  # ln -sfn tmp
            _result(success=True),  # mv -T tmp -> venv_path
            _result(
                success=True, stdout=str(new_version) + "\n"
            ),  # readlink (_prune : confirme le lien basculé vers new_version)
            _result(
                success=True,
                stdout=(
                    f"{purgeable_version.name}\n"
                    f"{old_version.name}\n"
                    f"{new_version.name}\n"
                ),
            ),  # find
            _result(success=False, stderr="rm error"),  # rm -rf échoue
        ]
        installer = VenvInstaller(executor)
        clock = MagicMock(return_value=datetime(2026, 9, 29, 16, 49, 0, 0))
        releaser = VenvReleaser(executor, installer, clock=clock)
        verify = MagicMock(
            return_value=(CheckResult(label="import app", ok=True),)
        )

        outcome = releaser.release(
            venv_path, Path("/src"), verify, keep_versions=1
        )

        assert outcome.success is True
        last_call = executor.run.call_args_list[-1].args[0]
        assert last_call[:2] == ["rm", "-rf"]


class TestVenvReleaserPlannedSteps:
    """Tests pour VenvReleaser.planned_steps (T7, dry-run)."""

    def test_retourne_les_etapes_sans_commande(self) -> None:
        """planned_steps décrit les étapes réelles sans rien exécuter."""
        steps = VenvReleaser.planned_steps(
            Path("/opt/app/venv"), Path("/src/app"), keep_versions=3
        )
        assert any("construction" in s for s in steps)
        assert any("vérifications" in s for s in steps)
        assert any("migration" in s for s in steps)
        assert any("bascule atomique" in s for s in steps)
        assert any("conserve 3 versions" in s for s in steps)
