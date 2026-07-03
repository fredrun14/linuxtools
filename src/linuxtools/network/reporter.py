"""Rapports et exports de peripheriques reseau.

Ce module fournit les implementations de DeviceReporter
pour generer des rapports en console, CSV, JSON et diff.
"""

import csv
import io
import json

from linuxtools.logging.base import Logger
from linuxtools.network.base import DeviceReporter
from linuxtools.network.models import NetworkDevice


def _sort_by_ip(
    devices: list[NetworkDevice],
) -> list[NetworkDevice]:
    """Trie les peripheriques par IP (octet par octet).

    Les appareils sans IP (hors ligne) sont places en fin
    de liste, tries par adresse MAC.

    Args:
        devices: Liste des peripheriques.

    Returns:
        Liste triee.
    """
    def _key(
        d: NetworkDevice,
    ) -> tuple[int, list[int], str]:
        if d.ip:
            return (0, [int(o) for o in d.ip.split(".")], "")
        return (1, [], d.mac)

    return sorted(devices, key=_key)


class ConsoleTableReporter(DeviceReporter):
    """Rapport en tableau formate pour la console.

    Attributes:
        _logger: Logger optionnel.
    """

    def __init__(
        self, logger: Logger | None = None
    ) -> None:
        """Initialise le reporter console.

        Args:
            logger: Logger optionnel.
        """
        self._logger = logger

    def report(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere un tableau formate des peripheriques.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Tableau formate pour la console.
        """
        cols = [
            ("IP", 16),
            ("MAC", 18),
            ("Hostname", 12),
            ("Vendor", 15),
            ("Type", 8),
            ("IP Fixe", 16),
            ("DNS", 20),
            ("Connu", 5),
        ]
        header = "".join(
            name.ljust(width) for name, width in cols
        )
        sep = "".join("-" * width for _, width in cols)
        lines = [header, sep]

        if not devices:
            lines.append("Aucun peripherique")
        else:
            for d in _sort_by_ip(devices):
                ip_display = d.ip if d.ip else "(hors ligne)"
                line = (
                    ip_display.ljust(16)
                    + d.mac.ljust(18)
                    + d.hostname.ljust(12)
                    + d.vendor[:14].ljust(15)
                    + d.device_type.ljust(8)
                    + (d.fixed_ip or "").ljust(16)
                    + (d.dns_name or "")[:19].ljust(20)
                    + ("Oui" if d.is_known
                       else "Non").ljust(5)
                )
                lines.append(line)

        total = len(devices)
        connus = sum(1 for d in devices if d.is_known)
        nouveaux = total - connus
        lines.append(sep)
        lines.append(
            f"Total : {total} | Connus : {connus} | "
            f"Nouveaux : {nouveaux}"
        )
        return "\n".join(lines) + "\n"


class CsvReporter(DeviceReporter):
    """Rapport au format CSV.

    Attributes:
        _logger: Logger optionnel.
    """

    FIELDNAMES = [
        "ip", "mac", "hostname", "vendor",
        "device_type", "is_known", "fixed_ip",
        "dns_name", "first_seen", "last_seen", "notes",
    ]

    def __init__(
        self, logger: Logger | None = None
    ) -> None:
        """Initialise le reporter CSV.

        Args:
            logger: Logger optionnel.
        """
        self._logger = logger

    def report(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere un rapport CSV des peripheriques.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Contenu CSV.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.FIELDNAMES)
        for d in devices:
            writer.writerow([
                d.ip,
                d.mac,
                d.hostname,
                d.vendor,
                d.device_type,
                d.is_known,
                d.fixed_ip or "",
                d.dns_name or "",
                d.first_seen.isoformat(),
                d.last_seen.isoformat(),
                d.notes,
            ])
        return output.getvalue()


class JsonReporter(DeviceReporter):
    """Rapport au format JSON.

    Attributes:
        _logger: Logger optionnel.
    """

    def __init__(
        self, logger: Logger | None = None
    ) -> None:
        """Initialise le reporter JSON.

        Args:
            logger: Logger optionnel.
        """
        self._logger = logger

    def report(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere un rapport JSON des peripheriques.

        Args:
            devices: Liste des peripheriques.

        Returns:
            Contenu JSON.
        """
        return json.dumps(
            [d.to_dict() for d in devices],
            indent=2,
            ensure_ascii=False,
        )


def _format_device_line(d: "NetworkDevice", prefix: str) -> str:
    """Formate une ligne de diff pour un peripherique.

    Args:
        d: Peripherique a afficher.
        prefix: Prefixe de ligne ('+' ou '-').

    Returns:
        Ligne formatee.
    """
    ip_str = d.ip if d.ip else "(hors ligne)"
    label = d.hostname or d.vendor
    return f"  {prefix} {ip_str:<16} {d.mac:<18} {label}"


class DiffReporter(DeviceReporter):
    """Rapport de differences entre scan et inventaire.

    Attributes:
        _new_devices: Nouveaux peripheriques decouverts.
        _disappeared: Peripheriques disparus.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        new_devices: list[NetworkDevice],
        disappeared: list[NetworkDevice],
        logger: Logger | None = None,
    ) -> None:
        """Initialise le reporter de differences.

        Args:
            new_devices: Nouveaux peripheriques.
            disappeared: Peripheriques disparus.
            logger: Logger optionnel.
        """
        self._new_devices = new_devices
        self._disappeared = disappeared
        self._logger = logger

    def report(
        self, devices: list[NetworkDevice]
    ) -> str:
        """Genere un rapport des differences.

        Args:
            devices: Liste complete des peripheriques
                (non utilisee directement, le diff utilise
                new_devices et disappeared).

        Returns:
            Rapport de differences formate.
        """
        lines: list[str] = []

        if self._new_devices:
            lines.append(
                f"=== Nouveaux peripheriques "
                f"({len(self._new_devices)}) ==="
            )
            lines.extend(
                _format_device_line(d, "+")
                for d in self._new_devices
            )
            lines.append("")

        if self._disappeared:
            lines.append(
                f"=== Peripheriques disparus "
                f"({len(self._disappeared)}) ==="
            )
            lines.extend(
                _format_device_line(d, "-")
                for d in self._disappeared
            )
            lines.append("")

        ip_changed = [
            d for d in devices
            if d.fixed_ip and d.ip != d.fixed_ip
        ]
        if ip_changed:
            lines.append(
                "=== IP changee ==="
            )
            for d in ip_changed:
                lines.append(
                    f"  ~ {d.mac:<18} "
                    f"{d.fixed_ip} -> {d.ip}"
                )
            lines.append("")

        if not lines:
            lines.append("Aucun changement detecte.")
            return "\n".join(lines) + "\n"

        total_changes = (
            len(self._new_devices)
            + len(self._disappeared)
        )
        lines.append(
            f"Resume : {len(self._new_devices)} "
            f"nouveau(x), "
            f"{len(self._disappeared)} disparu(s)"
        )
        return "\n".join(lines) + "\n"
