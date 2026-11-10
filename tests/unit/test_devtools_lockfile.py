"""Tests du contrôle de lock (linuxtools.devtools.lockfile)."""

from __future__ import annotations

from linuxtools.devtools.lockfile import unexpected_lock_changes


def _lock(*packages: str, revision: int = 3) -> str:
    """Assemble un uv.lock minimal à partir de blocs [[package]]."""
    return f"version = 1\nrevision = {revision}\n\n" + "\n".join(packages)


def _pkg(
    name: str,
    version: str,
    deps: tuple[str, ...] = (),
    source: str = '{ registry = "https://pypi.org/simple" }',
    extras: tuple[str, ...] = (),
) -> str:
    """Construit un bloc [[package]]."""
    bloc = f'[[package]]\nname = "{name}"\nversion = "{version}"\n'
    bloc += f"source = {source}\n"
    if deps:
        liste = ", ".join(f'{{ name = "{d}" }}' for d in deps)
        bloc += f"dependencies = [{liste}]\n"
    if extras:
        liste = ", ".join(f'{{ name = "{d}" }}' for d in extras)
        bloc += f"\n[package.optional-dependencies]\ncredentials = [{liste}]\n"
    return bloc


_GIT_V1 = '{ git = "https://git.example/linuxtools.git?tag=v1#aaa" }'
_GIT_V2 = '{ git = "https://git.example/linuxtools.git?tag=v2#bbb" }'


def test_changement_linuxtools_et_platformdirs_autorise() -> None:
    old = _lock(
        _pkg("linuxtools", "1", ("platformdirs",), _GIT_V1),
        _pkg("platformdirs", "4.1"),
        _pkg("pytest", "9.0"),
    )
    new = _lock(
        _pkg("linuxtools", "2", ("platformdirs",), _GIT_V2),
        _pkg("platformdirs", "4.2"),
        _pkg("pytest", "9.0"),
    )

    assert unexpected_lock_changes(old, new) == []


def test_changement_hors_fermeture_signale() -> None:
    old = _lock(
        _pkg("linuxtools", "1", ("platformdirs",), _GIT_V1),
        _pkg("platformdirs", "4.1"),
        _pkg("pytest", "9.0"),
        _pkg("mypy", "2.0"),
    )
    new = _lock(
        _pkg("linuxtools", "2", ("platformdirs",), _GIT_V2),
        _pkg("platformdirs", "4.1"),
        _pkg("pytest", "9.1"),
        _pkg("mypy", "2.1"),
    )

    assert unexpected_lock_changes(old, new) == ["mypy", "pytest"]


def test_changement_de_source_signale() -> None:
    old = _lock(_pkg("pytest", "9.0"))
    new = _lock(_pkg("pytest", "9.0", source='{ git = "https://x/y" }'))

    assert unexpected_lock_changes(old, new) == ["pytest"]


def test_en_tete_revision_ignore() -> None:
    paquet = _pkg("pytest", "9.0")

    old = _lock(paquet, revision=2)
    new = _lock(paquet, revision=3)

    assert unexpected_lock_changes(old, new) == []


def test_paquet_ajoute_hors_fermeture_signale() -> None:
    old = _lock(_pkg("linuxtools", "1", (), _GIT_V1))
    new = _lock(
        _pkg("linuxtools", "2", (), _GIT_V2),
        _pkg("intrus", "1.0"),
    )

    assert unexpected_lock_changes(old, new) == ["intrus"]


def test_paquet_retire_hors_fermeture_signale() -> None:
    old = _lock(_pkg("linuxtools", "1", (), _GIT_V1), _pkg("vieux", "1"))
    new = _lock(_pkg("linuxtools", "2", (), _GIT_V2))

    assert unexpected_lock_changes(old, new) == ["vieux"]


def test_fermeture_transitive_et_extras_autorises() -> None:
    old = _lock(
        _pkg("linuxtools", "1", ("a",), _GIT_V1, extras=("kr",)),
        _pkg("a", "1", ("b",)),
        _pkg("b", "1"),
        _pkg("kr", "1"),
    )
    new = _lock(
        _pkg("linuxtools", "2", ("a",), _GIT_V2, extras=("kr",)),
        _pkg("a", "2", ("b",)),
        _pkg("b", "2"),
        _pkg("kr", "2"),
    )

    assert unexpected_lock_changes(old, new) == []


def test_racine_personnalisee() -> None:
    old = _lock(_pkg("autre", "1"), _pkg("linuxtools", "1"))
    new = _lock(_pkg("autre", "2"), _pkg("linuxtools", "2"))

    assert unexpected_lock_changes(old, new, root="autre") == ["linuxtools"]


def test_fermeture_tolere_cycle_et_dependance_absente() -> None:
    old = _lock(
        _pkg("linuxtools", "1", ("a", "fantome"), _GIT_V1),
        _pkg("a", "1", ("linuxtools",)),
    )
    new = _lock(
        _pkg("linuxtools", "2", ("a", "fantome"), _GIT_V2),
        _pkg("a", "2", ("linuxtools",)),
    )

    assert unexpected_lock_changes(old, new) == []
