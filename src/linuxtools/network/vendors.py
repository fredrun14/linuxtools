"""Table de correspondance vendeur → type de peripherique reseau."""

_VENDOR_TYPES: tuple[tuple[str, str], ...] = (
    ("synology", "NAS"),
    ("nvidia", "Media Player"),
    ("nintendo", "Console"),
    ("apple", "Apple"),
    ("oneplus", "Smartphone"),
    ("samsung", "Smartphone"),
    ("huawei", "Smartphone"),
    ("xiaomi", "Smartphone"),
    ("asustek", "Routeur"),
    ("philips light", "Eclairage"),
    ("philips hue", "Eclairage"),
    ("hangzhou", "Camera/IoT"),
    ("hikvision", "Camera"),
    ("amazon", "Amazon"),
    ("raspberry", "Raspberry Pi"),
    ("sonos", "Audio"),
    ("espressif", "IoT"),
    ("intel", "PC/Laptop"),
    ("realtek", "PC/Laptop"),
)


def _infer_type_from_vendor(vendor: str) -> str:
    """Infere le type d'appareil depuis le fabricant.

    Args:
        vendor: Nom du fabricant (OUI ou DPI).

    Returns:
        Type infere ou 'unknown'.
    """
    v = vendor.lower()
    for keyword, device_type in _VENDOR_TYPES:
        if keyword in v:
            return device_type
    return "unknown"
