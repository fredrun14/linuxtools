"""Export et restauration génériques d'unités systemd via TOML.

Fournit SystemdUnitExporter et SystemdUnitRestorer pour porter des
configurations systemd entre machines sans perte de champs INI.

Typical usage example:

    from linuxtools.systemd.unit_porter import (
        SystemdUnitExporter,
        SystemdUnitRestorer,
    )

    exporter = SystemdUnitExporter(logger=logger)
    toml_str = exporter.export(
        Path("/etc/systemd/system/mon.service"),
        enabled=True,
    )
    Path("mon-service.toml").write_text(toml_str)

    restorer = SystemdUnitRestorer(executor=executor, logger=logger)
    ok, unit_name = restorer.restore(
        Path("mon-service.toml"),
        Path("/etc/systemd/system"),
    )
"""

# stdlib
import shutil
import subprocess  # nosec B404
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

# local
from linuxtools.filesystem.linux import write_text_secure
from linuxtools.logging.base import Logger
from linuxtools.logging.console_logger import ConsoleLogger
from linuxtools.systemd.validators import (
    reject_control_chars,
    validate_full_unit_name,
)

if TYPE_CHECKING:
    from linuxtools.systemd.executor import SystemdExecutor

_SUPPORTED_UNIT_TYPES = frozenset({"service", "timer", "mount"})


