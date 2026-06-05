"""Persistance des peripheriques reseau en JSON.

Ce module fournit l'implementation JsonDeviceRepository pour
sauvegarder et charger les peripheriques depuis un fichier JSON.
"""

import dataclasses
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from linux_python_utils.logging.base import Logger
from linux_python_utils.network.base import DeviceRepository
from linux_python_utils.network.models import NetworkDevice


class JsonDeviceRepository(DeviceRepository):
    """Repository de peripheriques au format JSON.

    Attributes:
        _file_path: Chemin du fichier JSON.
        _logger: Logger optionnel.
    """

    def __init__(
        self,
        file_path: str,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialise le repository JSON.

        Args:
            file_path: Chemin du fichier JSON.
            logger: Logger optionnel.
        """
        self._file_path = Path(file_path)
        self._logger = logger

    def load(self) -> List[NetworkDevice]:
        """Charge les peripheriques depuis le fichier JSON.

        Returns:
            Liste des peripheriques. Liste vide si le fichier
            n'existe pas ou est vide.
        """
        if not self._file_path.exists():
            return []
        content = self._file_path.read_text(
            encoding="utf-8"
        )
        if not content.strip():
            return []
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, OSError) as exc:
            if self._logger:
                self._logger.log_warning(
                    f"Inventaire illisible : {exc}"
                )
            return []
        devices = [
            NetworkDevice.from_dict(d) for d in data
        ]
        if self._logger:
            self._logger.log_info(
                f"Charge {len(devices)} peripherique(s) "
                f"depuis {self._file_path}"
            )
        return devices

    def save(
        self, devices: List[NetworkDevice]
    ) -> None:
        """Sauvegarde les peripheriques au format JSON.

        Args:
            devices: Liste des peripheriques a sauvegarder.
        """
        payload = json.dumps(
            [d.to_dict() for d in devices],
            indent=2,
            ensure_ascii=False,
        )
        fd, tmp = tempfile.mkstemp(
            dir=str(self._file_path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.chmod(tmp, 0o644)
            os.replace(tmp, self._file_path)
        except BaseException:
            os.unlink(tmp)
            raise
        if self._logger:
            self._logger.log_info(
                f"Sauvegarde {len(devices)} peripherique(s)"
                f" dans {self._file_path}"
            )

    def find_by_mac(
        self, mac: str
    ) -> Optional[NetworkDevice]:
        """Recherche un peripherique par adresse MAC.

        Args:
            mac: Adresse MAC (insensible a la casse).

        Returns:
            Le peripherique trouve ou None.
        """
        mac_lower = mac.lower()
        for device in self.load():
            if device.mac == mac_lower:
                return device
        return None

    def find_by_ip(
        self, ip: str
    ) -> Optional[NetworkDevice]:
        """Recherche un peripherique par adresse IP.

        Args:
            ip: Adresse IP a rechercher.

        Returns:
            Le peripherique trouve ou None.
        """
        for device in self.load():
            if device.ip == ip:
                return device
        return None

    def merge_scan_results(
        self,
        existing: List[NetworkDevice],
        scanned: List[NetworkDevice],
    ) -> Tuple[
        List[NetworkDevice],
        List[NetworkDevice],
        List[NetworkDevice],
    ]:
        """Fusionne les resultats d'un scan avec l'inventaire.

        Args:
            existing: Peripheriques existants dans l'inventaire.
            scanned: Peripheriques decouverts par le scan.

        Returns:
            Tuple (merged, new_devices, disappeared_devices).
        """
        existing_by_mac = {d.mac: d for d in existing}
        scanned_macs = set()
        merged: List[NetworkDevice] = []
        new_devices: List[NetworkDevice] = []

        for device in scanned:
            scanned_macs.add(device.mac)
            if device.mac in existing_by_mac:
                old = existing_by_mac[device.mac]
                updated = dataclasses.replace(
                    old,
                    ip=device.ip if device.ip else old.ip,
                    last_seen=datetime.now(),
                )
                merged.append(updated)
            else:
                new_devices.append(device)
                merged.append(device)

        disappeared = [
            d
            for d in existing
            if d.mac not in scanned_macs
        ]

        return merged, new_devices, disappeared
