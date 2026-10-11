"""Tests pour LanClient et load_lan_clients."""

import dataclasses

import pytest

from linuxtools.network.clients import LanClient, load_lan_clients


def test_load_lan_clients_table_valide_normalise_mac() -> None:
    """Une table valide donne un LanClient à MAC en majuscules."""
    # Arrange
    entries = [{"mac": "aa:bb:cc:dd:ee:ff"}]

    # Act
    result = load_lan_clients(entries)

    # Assert
    assert result == (LanClient(mac="AA:BB:CC:DD:EE:FF"),)


def test_load_lan_clients_non_liste_leve_valueerror() -> None:
    """Une entrée qui n'est pas une liste est rejetée."""
    # Act / Assert
    with pytest.raises(
        ValueError, match="client doit être une liste de tables"
    ):
        load_lan_clients("aa:bb:cc:dd:ee:ff")


def test_load_lan_clients_entree_non_table_leve_valueerror() -> None:
    """Une entrée qui n'est pas une table est rejetée."""
    # Act / Assert
    with pytest.raises(ValueError, match="entrée de client invalide : .aa:bb"):
        load_lan_clients(["aa:bb:cc:dd:ee:ff"])


@pytest.mark.parametrize("entry", [{}, {"mac": 42}, {"mac": None}])
def test_load_lan_clients_mac_absente_ou_mauvais_type(
    entry: dict[str, object],
) -> None:
    """Une MAC absente ou non str est rejetée en ValueError."""
    # Act / Assert
    with pytest.raises(ValueError, match="MAC invalide : "):
        load_lan_clients([entry])


def test_load_lan_clients_mac_invalide_leve_valueerror() -> None:
    """Une MAC mal formée est rejetée par validate_mac."""
    # Act / Assert
    with pytest.raises(ValueError, match="MAC invalide : .pas-une-mac"):
        load_lan_clients([{"mac": "pas-une-mac"}])


def test_load_lan_clients_mac_en_doublon_apres_normalisation() -> None:
    """Deux MAC identiques à la casse près sont rejetées."""
    # Arrange
    entries = [
        {"mac": "aa:bb:cc:dd:ee:ff"},
        {"mac": "AA:BB:CC:DD:EE:FF"},
    ]

    # Act / Assert
    with pytest.raises(ValueError, match="MAC en doublon : AA:BB:CC:DD:EE:FF"):
        load_lan_clients(entries)


def test_load_lan_clients_name_validator_valeur_retournee_stockee() -> None:
    """Le nom stocké est la valeur retournée par le validateur."""

    # Arrange
    def valider(raw: object) -> str | None:
        return f"{raw}-ok"

    # Act
    result = load_lan_clients(
        [{"mac": "aa:bb:cc:dd:ee:ff", "name": "tv"}],
        name_validator=valider,
    )

    # Assert
    assert result[0].name == "tv-ok"


def test_load_lan_clients_name_validator_recoit_none_si_absent() -> None:
    """Le validateur de nom est appelé avec None quand le nom manque."""
    # Arrange
    recus: list[object] = []

    def valider(raw: object) -> str | None:
        recus.append(raw)
        return None

    # Act
    load_lan_clients([{"mac": "aa:bb:cc:dd:ee:ff"}], name_validator=valider)

    # Assert
    assert recus == [None]


def test_load_lan_clients_name_validator_qui_leve_propage() -> None:
    """Un validateur de nom qui lève fait échouer le chargement."""

    # Arrange
    def refuser(raw: object) -> str | None:
        raise ValueError("nom refusé")

    # Act / Assert
    with pytest.raises(ValueError, match="nom refusé"):
        load_lan_clients(
            [{"mac": "aa:bb:cc:dd:ee:ff", "name": "x"}],
            name_validator=refuser,
        )


def test_load_lan_clients_sans_validateur_str_prise_telle_quelle() -> None:
    """Sans validateur : un nom str est conservé, un non-str devient None."""
    # Arrange
    entries = [
        {"mac": "aa:bb:cc:dd:ee:01", "name": "Salon TV"},
        {"mac": "aa:bb:cc:dd:ee:02", "name": 42},
        {"mac": "aa:bb:cc:dd:ee:03"},
    ]

    # Act
    result = load_lan_clients(entries)

    # Assert
    assert [c.name for c in result] == ["Salon TV", None, None]