def _toml_escape(value: str) -> str:
    """Échappe une valeur pour l'insérer dans une string TOML basique."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


class SystemdUnitExporter:
    """Exporte un fichier unit systemd vers un TOML générique.

    Préserve toutes les sections INI verbatim ([Unit], [Service]/
    [Timer]/[Mount], [Install]) sans perte de champs. Les valeurs
    multi-occurrences deviennent des tableaux TOML. Une section
    [meta] stocke unit_type, enabled et requires_exec pour permettre
    la restauration fidèle par SystemdUnitRestorer.

    Attributes:
        _logger: Logger injecté.

    Example:
        >>> exporter = SystemdUnitExporter(logger=logger)
        >>> toml_str = exporter.export(
        ...     Path("/etc/systemd/system/mon.service"),
        ...     enabled=True,
        ... )
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise l'exporteur.

        Args:
            logger: Logger injecté. Défaut : ConsoleLogger.
        """
        self._logger = logger or ConsoleLogger()

    def export(
        self,
        unit_path: Path,
        enabled: bool = False,
        requires_exec: str = "",
    ) -> str | None:
        """Parse un fichier unit et retourne son contenu TOML générique.

        Args:
            unit_path: Chemin absolu vers le fichier unit.
            enabled: True si l'unit est activée sur la machine source.
            requires_exec: Chemin du binaire externe requis pour ce service
                (vide = aucun prérequis vérifié à la restauration).

        Returns:
            Contenu TOML ou None si le type d'unit n'est pas supporté
            ou si le fichier est illisible.
        """
        try:
            data = self.parse_ini(unit_path)
        except OSError as exc:
            self._logger.log_error(
                f"Impossible de lire {unit_path.name} : {exc}"
            )
            return None
        suffix = unit_path.suffix
        if suffix not in {f".{t}" for t in _SUPPORTED_UNIT_TYPES}:
            self._logger.log_error(
                f"{unit_path.name} — type non supporté : {suffix!r}"
            )
            return None
        unit_type = suffix[1:]
        return self.to_toml(data, unit_type, enabled, requires_exec)

    @staticmethod
    def parse_ini(
        path: Path,
    ) -> dict[str, dict[str, list[str]]]:
        """Parse un fichier unit systemd (format INI) en dict.

        Chaque valeur est une liste pour supporter les clés dupliquées
        (ex : plusieurs lignes Environment=).

        Args:
            path: Chemin vers le fichier unit.

        Returns:
            Dict section → dict clé → list[valeur].

        Raises:
            OSError: Si le fichier est illisible.
        """
        result: dict[str, dict[str, list[str]]] = {}
        current_section = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("#")
                or stripped.startswith(";")
            ):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1]
                result.setdefault(current_section, {})
                continue
            if "=" in stripped and current_section:
                key, _, value = stripped.partition("=")
                result[current_section].setdefault(
                    key.strip(), []
                ).append(value.strip())
        return result

    @staticmethod
    def to_toml(
        data: dict[str, dict[str, list[str]]],
        unit_type: str,
        enabled: bool = False,
        requires_exec: str = "",
    ) -> str:
        """Sérialise un dict INI parsé en TOML générique.

        Génère une section [meta] puis reproduit chaque section INI
        verbatim. Les valeurs à occurrence unique deviennent des strings
        TOML ; les valeurs multi-occurrences deviennent des tableaux.

        Args:
            data: Dict section → dict clé → list[valeur],
                issu de parse_ini.
            unit_type: Type d'unit ("service", "timer", "mount").
            enabled: True si l'unit est activée sur la machine source.
            requires_exec: Chemin du binaire externe requis.

        Returns:
            Contenu TOML avec [meta] puis les sections INI verbatim.
        """
        lines = [
            "[meta]",
            f'unit_type = "{unit_type}"',
            f"enabled = {str(enabled).lower()}",
            f'requires_exec = "{_toml_escape(requires_exec)}"',
            "",
        ]
        for section, keys in data.items():
            lines.append(f"[{section}]")
            for key, values in keys.items():
                if len(values) == 1:
                    lines.append(
                        f'{key} = "{_toml_escape(values[0])}"'
                    )
                else:
                    items_str = ", ".join(
                        f'"{_toml_escape(v)}"' for v in values
                    )
                    lines.append(f"{key} = [{items_str}]")
            lines.append("")
        return "\n".join(lines)


class SystemdUnitRestorer:
    """Restaure un fichier unit systemd depuis un TOML générique.

    Lit le TOML produit par SystemdUnitExporter, vérifie les
    prérequis, reconstruit le fichier INI, l'installe dans dest_dir,
    active l'unit si enabled=true et recharge le daemon systemd.

    Le nom de l'unit est déduit du nom du fichier TOML selon la
    convention : ``{nom}-{type}.toml`` → ``{nom}.{type}``
    (ex : ``thermal-monitor-service.toml`` → ``thermal-monitor.service``).

    Attributes:
        _executor: Exécuteur systemctl injecté (optionnel).
        _logger: Logger injecté.

    Example:
        >>> restorer = SystemdUnitRestorer(executor=executor, logger=logger)
        >>> ok, name = restorer.restore(
        ...     Path("mon-service.toml"),
        ...     Path("/etc/systemd/system"),
        ... )
    """

    def __init__(
        self,
        executor: "SystemdExecutor | None" = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialise le restaureur.

        Args:
            executor: Exécuteur systemctl injecté (SystemdExecutor ou
                UserSystemdExecutor). Si None, utilise subprocess
                directement.
            logger: Logger injecté. Défaut : ConsoleLogger.
        """
        self._executor = executor
        self._logger = logger or ConsoleLogger()

    def restore(
        self,
        toml_path: Path,
        dest_dir: Path,
        dry_run: bool = False,
        user: bool = False,
    ) -> tuple[bool, str]:
        """Restaure une unit depuis un fichier TOML générique.

        Lit le TOML, vérifie le prérequis requires_exec, écrit le
        fichier INI dans dest_dir, active l'unit si enabled=true,
        puis recharge le daemon.

        Args:
            toml_path: Chemin du fichier .toml source.
            dest_dir: Répertoire de destination
                (ex : /etc/systemd/system/).
            dry_run: Si True, simule sans écriture réelle.
            user: Si True et qu'aucun executor n'est injecté, ajoute
                --user aux commandes systemctl. Ignoré si un executor
                est fourni (utiliser UserSystemdExecutor à la place).

        Returns:
            Tuple (succès, nom_unit). nom_unit est vide en cas d'échec
            ou de dry_run.
        """
        parsed = self._parse_meta(toml_path)
        if parsed is None:
            return (False, "")
        data, unit_type, enabled, requires_exec = parsed

        unit_name = self._resolve_unit_name(toml_path, unit_type)
        if unit_name is None:
            return (False, "")

        if requires_exec and not self._exec_present(requires_exec):
            self._logger.log_error(
                f"{unit_name} — prérequis manquant : {requires_exec}"
            )
            return (False, "")

        ini_content = self.to_ini(data, unit_type)

        if dry_run:
            self._logger.log_info(
                f"[dry-run] {unit_name} ← {toml_path.name}"
            )
            return (True, "")

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / unit_name
        try:
            write_text_secure(str(dest), ini_content)
        except OSError as exc:
            self._logger.log_error(
                f"Écriture de {dest} refusée : {exc}"
            )
            return (False, "")
        self._logger.log_info(f"{unit_name} → {dest}")

        if enabled:
            self._enable(unit_name, user=user)
        self._daemon_reload(user=user)
        return (True, unit_name)

    def _parse_meta(
        self, toml_path: Path
    ) -> "tuple[dict[str, object], str, bool, str] | None":
        """Parse le fichier TOML et extrait les métadonnées.

        Args:
            toml_path: Chemin du fichier TOML source.

        Returns:
            Tuple (data, unit_type, enabled, requires_exec) ou None si erreur.
        """
        try:
            data = tomllib.loads(
                toml_path.read_text(encoding="utf-8")
            )
        except (OSError, tomllib.TOMLDecodeError) as exc:
            self._logger.log_error(
                f"{toml_path.name} illisible : {exc}"
            )
            return None
        meta = data.get("meta", {})
        unit_type = str(meta.get("unit_type", ""))
        if unit_type not in _SUPPORTED_UNIT_TYPES:
            self._logger.log_error(
                f"{toml_path.name} — unit_type invalide : {unit_type!r}"
            )
            return None
        enabled = bool(meta.get("enabled", False))
        requires_exec = str(meta.get("requires_exec", ""))
        return data, unit_type, enabled, requires_exec

    def _resolve_unit_name(
        self, toml_path: Path, unit_type: str
    ) -> str | None:
        """Déduit et valide le nom d'unité depuis le stem du fichier TOML.

        Convention : ``{nom}-{type}.toml`` → ``{nom}.{type}``.

        Args:
            toml_path: Chemin du fichier TOML.
            unit_type: Type d'unit extrait des métadonnées.

        Returns:
            Nom d'unité validé ou None si incohérent/invalide.
        """
        stem = toml_path.stem
        if not stem.endswith(f"-{unit_type}"):
            self._logger.log_error(
                f"{toml_path.name} — stem {stem!r} incohérent "
                f"avec unit_type {unit_type!r}"
            )
            return None
        unit_name = stem[: -len(unit_type) - 1] + "." + unit_type
        try:
            validate_full_unit_name(unit_name)
        except ValueError as exc:
            self._logger.log_error(
                f"{toml_path.name} — nom d'unité invalide : {exc}"
            )
            return None
        return unit_name

    @staticmethod
    def to_ini(
        data: dict[str, object],
        unit_type: str,
    ) -> str:
        """Reconstruit le contenu INI d'un fichier unit depuis le dict TOML.

        Ignore [meta] et les sous-tables non-INI. Reproduit les sections
        [Unit], [Service/Timer/Mount], [Install] dans l'ordre standard.

        Args:
            data: Dict issu de tomllib.loads().
            unit_type: Type d'unit ("service", "timer", "mount").

        Returns:
            Contenu INI prêt à écrire dans le répertoire systemd.
        """
        section_order = ["Unit", unit_type.capitalize(), "Install"]
        lines: list[str] = []
        for section in section_order:
            if section not in data:
                continue
            lines.append(f"[{section}]")
            for key, value in data[section].items():  # type: ignore
                if isinstance(value, list):
                    for v in value:
                        lines.append(
                            f"{key}={reject_control_chars(str(v), key)}"
                        )
                else:
                    lines.append(
                        f"{key}={reject_control_chars(str(value), key)}"
                    )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _exec_present(path_or_name: str) -> bool:
        """Vérifie que le binaire requis est présent sur le système.

        Args:
            path_or_name: Chemin absolu ou nom de binaire dans PATH.

        Returns:
            True si le binaire est trouvé.
        """
        p = Path(path_or_name)
        if p.is_absolute():
            return p.exists()
        return shutil.which(path_or_name) is not None

    def _run_systemctl_fallback(
        self, *args: str, user: bool = False
    ) -> None:
        """Exécute systemctl en fallback sans executor injecté.

        Args:
            *args: Arguments systemctl (ex: "enable", "unit-name").
            user: Si True, ajoute --user.
        """
        cmd = ["systemctl"]
        if user:
            cmd.append("--user")
        cmd.extend(args)
        subprocess.run(cmd, check=False)  # nosec B603

    def _enable(self, unit_name: str, user: bool = False) -> None:
        """Active une unit via l'exécuteur injecté ou subprocess.

        Args:
            unit_name: Nom de l'unit à activer.
            user: Si True et pas d'executor, ajoute --user.
        """
        if self._executor is not None:
            self._executor.enable_unit(unit_name)
        else:
            self._run_systemctl_fallback("enable", unit_name, user=user)

    def _daemon_reload(self, user: bool = False) -> None:
        """Recharge le daemon systemd via l'exécuteur ou subprocess.

        Args:
            user: Si True et pas d'executor, ajoute --user.
        """
        if self._executor is not None:
            self._executor.reload_systemd()
        else:
            self._run_systemctl_fallback("daemon-reload", user=user)
