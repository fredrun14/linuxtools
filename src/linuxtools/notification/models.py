"""Modèles de données pour les notifications et comptes rendus.

Ce module fournit :
    - Urgency : niveau d'urgence d'une notification.
    - Notification : message immuable prêt à être envoyé.
    - StepResult : résultat d'une étape d'exécution.
    - ExecutionReport : compte rendu d'exécution d'un script,
      convertible en Notification en fin de traitement.

Typical usage example:

    report = ExecutionReport(script_name="backup-nas")
    with report.step("rsync documents"):
        ...  # étape chronométrée automatiquement
    report.finish()
    notification = report.to_notification()
"""

import socket
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Urgency(Enum):
    """Niveau d'urgence d'une notification.

    Les valeurs correspondent aux niveaux acceptés par
    ``notify-send -u`` ; chaque notifier concret les traduit
    dans son propre référentiel (priorité Gotify, PRIORITY
    journald, etc.).
    """

    LOW = "low"
    NORMAL = "normal"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Notification:
    """Notification immuable prête à être envoyée.

    Attributes:
        title: Titre court (une seule ligne, non vide).
        message: Corps du message (multiligne autorisé, non vide).
        urgency: Niveau d'urgence.
        icon: Nom d'icône freedesktop (utilisé par le canal desktop).
    """

    title: str
    message: str
    urgency: Urgency = Urgency.NORMAL
    icon: str = ""

    def __post_init__(self) -> None:
        """Valide le titre et le message.

        Raises:
            ValueError: Si le titre ou le message est vide, ou si
                le titre contient un saut de ligne.
        """
        if not self.title:
            raise ValueError("title est requis")
        if not self.message:
            raise ValueError("message est requis")
        if "\n" in self.title:
            raise ValueError("title ne doit pas contenir de saut de ligne")


@dataclass
class StepResult:
    """Résultat d'une étape d'exécution d'un script.

    Attributes:
        name: Nom lisible de l'étape (ex: 'rsync documents').
        success: True si l'étape s'est terminée sans erreur.
        duration: Durée de l'étape en secondes.
        message: Détail optionnel (message d'erreur, volumétrie…).
    """

    name: str
    success: bool
    duration: float = 0.0
    message: str = ""


@dataclass
class ExecutionReport:
    """Compte rendu d'exécution d'un script.

    Accumule les résultats d'étapes et les erreurs pendant
    l'exécution, puis produit un résumé textuel et une
    Notification en fin de traitement.

    Attributes:
        script_name: Nom du script (ex: 'backup-nas').
        hostname: Nom de la machine (détecté par défaut).
        started_at: Horodatage de début (défaut : maintenant).
        finished_at: Horodatage de fin (renseigné par finish()).
        steps: Résultats des étapes dans l'ordre d'exécution.
        errors: Erreurs globales hors étapes.

    Example:
        >>> report = ExecutionReport(script_name="demo")
        >>> report.add_step("étape 1", success=True)
        >>> report.finish()
        >>> report.success
        True
    """

    script_name: str
    hostname: str = field(default_factory=socket.gethostname)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    steps: list[StepResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Valide le nom du script.

        Raises:
            ValueError: Si script_name est vide.
        """
        if not self.script_name:
            raise ValueError("script_name est requis")

    @property
    def success(self) -> bool:
        """Retourne True si toutes les étapes ont réussi sans erreur."""
        steps_ok = all(step.success for step in self.steps)
        return steps_ok and not self.errors

    @property
    def duration(self) -> float:
        """Retourne la durée totale en secondes (0.0 si non terminé)."""
        if self.finished_at is None:
            return 0.0
        delta = self.finished_at - self.started_at
        return delta.total_seconds()

    def add_step(
        self,
        name: str,
        success: bool,
        duration: float = 0.0,
        message: str = "",
    ) -> None:
        """Enregistre le résultat d'une étape.

        Args:
            name: Nom lisible de l'étape.
            success: True si l'étape a réussi.
            duration: Durée en secondes.
            message: Détail optionnel.
        """
        self.steps.append(
            StepResult(
                name=name,
                success=success,
                duration=duration,
                message=message,
            )
        )

    def add_error(self, message: str) -> None:
        """Enregistre une erreur globale hors étape.

        Args:
            message: Description de l'erreur.
        """
        self.errors.append(message)

    @contextmanager
    def step(self, name: str, reraise: bool = False) -> Iterator[None]:
        """Chronomètre une étape et enregistre son résultat.

        Toute exception levée dans le bloc marque l'étape en échec
        et son message est conservé dans le résultat.

        Args:
            name: Nom lisible de l'étape.
            reraise: Si True, relaie l'exception après enregistrement.
                Si False (défaut), l'exception est absorbée afin de
                laisser les étapes suivantes s'exécuter.

        Yields:
            None.
        """
        start = time.monotonic()
        try:
            yield
        except Exception as exc:
            self.add_step(
                name=name,
                success=False,
                duration=time.monotonic() - start,
                message=str(exc),
            )
            if reraise:
                raise
        else:
            self.add_step(
                name=name,
                success=True,
                duration=time.monotonic() - start,
            )

    def finish(self) -> None:
        """Clôture le rapport en renseignant finished_at."""
        self.finished_at = datetime.now()

    def format_summary(self) -> str:
        """Retourne un résumé textuel lisible du rapport.

        Returns:
            Chaîne multiligne : statut global, machine, durée,
            détail des étapes et erreurs éventuelles.
        """
        status = "✓ Succès" if self.success else "✗ Échec"
        lines = [
            f"{status} — {self.script_name} sur {self.hostname}",
            f"  Début : {self.started_at:%Y-%m-%d %H:%M:%S}",
        ]
        if self.finished_at is not None:
            lines.append(f"  Durée : {self.duration:.1f}s")
        for step in self.steps:
            mark = "✓" if step.success else "✗"
            line = f"    {mark} {step.name} ({step.duration:.1f}s)"
            if step.message:
                line += f" — {step.message}"
            lines.append(line)
        for error in self.errors:
            lines.append(f"    ! {error}")
        return "\n".join(lines)

    def to_notification(
        self,
        icon_success: str = "emblem-default",
        icon_failure: str = "dialog-error",
    ) -> Notification:
        """Convertit le rapport en Notification prête à l'envoi.

        L'urgence est NORMAL en cas de succès, CRITICAL en cas
        d'échec.

        Args:
            icon_success: Icône utilisée en cas de succès.
            icon_failure: Icône utilisée en cas d'échec.

        Returns:
            Notification construite depuis le résumé du rapport.
        """
        if self.success:
            title = f"✓ {self.script_name} — succès"
            icon = icon_success
            urgency = Urgency.NORMAL
        else:
            title = f"✗ {self.script_name} — échec"
            icon = icon_failure
            urgency = Urgency.CRITICAL
        return Notification(
            title=title,
            message=self.format_summary(),
            urgency=urgency,
            icon=icon,
        )
