"""Modeles de donnees pour la gestion des credentials.

Ce module definit les dataclasses immuables CredentialKey
et Credential representant les cles et valeurs de secrets
applicatifs.
"""

from dataclasses import dataclass, field


def _validate_non_empty(field_name: str, value: str) -> None:
    """Leve ValueError si value est vide ou ne contient que des espaces."""
    if not value or not value.strip():
        raise ValueError(
            f"Le champ '{field_name}' ne peut pas etre vide."
        )


@dataclass(frozen=True)
class CredentialKey:
    """Cle d'identification d'un credential.

    Attributes:
        service: Nom du service applicatif (ex: "scannethome").
        key: Nom de la cle (ex: "ASUS_ROUTER_PASSWORD").
    """

    service: str
    key: str

    def __post_init__(self) -> None:
        """Valide les champs apres initialisation."""
        _validate_non_empty("service", self.service)
        _validate_non_empty("key", self.key)


@dataclass(frozen=True)
class Credential:
    """Credential complet : service, cle et valeur.

    Attributes:
        service: Nom du service applicatif.
        key: Nom de la cle.
        value: Valeur secrete du credential.
        source: Source d'ou provient la valeur
            (ex: "env", "dotenv", "keyring").
    """

    service: str
    key: str
    value: str = field(repr=False)  # jamais affiché (anti-fuite)
    source: str = ""

    def __post_init__(self) -> None:
        """Valide les champs apres initialisation."""
        _validate_non_empty("service", self.service)
        _validate_non_empty("key", self.key)

    @property
    def credential_key(self) -> CredentialKey:
        """Retourne la cle d'identification du credential.

        Returns:
            Instance de CredentialKey.
        """
        return CredentialKey(
            service=self.service,
            key=self.key,
        )