def test_load_lan_clients_ip_validator_valeur_retournee_stockee() -> None:
    """L'IP stockée est la valeur retournée par le validateur d'IP."""

    # Arrange
    def valider(raw: object) -> str | None:
        return f"{raw}!"

    # Act
    result = load_lan_clients(
        [{"mac": "aa:bb:cc:dd:ee:ff", "ip": "192.168.1.10"}],
        ip_validator=valider,
    )

    # Assert
    assert result[0].pinned_ip == "192.168.1.10!"


def test_load_lan_clients_ip_validator_recoit_none_si_absent() -> None:
    """Le validateur d'IP est appelé avec None quand l'IP manque."""
    # Arrange
    recus: list[object] = []

    def valider(raw: object) -> str | None:
        recus.append(raw)
        return None

    # Act
    load_lan_clients([{"mac": "aa:bb:cc:dd:ee:ff"}], ip_validator=valider)

    # Assert
    assert recus == [None]


def test_load_lan_clients_ip_validator_qui_leve_propage() -> None:
    """Un validateur d'IP qui lève fait échouer le chargement."""

    # Arrange
    def refuser(raw: object) -> str | None:
        raise ValueError("ip refusée")

    # Act / Assert
    with pytest.raises(ValueError, match="ip refusée"):
        load_lan_clients(
            [{"mac": "aa:bb:cc:dd:ee:ff", "ip": "127.0.0.1"}],
            ip_validator=refuser,
        )


def test_load_lan_clients_ip_sans_validateur_str_ou_none() -> None:
    """Sans validateur : une IP str est conservée, un non-str → None."""
    # Arrange
    entries = [
        {"mac": "aa:bb:cc:dd:ee:01", "ip": "10.0.0.5"},
        {"mac": "aa:bb:cc:dd:ee:02", "ip": 5},
    ]

    # Act
    result = load_lan_clients(entries)

    # Assert
    assert [c.pinned_ip for c in result] == ["10.0.0.5", None]


def test_load_lan_clients_dedup_names_rejette_nom_en_doublon() -> None:
    """Avec dedup_names=True, deux noms identiques sont rejetés."""
    # Arrange
    entries = [
        {"mac": "aa:bb:cc:dd:ee:01", "name": "tv"},
        {"mac": "aa:bb:cc:dd:ee:02", "name": "tv"},
    ]

    # Act / Assert
    with pytest.raises(ValueError, match="nom de client en doublon : tv"):
        load_lan_clients(entries, dedup_names=True)


def test_load_lan_clients_noms_en_doublon_acceptes_par_defaut() -> None:
    """Sans dedup_names, des noms identiques sont acceptés."""
    # Arrange
    entries = [
        {"mac": "aa:bb:cc:dd:ee:01", "name": "tv"},
        {"mac": "aa:bb:cc:dd:ee:02", "name": "tv"},
    ]

    # Act
    result = load_lan_clients(entries)

    # Assert
    assert len(result) == 2


def test_load_lan_clients_dedup_names_ignore_les_none() -> None:
    """Avec dedup_names=True, plusieurs noms None ne sont pas des doublons."""
    # Arrange
    entries = [
        {"mac": "aa:bb:cc:dd:ee:01"},
        {"mac": "aa:bb:cc:dd:ee:02"},
    ]

    # Act
    result = load_lan_clients(entries, dedup_names=True)

    # Assert
    assert len(result) == 2


def test_load_lan_clients_require_non_empty_rejette_liste_vide() -> None:
    """Avec require_non_empty=True, une liste vide est rejetée."""
    # Act / Assert
    with pytest.raises(ValueError, match="au moins un client requis"):
        load_lan_clients([], require_non_empty=True)


def test_load_lan_clients_liste_vide_acceptee_par_defaut() -> None:
    """Sans require_non_empty, une liste vide donne un tuple vide."""
    # Act / Assert
    assert load_lan_clients([]) == ()


