"""Primitive partagée d'écriture distante via `install`."""


def build_remote_write_command(mode: int, dest: str) -> list[str]:
    """Construit `install -m <mode> -T /dev/stdin <dest>`.

    Seule commande validée pour écrire un fichier sur une cible
    distante (invariant projet, voir CONTEXT.md) : `-m` applique le
    mode dès la création du fichier — aucune fenêtre où il serait
    lisible avec l'umask distant — et `-T` (--no-target-directory)
    empêche `install` de suivre un symlink planté en position de
    destination (le lien est remplacé, pas traversé) ou de créer un
    fichier fantôme si la destination est un répertoire. Le contenu
    n'est jamais inclus dans cette commande : il doit toujours être
    transmis séparément via `stdin`, jamais par argument (`ps`
    l'exposerait sinon).

    Args:
        mode: Permissions POSIX à appliquer (ex. 0o644).
        dest: Chemin de destination sur l'hôte distant.

    Returns:
        La commande sous forme de liste, prête pour
        `CommandExecutor.run(cmd, stdin=content)` (ou tout passe-plat
        de même signature, ex. `SystemdExecutor.run_raw`).
    """
    return ["install", "-m", format(mode, "03o"), "-T", "/dev/stdin", dest]


def build_remote_exists_command(dest: str) -> list[str]:
    """Construit ``test -e <dest> -o -L <dest>``.

    Sonde d'existence : vrai pour un fichier existant comme pour un lien
    symbolique, même cassé. Code 0 = existe, 1 = absent, autre = sonde
    ambiguë (à traiter en échec fermé).

    Args:
        dest: Chemin à sonder sur l'hôte distant.

    Returns:
        La commande sous forme de liste.
    """
    return ["test", "-e", dest, "-o", "-L", dest]


def build_remote_is_dir_command(dest: str) -> list[str]:
    """Construit ``test -d <dest> -a ! -L <dest>``.

    Sonde « dossier réel » : un lien symbolique vers un dossier n'en est
    pas un (il reste traité comme un fichier présent). Code 0 = dossier.

    Args:
        dest: Chemin à sonder sur l'hôte distant.

    Returns:
        La commande sous forme de liste.
    """
    return ["test", "-d", dest, "-a", "!", "-L", dest]


def build_remote_link_command(tmp: str, dest: str) -> list[str]:
    """Construit ``ln -T -- <tmp> <dest>``.

    Lien dur atomique : échoue si ``dest`` existe déjà, ce qui garantit la
    création exclusive (``noclobber`` n'est pas utilisé : il diffère
    entre bash et dash).

    Args:
        tmp: Fichier temporaire déjà écrit.
        dest: Destination finale, qui ne doit pas exister.

    Returns:
        La commande sous forme de liste.
    """
    return ["ln", "-T", "--", tmp, dest]
