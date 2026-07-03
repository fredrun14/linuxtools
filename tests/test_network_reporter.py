"""Tests pour les reporters reseau."""

import csv
import io
import json

from linuxtools.network.models import NetworkDevice
from linuxtools.network.reporter import (
    ConsoleTableReporter,
    CsvReporter,
    DiffReporter,
    JsonReporter,
)


def _device(
    ip: str = "192.168.1.1",
    mac: str = "aa:bb:cc:dd:ee:ff",
    **kwargs,
) -> NetworkDevice:
    """Cree un NetworkDevice pour les tests."""
    return NetworkDevice(ip=ip, mac=mac, **kwargs)


class TestConsoleTableReporter:
    """Tests pour ConsoleTableReporter."""

    def test_rapport_formate(self) -> None:
        """Contient en-tete et lignes de donnees."""
        reporter = ConsoleTableReporter()
        devices = [
            _device(hostname="nas", vendor="Synology")
        ]
        output = reporter.report(devices)
        assert "IP" in output
        assert "MAC" in output
        assert "192.168.1.1" in output
        assert "nas" in output

    def test_rapport_tri_par_ip(self) -> None:
        """192.168.1.1 avant 192.168.1.10."""
        reporter = ConsoleTableReporter()
        devices = [
            _device("192.168.1.10", "aa:bb:cc:dd:ee:01"),
            _device("192.168.1.1", "aa:bb:cc:dd:ee:02"),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:03"),
        ]
        output = reporter.report(devices)
        lines = output.split("\n")
        data_lines = [
            l for l in lines
            if "192.168.1." in l and "---" not in l
        ]
        ips = [l.split()[0] for l in data_lines]
        assert ips == [
            "192.168.1.1",
            "192.168.1.2",
            "192.168.1.10",
        ]

    def test_rapport_liste_vide(self) -> None:
        """Liste vide affiche 'Aucun peripherique'."""
        reporter = ConsoleTableReporter()
        output = reporter.report([])
        assert "Aucun peripherique" in output

    def test_rapport_resume(self) -> None:
        """Resume avec total et compteurs."""
        reporter = ConsoleTableReporter()
        devices = [
            _device(
                "192.168.1.1",
                "aa:bb:cc:dd:ee:01",
                is_known=True,
            ),
            _device("192.168.1.2", "aa:bb:cc:dd:ee:02"),
        ]
        output = reporter.report(devices)
        assert "Total : 2" in output
        assert "Connus : 1" in output
        assert "Nouveaux : 1" in output

    def test_appareil_sans_ip_affiche_hors_ligne(
        self,
    ) -> None:
        """Un appareil avec ip='' affiche '(hors ligne)'."""
        reporter = ConsoleTableReporter()
        devices = [
            _device("", "aa:bb:cc:dd:ee:ff", hostname="Thermo")
        ]
        output = reporter.report(devices)
        assert "(hors ligne)" in output

    def test_appareils_sans_ip_tries_en_fin(self) -> None:
        """Les appareils sans IP apparaissent apres ceux avec IP."""
        reporter = ConsoleTableReporter()
        devices = [
            _device("", "aa:bb:cc:dd:ee:01", hostname="Offline"),
            _device("192.168.1.5", "aa:bb:cc:dd:ee:02"),
            _device("192.168.1.1", "aa:bb:cc:dd:ee:03"),
        ]
        output = reporter.report(devices)
        lines = [
            l for l in output.split("\n")
            if "192.168.1." in l or "(hors ligne)" in l
        ]
        # Les deux appareils avec IP doivent preceder l'offline
        assert "(hors ligne)" in lines[-1]


class TestCsvReporter:
    """Tests pour CsvReporter."""

    def test_entete_csv(self) -> None:
        """Premiere ligne = noms de colonnes."""
        reporter = CsvReporter()
        output = reporter.report([])
        first_line = output.strip().split("\n")[0]
        assert "ip" in first_line
        assert "mac" in first_line
        assert "hostname" in first_line

    def test_contenu_csv(self) -> None:
        """Donnees correctes dans le CSV."""
        reporter = CsvReporter()
        output = reporter.report([
            _device(hostname="nas")
        ])
        assert "192.168.1.1" in output
        assert "aa:bb:cc:dd:ee:ff" in output
        assert "nas" in output

    def test_csv_parsable(self) -> None:
        """CSV relisible via csv.reader."""
        reporter = CsvReporter()
        output = reporter.report([_device()])
        reader = csv.reader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 2  # header + 1 device

    def test_csv_liste_vide(self) -> None:
        """En-tete uniquement pour liste vide."""
        reporter = CsvReporter()
        output = reporter.report([])
        reader = csv.reader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 1


class TestJsonReporter:
    """Tests pour JsonReporter."""

    def test_json_valide(self) -> None:
        """json.loads ne leve pas d'erreur."""
        reporter = JsonReporter()
        output = reporter.report([_device()])
        json.loads(output)  # ne leve pas

    def test_json_contenu(self) -> None:
        """Donnees correctes dans le JSON."""
        reporter = JsonReporter()
        output = reporter.report([
            _device(hostname="nas")
        ])
        data = json.loads(output)
        assert data[0]["ip"] == "192.168.1.1"
        assert data[0]["hostname"] == "nas"

    def test_json_liste_vide(self) -> None:
        """Liste vide donne '[]'."""
        reporter = JsonReporter()
        output = reporter.report([])
        assert json.loads(output) == []


class TestDiffReporter:
    """Tests pour DiffReporter."""

    def test_rapport_nouveaux(self) -> None:
        """Section nouveaux affichee."""
        new = [_device()]
        reporter = DiffReporter(new, [])
        output = reporter.report([])
        assert "Nouveaux peripheriques" in output
        assert "192.168.1.1" in output

    def test_rapport_disparus(self) -> None:
        """Section disparus affichee."""
        gone = [_device()]
        reporter = DiffReporter([], gone)
        output = reporter.report([])
        assert "Peripheriques disparus" in output

    def test_rapport_aucun_changement(self) -> None:
        """Message 'Aucun changement'."""
        reporter = DiffReporter([], [])
        output = reporter.report([])
        assert "Aucun changement" in output

    def test_rapport_mixte(self) -> None:
        """Nouveaux + disparus."""
        new = [_device("192.168.1.10", "aa:bb:cc:dd:ee:01")]
        gone = [_device("192.168.1.20", "aa:bb:cc:dd:ee:02")]
        reporter = DiffReporter(new, gone)
        output = reporter.report([])
        assert "Nouveaux" in output
        assert "disparus" in output
        assert "1 nouveau" in output
        assert "1 disparu" in output


class TestDiffReporterIpChange:
    """Tests pour DiffReporter avec IP changee."""

    def test_rapport_inclut_ip_changee(self) -> None:
        """DiffReporter signale les appareils dont l'IP a change."""
        reporter = DiffReporter([], [])
        current = [
            _device("192.168.1.200", "aa:bb:cc:dd:ee:ff", fixed_ip="192.168.1.10")
        ]
        output = reporter.report(current)
        assert "IP changee" in output
        assert "192.168.1.10" in output