def test_load_lan_clients_ordre_preserve_et_tuple_immuable() -> None:
    """L'ordre d'entrée est préservé et le résultat est un tuple."""
    # Arrange
    entries = [
        {"mac": "aa:bb:cc:dd:ee:03"},
        {"mac": "aa:bb:cc:dd:ee:01"},
        {"mac": "aa:bb:cc:dd:ee:02"},
    ]

    # Act
    result = load_lan_clients(entries)

    # Assert
    assert isinstance(result, tuple)
    assert [c.mac for c in result] == [
        "AA:BB:CC:DD:EE:03",
        "AA:BB:CC:DD:EE:01",
        "AA:BB:CC:DD:EE:02",
    ]


def test_lan_client_est_immuable() -> None:
    """LanClient est frozen : toute affectation lève."""
    # Arrange
    client = LanClient(mac="aa:bb:cc:dd:ee:ff")

    champ = "name"

    # Act / Assert
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(client, champ, "x")


def test_load_lan_clients_mac_validee_avant_les_validateurs() -> None:
    """Une MAC invalide est signalée avant tout appel aux validateurs."""

    # Arrange
    def refuser(raw: object) -> str | None:
        raise ValueError("nom refusé")

    # Act / Assert
    with pytest.raises(ValueError, match="MAC invalide : .zz"):
        load_lan_clients([{"mac": "zz", "name": "x"}], name_validator=refuser)


def test_lan_client_et_loader_exposes_a_la_racine() -> None:
    """LanClient et load_lan_clients sont importables depuis linuxtools."""
    # Act
    import linuxtools
    from linuxtools.network import clients

    # Assert
    assert linuxtools.LanClient is clients.LanClient
    assert linuxtools.load_lan_clients is clients.load_lan_clients
    assert {"LanClient", "load_lan_clients"} <= set(linuxtools.__all__)


def test_load_lan_clients_require_non_empty_accepte_liste_non_vide() -> None:
    """require_non_empty=True n'empêche pas une liste non vide."""
    # Act
    result = load_lan_clients(
        [{"mac": "aa:bb:cc:dd:ee:ff"}], require_non_empty=True
    )

    # Assert
    assert len(result) == 1


def test_load_lan_clients_dedup_names_sur_valeur_normalisee() -> None:
    """La dédup de noms porte sur la valeur stockée par le validateur."""

    # Arrange
    def minuscules(raw: object) -> str | None:
        return str(raw).lower()

    entries = [
        {"mac": "aa:bb:cc:dd:ee:01", "name": "TV"},
        {"mac": "aa:bb:cc:dd:ee:02", "name": "tv"},
    ]

    # Act / Assert
    with pytest.raises(ValueError, match="nom de client en doublon : tv"):
        load_lan_clients(entries, name_validator=minuscules, dedup_names=True)


def test_load_lan_clients_mac_doublon_prioritaire_sur_nom_doublon() -> None:
    """Une MAC en doublon est signalée avant un nom en doublon."""
    # Arrange
    entries = [
        {"mac": "aa:bb:cc:dd:ee:01", "name": "tv"},
        {"mac": "aa:bb:cc:dd:ee:01", "name": "tv"},
    ]

    # Act / Assert
    with pytest.raises(ValueError, match="MAC en doublon"):
        load_lan_clients(entries, dedup_names=True)


def test_lan_client_construction_directe_mac_invalide() -> None:
    """LanClient valide aussi la MAC hors du loader."""
    # Act / Assert
    with pytest.raises(ValueError, match="MAC invalide : .invalide"):
        LanClient(mac="invalide")


@pytest.mark.parametrize(
    "mac", [True, " aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff "]
)
def test_load_lan_clients_mac_bool_ou_espaces_rejetee(mac: object) -> None:
    """Une MAC booléenne ou entourée d'espaces est rejetée."""
    # Act / Assert
    with pytest.raises(ValueError, match="MAC invalide : "):
        load_lan_clients([{"mac": mac}])
