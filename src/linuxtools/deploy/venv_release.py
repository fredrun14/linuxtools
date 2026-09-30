"""Bascule atomique du venv déployé (mode opt-in `atomic_swap`).

Chaque déploiement construit une version neuve du venv sous
`<parent>/venvs/<name>-<horodatage>/`, la vérifie là, puis bascule le
lien symbolique `venv_path` vers elle par une opération atomique
(`ln -sfn` + `mv -T`, rename(2) même répertoire). Les versions
précédentes sont conservées en nombre limité (`keep_versions`) et
purgées en best-effort après bascule réussie.

Toutes les commandes passent par le CommandExecutor cible injecté
(local ou SSH) — ce module ne sait jamais s'il opère en local ou à
distance.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from linuxtools.deploy.exceptions import DeployError
from linuxtools.deploy.models import CheckResult, DeployPhase

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from linuxtools.commands.base import CommandExecutor
    from linuxtools.deploy.venv_installer import VenvInstaller
    from linuxtools.logging.base import Logger

    VerifyFn = Callable[[Path], tuple[CheckResult, ...]]

VenvState = Literal["link", "dir", "other", "absent"]

_VERSIONS_DIRNAME = "venvs"
_TS_FORMAT = "%Y%m%d-%H%M%S-%f"
_LEGACY_SUFFIX = "-legacy"

# Script de migration constant, exécuté en un seul processus distant
# (via <version>/bin/python -I -c) : deux rename(2) valent mieux que
# deux appels réseau (chaque run() via SshCommandExecutor = une
# connexion ssh, donc une fenêtre de 0,1 à 1 s). -I isole le script de
# l'environnement (site, PYTHONPATH). En cas d'échec du second rename,
# le répertoire d'origine est remis en place avant de sortir en erreur
# — jamais de venv_path absent après une migration ratée.
_MIGRATE_SCRIPT = (
    "import os, sys\n"
    "venv, legacy, tmp = sys.argv[1:4]\n"
    "os.rename(venv, legacy)\n"
    "try:\n"
    "    os.rename(tmp, venv)\n"
    "except OSError:\n"
    "    os.rename(legacy, venv)\n"
    "    raise\n"
)


def _new_version_id(name: str, now: datetime) -> str:
    """Construit l'identifiant horodaté d'une nouvelle version.

    Args:
        name: Nom de l'outil (dernier composant de venv_path).
        now: Horodatage à utiliser (horloge injectable pour les
            tests déterministes — cf. VenvReleaser.__init__).

    Returns:
        Identifiant `<name>-<YYYYmmdd-HHMMSS-ffffff>`.
    """
    return f"{name}-{now.strftime(_TS_FORMAT)}"


def _version_id_pattern(name: str) -> re.Pattern[str]:
    """Construit le motif namespacé des ids de version d'un outil.

    Args:
        name: Nom de l'outil (dernier composant de venv_path).

    Returns:
        Motif compilé reconnaissant `<name>-YYYYMMDD-HHMMSS-ffffff`,
        avec suffixe `-legacy` optionnel. `re.escape(name)` empêche
        qu'un nom voisin ("app" / "app2") ne se recouvrent.
    """
    return re.compile(
        rf"^{re.escape(name)}-\d{{8}}-\d{{6}}-\d{{6}}(-legacy)?$"
    )


def _version_sort_key(version_id: str) -> str:
    """Clé de tri chronologique d'un id de version.

    Le suffixe `-legacy` n'influe pas sur l'ordre : seul l'horodatage
    compte (retiré du suffixe avant comparaison).

    Args:
        version_id: Identifiant `<name>-<ts>[-legacy]`.

    Returns:
        L'identifiant sans son éventuel suffixe `-legacy`.
    """
    return version_id.removesuffix(_LEGACY_SUFFIX)


def select_versions_to_prune(
    version_ids: Sequence[str],
    name: str,
    active_id: str,
    previous_id: str | None,
    keep: int,
) -> tuple[str, ...]:
    """Retourne les ids de version à purger, du plus ancien au plus récent.

    Politique de rétention pure (conception §6/§7) : `active_id`
    n'est jamais purgé, ni aucun id postérieur (déploiement
    concurrent). Les ids étrangers au motif namespacé de `name`
    sont ignorés (protection d'un outil voisin partageant le même
    parent). `previous_id` est toujours protégé, quelle que soit sa
    position chronologique et quel que soit `keep` (avenant CDC
    Q-05, F02/F01).

    Args:
        version_ids: Ids trouvés sous le répertoire des versions.
        name: Nom de l'outil (dernier composant de venv_path), reçu
            explicitement plutôt que dérivé d'`active_id` (F07) — un
            `active_id` suffixé `-legacy` tronquerait le nom déduit
            par `rsplit`.
        active_id: Id de la version actuellement active.
        previous_id: Id de la version de repli, ou None. Toujours
            protégé, quelle que soit sa position chronologique et
            quel que soit `keep` (avenant CDC Q-05, F02/F01).
        keep: Nombre de versions à conserver, active incluse (≥ 1).

    Returns:
        Ids à purger, triés du plus ancien au plus récent.
    """
    pattern = _version_id_pattern(name)
    known = [vid for vid in version_ids if pattern.fullmatch(vid)]
    sorted_ids = sorted(known, key=_version_sort_key)

    active_key = _version_sort_key(active_id)
    older = [vid for vid in sorted_ids if _version_sort_key(vid) < active_key]

    keep_older = max(keep - 1, 0)
    protected = {previous_id} if previous_id is not None else set()
    # previous_id occupe toujours un emplacement protégé — la fenêtre
    # des plus récentes ne porte que sur le budget restant, pour ne
    # jamais garder previous_id ET la fenêtre en plus (F01/F02 :
    # previous_id doit être protégé sans faire gonfler `keep`).
    remaining_budget = max(keep_older - len(protected & set(older)), 0)
    pool = [vid for vid in older if vid not in protected]
    window = set(pool[-remaining_budget:]) if remaining_budget else set()
    to_keep = protected | window
    to_prune = [vid for vid in older if vid not in to_keep]
    return tuple(to_prune)


def _legacy_ts_before(venv_name: str, version_id: str) -> str:
    """Dérive l'horodatage du legacy à partir de celui de version_id.

    Le legacy doit toujours trier immédiatement avant la version en
    cours d'activation (F01) : recalculer l'horodatage depuis une
    nouvelle lecture d'horloge introduit une course (l'horloge peut
    avoir avancé entre les deux appels). On dérive donc l'horodatage
    du legacy de celui, déjà connu, de version_id, moins un delta
    minimal — le tri est alors correct par construction.

    Args:
        venv_name: Nom de l'outil (dernier composant de venv_path).
        version_id: Id de la version en cours d'activation.

    Returns:
        Horodatage formaté `_TS_FORMAT`, antérieur à celui de version_id.
    """
    ts_part = version_id[len(venv_name) + 1 :]
    version_ts = datetime.strptime(ts_part, _TS_FORMAT)
    return (version_ts - timedelta(microseconds=1)).strftime(_TS_FORMAT)


def _managed_version_path(venv_path: Path, raw_id: str) -> Path:
    """Reconstruit le chemin d'une version gérée depuis son id.

    Ne fait jamais confiance à un chemin brut issu d'une sortie de
    commande (ex. `find`) : le chemin final est toujours recomposé en
    Python à partir de `_versions_dir` et de l'id validé.

    Args:
        venv_path: Chemin du venv cible (lien symbolique actif).
        raw_id: Identifiant de version à valider et reconstruire.

    Returns:
        `<versions_dir>/<raw_id>`.

    Raises:
        DeployError: Si raw_id ne matche pas le motif namespacé du
            nom de venv_path.
    """
    pattern = _version_id_pattern(venv_path.name)
    if not pattern.fullmatch(raw_id):
        raise DeployError(
            f"Identifiant de version non conforme, refusé : {raw_id}"
        )
    return _versions_dir(venv_path) / raw_id


def _ensure_managed_link_target(
    venv_path: Path, expected_dir: Path, target: Path
) -> None:
    """Vérifie que target est une cible de lien gérée sous expected_dir.

    Args:
        venv_path: Chemin du venv cible (pour le message d'erreur).
        expected_dir: Répertoire des versions attendu.
        target: Cible actuelle du lien venv_path.

    Raises:
        DeployError: Si target ne matche pas le motif namespacé de
            venv_path.name ou n'est pas sous expected_dir.
    """
    if (
        not _version_id_pattern(venv_path.name).fullmatch(target.name)
        or target.parent != expected_dir
    ):
        raise DeployError(f"venv_path pointe vers un lien non géré : {target}")


def _versions_dir(venv_path: Path) -> Path:
    """Retourne le répertoire des versions, frère de venv_path.

    Args:
        venv_path: Chemin du venv cible (lien symbolique actif).

    Returns:
        `<venv_path.parent>/venvs` (Q-02 du CDC).
    """
    return venv_path.parent / _VERSIONS_DIRNAME


def _validate_venv_path(venv_path: Path) -> None:
    """Valide un venv_path avant toute commande sur l'hôte.

    Contrôle de sécurité obligatoire (conception §6) : un `rm -rf`
    construit depuis un chemin non fiable ne doit jamais viser autre
    chose qu'un sous-répertoire du répertoire des versions.

    Args:
        venv_path: Chemin du venv cible à valider.

    Raises:
        DeployError: Si venv_path n'est pas absolu, contient un
            composant `.`/`..`/`//` (non normalisé), a pour parent la
            racine, ou a un nom vide.
    """
    if not venv_path.is_absolute():
        raise DeployError(f"venv_path doit être absolu : {venv_path}")
    if os.path.normpath(str(venv_path)) != str(venv_path):
        raise DeployError(f"venv_path doit être normalisé : {venv_path}")
    if venv_path.parent == Path("/"):
        raise DeployError(
            f"venv_path ne peut pas être directement sous la racine : "
            f"{venv_path}"
        )


@dataclass(frozen=True)
class ReleaseOutcome:
    """Compte rendu d'un appel à VenvReleaser.release().

    release() ne lève jamais : tout passe par cette structure, pour
    que Deployer construise un DeployReport sans avoir à intercepter
    des exceptions métier venues d'un module différent.

    Attributes:
        success: True si la version a été construite, vérifiée et
            basculée avec succès.
        phase_reached: Dernière phase atteinte (INSTALL, VERIFY,
            ACTIVATE ou DONE).
        checks: Résultats des vérifications post-install, si la
            phase VERIFY a été atteinte.
        active_version: Chemin de la version basculée, si succès.
        fallback_version: Chemin de la version de repli précédente,
            si succès.
        messages: Messages explicatifs (échec, purge non bloquante).
    """

    success: bool
    phase_reached: DeployPhase
    checks: tuple[CheckResult, ...] = ()
    active_version: Path | None = None
    fallback_version: Path | None = None
    messages: tuple[str, ...] = ()


class VenvReleaser:
    """Gère le cycle de vie versionné d'un venv basculé par lien.

    Construit une version neuve, la vérifie, bascule le lien
    `venv_path` vers elle, puis purge les versions excédentaires.
    Toutes les commandes passent par le CommandExecutor cible injecté
    (local ou SSH) — VenvReleaser ne sait jamais s'il opère en local
    ou à distance.

    Attributes:
        _executor: Exécuteur ciblant l'hôte (local ou
            SshCommandExecutor).
        _installer: VenvInstaller réel, réutilisé pour construire
            chaque version (aucun code de build dupliqué).
        _logger: Logger optionnel.
        _clock: Horloge injectable (tests déterministes).
    """

    def __init__(
        self,
        executor: CommandExecutor,
        installer: VenvInstaller,
        logger: Logger | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialise le releaser avec ses collaborateurs.

        Args:
            executor: Exécuteur de commandes ciblant l'hôte.
            installer: VenvInstaller réel, utilisé pour install().
            logger: Logger optionnel.
            clock: Horloge injectable, pour des ids de version
                déterministes en test. Par défaut en UTC (F08) : une
                horloge locale n'est pas monotone au changement
                d'heure été/hiver, ce qui casserait le tri
                chronologique des ids de version.
        """
        self._executor = executor
        self._installer = installer
        self._logger = logger
        self._clock = clock

    def _log(self, message: str) -> None:
        """Envoie un message d'information au logger si disponible."""
        if self._logger:
            self._logger.log_info(message)

    def _log_error(self, message: str) -> None:
        """Envoie un message d'erreur au logger si disponible."""
        if self._logger:
            self._logger.log_error(message)

    def _current_state(self, venv_path: Path) -> tuple[VenvState, Path | None]:
        """Détermine l'état actuel de venv_path sur l'hôte.

        Args:
            venv_path: Chemin du venv cible.

        Returns:
            ("link", cible) si venv_path est un lien symbolique ;
            ("dir", None) si c'est un répertoire réel (migration) ;
            ("other", None) si c'est autre chose (fichier...) ;
            ("absent", None) si rien n'existe à ce chemin.

        Raises:
            DeployError: Si readlink échoue avec un code différent de
                1 (état indéterminé, ex. coupure ssh transitoire —
                F16).
        """
        readlink = self._executor.run(["readlink", "--", str(venv_path)])
        if readlink.success:
            return "link", Path(readlink.stdout.strip())
        if readlink.return_code != 1:
            # readlink a échoué avec un code différent de 1 (ex. 255 :
            # échec de transport ssh) : la commande n'a pas pu confirmer
            # que venv_path n'est pas un lien. test -d/test -e suivent les
            # liens symboliques et classeraient à tort un lien géré en
            # "dir"/"other" — refuser plutôt que deviner (F16, avenant
            # CONCEPTION §61).
            raise DeployError(
                f"état de {venv_path} indéterminé : readlink a échoué avec "
                f"le code {readlink.return_code}"
            )
        if self._executor.run(["test", "-d", str(venv_path)]).success:
            return "dir", None
        if self._executor.run(["test", "-e", str(venv_path)]).success:
            return "other", None
        return "absent", None

    def activate(self, venv_path: Path, version_path: Path) -> Path | None:
        """Bascule atomiquement venv_path vers version_path.

        Sert aussi de primitive de rollback : rappeler activate()
        avec la version de repli rebascule le lien sans copie.

        Le venv legacy issu d'une migration ne peut être vérifié
        qu'une fois le lien rebasculé sur lui (ses shebangs visent
        `venv_path/bin/python`, jamais son propre chemin réel).

        Note :
            Un processus déjà en cours d'exécution depuis l'ancien
            `venv_path` (devenu le legacy après migration) continue de
            tourner avec les fichiers de ce legacy : ses imports différés
            (import effectué après la bascule) résolvent alors vers la
            nouvelle version, pas vers le code avec lequel le processus a
            démarré. C'est un compromis assumé (CDC : "les timers ne sont
            jamais arrêtés ni relancés") — à documenter pour l'appelant, pas
            un bug de `activate()`.

        Args:
            venv_path: Chemin du venv cible (lien symbolique actif).
            version_path: Chemin de la version à activer.

        Returns:
            Chemin de l'ancienne cible du lien (None si venv_path
            était absent avant la bascule ; le répertoire migré en
            cas de migration).

        Raises:
            DeployError: Si venv_path est invalide, si version_path
                n'est pas une version gérée sous `venvs/`, si
                venv_path est un fichier/lien non géré, ou si une
                étape de la bascule échoue sur l'hôte.
        """
        _validate_venv_path(venv_path)
        expected_dir = _versions_dir(venv_path)
        if version_path.parent != expected_dir or not _version_id_pattern(
            venv_path.name
        ).fullmatch(version_path.name):
            raise DeployError(
                f"version_path n'est pas une version gérée : {version_path}"
            )
        if not self._executor.run(["test", "-d", str(version_path)]).success:
            raise DeployError(
                f"version_path n'existe pas sur l'hôte : {version_path} "
                "(F18 : refus avant de basculer le lien actif vers une "
                "cible absente)"
            )

        state, target = self._current_state(venv_path)
        if state == "other":
            raise DeployError(
                "venv_path existe mais n'est ni un lien ni un répertoire"
                f" : {venv_path}"
            )
        if state == "link":
            if target is None:
                raise DeployError(
                    f"état incohérent : lien détecté sans cible pour "
                    f"{venv_path}"
                )
            _ensure_managed_link_target(venv_path, expected_dir, target)
        elif state == "dir" and version_path.name.endswith(_LEGACY_SUFFIX):
            raise DeployError(
                f"activate() refuse une version déjà marquée legacy "
                f"({version_path.name}) alors que {venv_path} est encore "
                "un répertoire réel : la migration n'a pas encore eu lieu, "
                "il n'y a pas de version antérieure à re-horodater"
            )

        tmp = venv_path.parent / f".{venv_path.name}.swap-{uuid4().hex[:8]}"
        ln_result = self._executor.run(
            ["ln", "-sfn", "--", str(version_path), str(tmp)]
        )
        if not ln_result.success:
            raise DeployError(
                f"Échec de création du lien temporaire {tmp} : "
                f"{ln_result.stderr}"
            )

        if state == "dir":
            legacy_ts = _legacy_ts_before(venv_path.name, version_path.name)
            legacy = (
                expected_dir / f"{venv_path.name}-{legacy_ts}{_LEGACY_SUFFIX}"
            )
            python_bin = str(version_path / "bin" / "python")
            migrate_result = self._executor.run(
                [
                    python_bin,
                    "-I",
                    "-c",
                    _MIGRATE_SCRIPT,
                    str(venv_path),
                    str(legacy),
                    str(tmp),
                ]
            )
            if not migrate_result.success:
                self._executor.run(["rm", "-f", "--", str(tmp)])
                raise DeployError(
                    "Échec de la migration de venv_path (répertoire "
                    f"d'origine remis en place) : {migrate_result.stderr}"
                )
            self._log(
                f"bascule répertoire migré {venv_path} → {version_path} "
                f"(ancien conservé sous {legacy})"
            )
            return legacy

        mv_result = self._executor.run(
            ["mv", "-T", "--", str(tmp), str(venv_path)]
        )
        if not mv_result.success:
            self._executor.run(["rm", "-f", "--", str(tmp)])
            raise DeployError(
                f"Échec de la bascule de {venv_path} : {mv_result.stderr}"
            )

        old_target = target if state == "link" else None
        self._log(f"bascule {old_target or 'absent'} → {version_path}")
        return old_target

    def _discard(self, version: Path, venv_path: Path) -> None:
        """Supprime une version ratée, avec garde-fou (best-effort).

        Args:
            version: Version à supprimer (construite ou en cours
                d'activation, jamais encore la cible du lien).
            venv_path: Chemin du venv cible.

        Note:
            Le garde-fou suppose que l'exécuteur renvoie le code de
            retour réel du processus (F10) : -1 sur un timeout ou une
            OSError locale, 255 sur un échec de transport ssh (avant
            même l'exécution de la commande distante). Seul
            return_code == 1 est traité comme une confirmation.
        """
        try:
            managed = _managed_version_path(venv_path, version.name)
        except DeployError:
            return
        readlink = self._executor.run(["readlink", "--", str(venv_path)])
        if readlink.success:
            if Path(readlink.stdout.strip()) == managed:
                return  # Jamais supprimer la cible actuelle du lien.
        elif readlink.return_code != 1:
            # readlink a échoué avec un code différent de 1 (ex. 255 :
            # échec de transport ssh) : la commande n'a pas pu confirmer
            # l'état réel de venv_path. return_code == 1 signifie que
            # readlink s'est bien exécuté et a confirmé que venv_path
            # n'est pas/plus un lien — seul ce cas autorise la suite
            # (F10 : test -e suit les liens, il ne distingue pas un lien
            # géré d'un répertoire réel, il a été retiré).
            self._log_error(
                f"Suppression de {managed} annulée : état de {venv_path} "
                f"indéterminé (readlink a échoué avec le code "
                f"{readlink.return_code}, non bloquant)."
            )
            return
        result = self._executor.run(["rm", "-rf", "--", str(managed)])
        if not result.success:
            self._log_error(
                f"Échec de suppression de la version ratée {managed} "
                f"(non bloquant) : {result.stderr}"
            )
        else:
            self._log(f"version ratée supprimée : {managed}")

    def _prune(
        self,
        venv_path: Path,
        version: Path,
        previous: Path | None,
        keep_versions: int,
    ) -> tuple[str, ...]:
        """Purge best-effort des versions excédentaires après bascule.

        Args:
            venv_path: Chemin du venv cible.
            version: Version nouvellement basculée (active).
            previous: Version de repli précédente, ou None.
            keep_versions: Nombre de versions à conserver.

        Returns:
            Messages informatifs (purge ignorée, ou vide si rien à
            signaler — les échecs individuels sont loggués, non
            bloquants, et n'apparaissent pas ici).
        """
        readlink = self._executor.run(["readlink", "--", str(venv_path)])
        if not readlink.success or Path(readlink.stdout.strip()) != version:
            return (
                "Purge ignorée : le lien a changé depuis la bascule "
                "(déploiement concurrent).",
            )

        versions_dir = _versions_dir(venv_path)
        find_result = self._executor.run(
            [
                "find",
                str(versions_dir),
                "-mindepth",
                "1",
                "-maxdepth",
                "1",
                "-type",
                "d",
                "-printf",
                "%f\n",
            ]
        )
        if not find_result.success:
            self._log_error(
                "Échec de listage des versions pour la purge "
                f"(non bloquant) : {find_result.stderr}"
            )
            return ()

        ids = [line for line in find_result.stdout.splitlines() if line]
        previous_id = previous.name if previous is not None else None
        to_prune = select_versions_to_prune(
            ids, venv_path.name, version.name, previous_id, keep_versions
        )
        for version_id in to_prune:
            try:
                path = _managed_version_path(venv_path, version_id)
            except DeployError:
                continue
            result = self._executor.run(["rm", "-rf", "--", str(path)])
            if not result.success:
                self._log_error(
                    f"Échec de purge de {path} (non bloquant) : "
                    f"{result.stderr}"
                )
        if to_prune:
            self._log(
                f"purge : {len(to_prune)} version(s) supprimée(s) : "
                f"{', '.join(to_prune)}"
            )
        return ()

    def release(
        self,
        venv_path: Path,
        source_dir: Path,
        verify: VerifyFn,
        keep_versions: int = 2,
    ) -> ReleaseOutcome:
        """Construit, vérifie et bascule une nouvelle version du venv.

        Ne lève jamais : tout échec est reporté via ReleaseOutcome
        (cf. sa docstring). Le venv actif n'est touché que si le
        résultat est un succès, ou si phase_reached == ACTIVATE avec
        succès False (le lien reste alors inchangé dans ce dernier
        cas).

        Args:
            venv_path: Chemin du venv cible (lien symbolique actif).
            source_dir: Répertoire source à installer.
            verify: Fonction de vérification post-install, reçoit le
                chemin de la version à tester.
            keep_versions: Nombre de versions à conserver après
                bascule réussie (défaut 2).

        Returns:
            Compte rendu complet de la tentative de release.
        """
        try:
            _validate_venv_path(venv_path)
        except DeployError as exc:
            return ReleaseOutcome(
                success=False,
                phase_reached=DeployPhase.INSTALL,
                messages=(str(exc),),
            )

        expected_dir = _versions_dir(venv_path)
        try:
            state, target = self._current_state(venv_path)
        except DeployError as exc:
            return ReleaseOutcome(
                success=False,
                phase_reached=DeployPhase.INSTALL,
                messages=(str(exc),),
            )
        if state == "other":
            return ReleaseOutcome(
                success=False,
                phase_reached=DeployPhase.INSTALL,
                messages=(
                    "venv_path existe mais n'est ni un lien ni un "
                    "répertoire — refus avant build.",
                ),
            )
        if state == "link":
            if target is None:
                # Ne devrait jamais se produire : _current_state garantit
                # target is not None quand state == "link" — invariant
                # vérifié explicitement plutôt que par un assert, qui
                # disparaît sous python -O (F06).
                return ReleaseOutcome(
                    success=False,
                    phase_reached=DeployPhase.INSTALL,
                    messages=(
                        f"état incohérent : lien détecté sans cible pour "
                        f"{venv_path} — refus avant build.",
                    ),
                )
            try:
                _ensure_managed_link_target(venv_path, expected_dir, target)
            except DeployError as exc:
                return ReleaseOutcome(
                    success=False,
                    phase_reached=DeployPhase.INSTALL,
                    messages=(f"{exc} — refus avant build.",),
                )

        if self._executor.run(["test", "-L", str(expected_dir)]).success:
            return ReleaseOutcome(
                success=False,
                phase_reached=DeployPhase.INSTALL,
                messages=(f"{expected_dir} est un lien : refus avant build.",),
            )

        mkdir_result = self._executor.run(
            ["mkdir", "-p", "--", str(expected_dir)]
        )
        if not mkdir_result.success:
            return ReleaseOutcome(
                success=False,
                phase_reached=DeployPhase.INSTALL,
                messages=(
                    f"Échec de création de {expected_dir} : "
                    f"{mkdir_result.stderr}",
                ),
            )

        version_id = _new_version_id(venv_path.name, self._clock())
        version = expected_dir / version_id

        install_result = self._installer.install(
            version, source_dir, recreate=True
        )
        if not install_result.success:
            self._discard(version, venv_path)
            return ReleaseOutcome(
                success=False,
                phase_reached=DeployPhase.INSTALL,
                messages=(f"Installation échouée : {install_result.stderr}",),
            )

        checks = tuple(verify(version))
        if not all(check.ok for check in checks):
            self._discard(version, venv_path)
            return ReleaseOutcome(
                success=False,
                phase_reached=DeployPhase.VERIFY,
                checks=checks,
                messages=("Vérification post-install échouée.",),
            )

        try:
            previous = self.activate(venv_path, version)
        except DeployError as exc:
            self._discard(version, venv_path)
            return ReleaseOutcome(
                success=False,
                phase_reached=DeployPhase.ACTIVATE,
                checks=checks,
                messages=(str(exc),),
            )

        prune_messages = self._prune(
            venv_path, version, previous, keep_versions
        )

        return ReleaseOutcome(
            success=True,
            phase_reached=DeployPhase.DONE,
            checks=checks,
            active_version=version,
            fallback_version=previous,
            messages=prune_messages,
        )

    @staticmethod
    def planned_steps(
        venv_path: Path, source_dir: Path, keep_versions: int
    ) -> tuple[str, ...]:
        """Liste les étapes d'un release() pour le dry-run.

        Args:
            venv_path: Chemin du venv cible.
            source_dir: Répertoire source à installer.
            keep_versions: Nombre de versions conservées après purge.

        Returns:
            Libellés lisibles des étapes réelles (aucune commande
            n'est exécutée par cette méthode).
        """
        versions_dir = _versions_dir(venv_path)
        return (
            f"construction {versions_dir}/{venv_path.name}-<horodatage> "
            f"depuis {source_dir}",
            "pip install --force-reinstall <source> dans la version",
            "vérifications post-install sur la version (chemins redirigés)",
            f"si {venv_path} est un répertoire réel : migration vers "
            f"{versions_dir}/{venv_path.name}-<horodatage>-legacy",
            f"bascule atomique {venv_path} -> version",
            f"purge (conserve {keep_versions} versions)",
        )
