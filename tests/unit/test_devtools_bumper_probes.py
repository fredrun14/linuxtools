"""Tests des sondes et du dry-run de ConsumerBumper (T6)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from linuxtools.devtools.bumper import ConsumerBumper
from linuxtools.devtools.discovery import Consumer
from linuxtools.devtools.report import Status
from tests.unit.scripted_executor import ScriptedExecutor

if TYPE_CHECKING:
    from pathlib import Path

    from linuxtools.devtools.report import BumpOutcome

_FORGEJO = "https://git.ricfasohel.fr/fred/app.git"
_BRANCHE = "chore/pin-linuxtools-2-11-1"
_CO_AUTHOR = "Claude Sonnet 5.5 <noreply@anthropic.com>"


def _pin(tag: str) -> str:
    return (
        "linuxtools[credentials] @ "
        f"git+https://git.ricfasohel.fr/fred/linuxtools.git@{tag}"
    )


def _pyproject(
    tag: str = "v2.10.0",
    extra_deps: tuple[str, ...] = (),
    contrat: bool = True,
) -> str:
    deps = ", ".join(f'"{d}"' for d in (_pin(tag), *extra_deps))
    texte = f'[project]\nname = "app"\ndependencies = [{deps}]\n'
    if contrat:
        texte += (
            "[tool.linuxtools.consumer]\n"
            'sync-args = ["--extra", "dev"]\n'
            'checks = [["pytest"], ["mypy", "src/app/"]]\n'
        )
    return texte


def _executor(
    pyproject: str | None = None,
    *,
    fetch_url: str = _FORGEJO,
    push_url: str = _FORGEJO,
) -> ScriptedExecutor:
    """Scénario nominal : tout est sain, pin à monter de v2.10.0."""
    ex = ScriptedExecutor()
    ex.on(
        "git", "remote", "get-url", "--all", "origin", stdout=fetch_url + "\n"
    )
    ex.on(
        "git",
        "remote",
        "get-url",
        "--push",
        "--all",
        stdout=push_url + "\n",
    )
    ex.on(
        "git",
        "ls-remote",
        "--symref",
        stdout="ref: refs/heads/main\tHEAD\nabc123\tHEAD\n",
    )
    ex.on("git", "rev-parse", "--verify", rc=1)
    ex.on("git", "ls-remote", "--heads", stdout="")
    ex.on(
        "git",
        "show",
        "origin/main:pyproject.toml",
        stdout=pyproject or _pyproject(),
    )
    ex.on("git", "ls-tree", stdout="")
    ex.on("git", "show", "origin/main:CHANGELOG.md", rc=128)
    return ex


def _bumper(
    ex: ScriptedExecutor,
    tmp_path: Path,
    *,
    dry_run: bool = True,
    tag: str = "v2.11.1",
) -> ConsumerBumper:
    return ConsumerBumper(
        ex,
        MagicMock(),
        tag=tag,
        root=tmp_path,
        dry_run=dry_run,
        push=True,
        co_author=_CO_AUTHOR,
    )


def _bumper_avec_logger(
    ex: ScriptedExecutor, tmp_path: Path, logger: MagicMock
) -> ConsumerBumper:
    return ConsumerBumper(
        ex,
        logger,
        tag="v2.11.1",
        root=tmp_path,
        dry_run=True,
        push=True,
        co_author=_CO_AUTHOR,
    )


def _bump(ex: ScriptedExecutor, tmp_path: Path) -> BumpOutcome:
    bumper = _bumper(ex, tmp_path)
    return bumper.bump(Consumer("app", tmp_path / "app"))


@pytest.mark.parametrize(
    ("fetch_url", "push_url"),
    [
        ("https://github.com/fred/app.git", _FORGEJO),
        (_FORGEJO, "git@github.com:fred/app.git"),
        ("https://git.ricfasohel.fr@github.com/fred/app.git", _FORGEJO),
        ("https://evil.example/git.ricfasohel.fr/app.git", _FORGEJO),
        ("https://git.ricfasohel.fr.evil.example/app.git", _FORGEJO),
    ],
)
def test_origin_github_refuse(
    tmp_path: Path, fetch_url: str, push_url: str
) -> None:
    ex = _executor(fetch_url=fetch_url, push_url=push_url)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert "git.ricfasohel.fr" in outcome.detail
    assert not any(a[:2] == ("git", "show") for a in ex.argvs())


@pytest.mark.parametrize(
    "url",
    [
        _FORGEJO,
        "git@git.ricfasohel.fr:fred/app.git",
        "ssh://git@git.ricfasohel.fr:2222/fred/app.git",
        "git@git.ricfasohel.fr:/srv/git/app.git",
        "git.ricfasohel.fr:a:b.git",
        "https://user:pw@GIT.ricfasohel.fr/fred/app.git",
    ],
)
def test_origin_forgejo_accepte_les_formes_usuelles(
    tmp_path: Path, url: str
) -> None:
    outcome = _bump(_executor(fetch_url=url, push_url=url), tmp_path)

    assert outcome.status is Status.SIMULE


@pytest.mark.parametrize(
    "url",
    [
        # git contacte github.com : tout ce qui suit `#` ou `?` est ignoré
        "https://github.com#@git.ricfasohel.fr/fred/app.git",
        "https://github.com?@git.ricfasohel.fr/fred/app.git",
        "https://github.com\\@git.ricfasohel.fr/fred/app.git",
        "http://git.ricfasohel.fr/fred/app.git",
        "file://git.ricfasohel.fr/fred/app.git",
        "git.ricfasohel.fr/fred/app.git",
        "git.ricfasohel.fr:fred/app.git\nautre",
        # `hôte::adresse` : helper de transport git (`<helper>::<adresse>`)
        "git.ricfasohel.fr::fred/app.git",
        "git@git.ricfasohel.fr::fred/app.git",
        "git.ricfasohel.fr::",
        # `hôte://…` : forme schéma sans schéma reconnu
        "git.ricfasohel.fr://fred/app.git",
        "git@git.ricfasohel.fr://fred/app.git",
    ],
)
def test_origin_forme_trompeuse_refusee(tmp_path: Path, url: str) -> None:
    ex = _executor(fetch_url=url, push_url=_FORGEJO)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert not any(a[:2] == ("git", "show") for a in ex.argvs())


@pytest.mark.parametrize("push", [False, True])
def test_deuxieme_url_github_d_origin_refusee(
    tmp_path: Path, push: bool
) -> None:
    """Une 2e `url`/`pushurl` miroir échappe à `get-url` sans `--all`."""
    miroir = "git@github.com:fred/app.git"
    doublon = f"{_FORGEJO}\n{miroir}"
    ex = _executor(
        fetch_url=doublon if not push else _FORGEJO,
        push_url=doublon if push else _FORGEJO,
    )

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert not any(a[:2] == ("git", "show") for a in ex.argvs())


def test_urls_multiples_toutes_forgejo_acceptees(tmp_path: Path) -> None:
    deux = f"{_FORGEJO}\ngit@git.ricfasohel.fr:fred/app.git"

    outcome = _bump(_executor(fetch_url=deux, push_url=deux), tmp_path)

    assert outcome.status is Status.SIMULE


def test_jeton_de_l_origin_absent_du_detail_et_du_journal(
    tmp_path: Path,
) -> None:
    url = "https://tok:s3cret@github.com/fred/app.git"
    ex = _executor(fetch_url=url, push_url=url)
    logger = MagicMock()
    bumper = ConsumerBumper(
        ex,
        logger,
        tag="v2.11.1",
        root=tmp_path,
        dry_run=True,
        push=True,
        co_author=_CO_AUTHOR,
    )

    outcome = bumper.bump(Consumer("app", tmp_path / "app"))

    assert outcome.status is Status.REFUSE
    assert "s3cret" not in outcome.detail
    assert "s3cret" not in str(logger.mock_calls)


def test_pin_deja_a_jour(tmp_path: Path) -> None:
    ex = _executor(_pyproject("v2.11.1"))

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.A_JOUR
    assert outcome.old_pin == "v2.11.1"


def test_retrogradation_refusee(tmp_path: Path) -> None:
    ex = _executor(_pyproject("v2.12.0"))

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert "v2.12.0" in outcome.detail
    assert "v2.11.1" in outcome.detail


def test_contrat_absent_refuse(tmp_path: Path) -> None:
    ex = _executor(_pyproject(contrat=False))

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert "contrat consommateur" in outcome.detail
    assert outcome.old_pin == "?"


def test_dependance_maison_en_conflit_bloque(tmp_path: Path) -> None:
    maison = (
        "webapitools @ git+https://git.ricfasohel.fr/fred/"
        "webapitools.git@v0.13.0"
    )
    ex = _executor(_pyproject(extra_deps=(maison,)))
    ex.on(
        "git",
        "-C",
        str(tmp_path / "webapitools"),
        "show",
        "v0.13.0:pyproject.toml",
        stdout=f'[project]\nname="w"\ndependencies=["{_pin("v2.10.0")}"]\n',
    )

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.BLOQUE
    assert "webapitools" in outcome.detail


def test_dependance_maison_alignee_ne_bloque_pas(tmp_path: Path) -> None:
    maison = (
        "webapitools @ git+https://git.ricfasohel.fr/fred/"
        "webapitools.git@v0.14.0"
    )
    ex = _executor(_pyproject(extra_deps=(maison,)))
    ex.on(
        "git",
        "-C",
        str(tmp_path / "webapitools"),
        "show",
        "v0.14.0:pyproject.toml",
        stdout=f'[project]\nname="w"\ndependencies=["{_pin("v2.11.1")}"]\n',
    )

    assert _bump(ex, tmp_path).status is Status.SIMULE


@pytest.mark.parametrize(
    ("sortie", "rc", "motif"),
    [
        ("", 128, "introuvable"),
        ("[project\n", 0, "illisible"),
    ],
)
def test_dependance_maison_illisible_ou_absente_refusee(
    tmp_path: Path, sortie: str, rc: int, motif: str
) -> None:
    maison = (
        "webapitools @ git+https://git.ricfasohel.fr/fred/"
        "webapitools.git@v0.13.0"
    )
    ex = _executor(_pyproject(extra_deps=(maison,)))
    ex.on("git", "-C", stdout=sortie, rc=rc, stderr="fatal: pas de tag")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert "webapitools" in outcome.detail
    assert "v0.13.0" in outcome.detail
    assert motif in outcome.detail


@pytest.mark.parametrize(
    "maison",
    [
        "x @ git+https://git.ricfasohel.fr/fred/a/../b.git@v1.0.0",
        "x @ git+https://git.ricfasohel.fr/fred/x.git@--output=/etc/p",
    ],
)
def test_dependance_maison_suspecte_refusee(
    tmp_path: Path, maison: str
) -> None:
    ex = _executor(_pyproject(extra_deps=(maison,)))

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert not any(a[:2] == ("git", "-C") for a in ex.argvs())


_SHA_DISTANT = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


def _branche_distante(
    ex: ScriptedExecutor,
    *,
    objet: bool = True,
    pin: str = "v2.11.1",
    fichiers: str = "pyproject.toml\n",
    pyproject: str | None = None,
    parents: int = 1,
    sha: str = _SHA_DISTANT,
) -> None:
    """Déclare une branche de bump déjà poussée sur origin.

    ``fichiers`` est la sortie de ``git diff --name-only origin/main...sha`` :
    toute la branche, pas seulement son sommet.
    """
    ex.on(
        "git",
        "ls-remote",
        "--heads",
        "origin",
        f"refs/heads/{_BRANCHE}",
        stdout=f"{sha}\trefs/heads/{_BRANCHE}\n",
    )
    ex.on("git", "fetch")
    ex.on("git", "cat-file", "-e", rc=0 if objet else 1)
    ex.on(
        "git",
        "show",
        f"{sha}:pyproject.toml",
        stdout=pyproject or _pyproject(pin),
    )
    ex.on(
        "git",
        "rev-list",
        "--parents",
        "-n1",
        sha,
        stdout=" ".join([sha, *["a" * 40] * parents]) + "\n",
    )
    ex.on(
        "git", "diff", "--name-only", f"origin/main...{sha}", stdout=fichiers
    )


def test_branche_poussee_avec_commit_de_bump_valide_en_attente(
    tmp_path: Path,
) -> None:
    ex = _executor()
    _branche_distante(ex)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.EN_ATTENTE


def test_branche_poussee_dry_run_objet_absent_non_verifie(
    tmp_path: Path,
) -> None:
    ex = _executor()
    _branche_distante(ex, objet=False)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.EN_ATTENTE
    assert "non vérifié" in outcome.detail
    assert not any(a[:2] == ("git", "fetch") for a in ex.argvs())


def test_branche_poussee_reel_fetch_la_branche_puis_verifie(
    tmp_path: Path,
) -> None:
    ex = _executor()
    _branche_distante(ex)
    bumper = _bumper(ex, tmp_path, dry_run=False)

    outcome = bumper.bump(Consumer("app", tmp_path / "app"))

    assert outcome.status is Status.EN_ATTENTE
    assert "non vérifié" not in outcome.detail
    assert (
        "git",
        "fetch",
        "--no-tags",
        "origin",
        f"refs/heads/{_BRANCHE}",
    ) in ex.argvs()


def test_branche_poussee_reel_objet_introuvable_refusee(
    tmp_path: Path,
) -> None:
    ex = _executor()
    _branche_distante(ex, objet=False)
    bumper = _bumper(ex, tmp_path, dry_run=False)

    outcome = bumper.bump(Consumer("app", tmp_path / "app"))

    assert outcome.status is Status.REFUSE
    assert _BRANCHE in outcome.detail


def test_branche_poussee_avec_autre_pin_refusee(tmp_path: Path) -> None:
    ex = _executor()
    _branche_distante(ex, pin="v2.10.0")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert "v2.11.1" in outcome.detail
    assert _BRANCHE in outcome.detail


def test_branche_poussee_avec_fichier_inattendu_refusee(
    tmp_path: Path,
) -> None:
    ex = _executor()
    _branche_distante(ex, fichiers="pyproject.toml\nsrc/evil.py\n")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert "src/evil.py" in outcome.detail


def test_branche_poussee_commit_dessous_hors_perimetre_refusee(
    tmp_path: Path,
) -> None:
    """Le diff couvre toute la branche : un commit sous le sommet compte."""
    ex = _executor()
    _branche_distante(ex, fichiers="pyproject.toml\nsrc/cache/evil.py\n")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert "src/cache/evil.py" in outcome.detail
    assert ("git", "diff", "--name-only", f"origin/main...{_SHA_DISTANT}") in (
        ex.argvs()
    )


def test_branche_poussee_sans_changement_refusee(tmp_path: Path) -> None:
    ex = _executor()
    _branche_distante(ex, fichiers="")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE


@pytest.mark.parametrize("parents", [0, 2, 3])
def test_branche_poussee_fusion_refusee(tmp_path: Path, parents: int) -> None:
    """Fusion ou racine (diff-tree vide) : pas un commit de bump."""
    ex = _executor()
    _branche_distante(ex, parents=parents)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert "fusion" in outcome.detail


@pytest.mark.parametrize(
    "sha",
    [
        "--output=/tmp/x",
        "HEAD",
        "deadbeef",
        "g" * 40,
        "A" * 40,
        "a" * 39,
        "a" * 41,
    ],
)
def test_branche_poussee_sha_non_hexadecimal_refuse(
    tmp_path: Path, sha: str
) -> None:
    ex = _executor()
    _branche_distante(ex, sha=sha)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    # le SHA douteux n'atteint jamais une commande git de lecture d'objet
    lecture = {"cat-file", "show", "diff", "rev-list", "fetch"}
    assert not any(sha in " ".join(a) for a in ex.argvs() if a[1] in lecture)


@pytest.mark.parametrize("sha", ["a" * 40, "0123456789abcdef" * 4])
def test_branche_poussee_sha_complet_accepte(tmp_path: Path, sha: str) -> None:
    ex = _executor()
    _branche_distante(ex, sha=sha)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.EN_ATTENTE


def test_branche_poussee_avec_pyproject_illisible_refusee(
    tmp_path: Path,
) -> None:
    ex = _executor()
    _branche_distante(ex, pyproject="[project\n")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert _BRANCHE in outcome.detail


def test_branche_locale_existante_refusee(tmp_path: Path) -> None:
    ex = _executor()
    ex.on("git", "rev-parse", "--verify", "--quiet", rc=0, stdout="abc\n")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE
    assert _BRANCHE in outcome.detail


def test_dry_run_n_ecrit_rien_et_ne_fetch_pas(tmp_path: Path) -> None:
    ex = _executor()
    ex.on(
        "git",
        "ls-tree",
        "--name-only",
        "origin/main",
        "uv.lock",
        stdout="uv.lock\n",
    )
    ex.on(
        "git",
        "ls-tree",
        "--name-only",
        "origin/main",
        "CHANGELOG.md",
        stdout="CHANGELOG.md\n",
    )
    ex.on(
        "git", "show", "origin/main:CHANGELOG.md", stdout="## [Non publié]\n"
    )

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.SIMULE
    assert ex.calls
    assert all(c.probe for c in ex.calls)
    assert not any(a[:2] == ("git", "fetch") for a in ex.argvs())
    assert _BRANCHE in outcome.detail
    assert "v2.10.0" in outcome.detail
    assert "v2.11.1" in outcome.detail
    assert "uv.lock" in outcome.detail
    assert "CHANGELOG" in outcome.detail
    assert list(tmp_path.iterdir()) == []


def test_dry_run_signale_l_origin_local_non_rafraichi(
    tmp_path: Path,
) -> None:
    outcome = _bump(_executor(), tmp_path)

    assert outcome.status is Status.SIMULE
    assert "origin/main local non rafraîchi" in outcome.detail


def test_dry_run_sans_lock_ni_changelog_le_dit(tmp_path: Path) -> None:
    outcome = _bump(_executor(), tmp_path)

    assert "uv.lock" not in outcome.detail
    assert "CHANGELOG" not in outcome.detail


def test_changelog_suivi_sans_section_non_publie_ignore(
    tmp_path: Path,
) -> None:
    ex = _executor()
    ex.on(
        "git",
        "ls-tree",
        "--name-only",
        "origin/main",
        "CHANGELOG.md",
        stdout="CHANGELOG.md\n",
    )
    ex.on("git", "show", "origin/main:CHANGELOG.md", stdout="# Changelog\n")

    outcome = _bump(ex, tmp_path)

    assert "CHANGELOG" not in outcome.detail


def test_echec_d_une_sonde_donne_echec_avec_stderr(tmp_path: Path) -> None:
    ex = _executor()
    ex.on("git", "remote", "get-url", "--all", rc=2, stderr="boum\n")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.ECHEC
    assert "boum" in outcome.detail


def test_echec_lecture_pyproject_origin(tmp_path: Path) -> None:
    ex = _executor()
    ex.on("git", "show", "origin/main:pyproject.toml", rc=128, stderr="absent")

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.ECHEC
    assert "absent" in outcome.detail


@pytest.mark.parametrize(
    "sortie",
    [
        "",
        "garbage\n",
        "ref: refs/heads/-x\tHEAD\n",
        "ref: refs/heads/a b\tHEAD\n",
    ],
)
def test_branche_par_defaut_illisible_refusee(
    tmp_path: Path, sortie: str
) -> None:
    ex = _executor()
    ex.on("git", "ls-remote", "--symref", stdout=sortie)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.REFUSE


def test_exception_inattendue_convertie_en_echec(tmp_path: Path) -> None:
    ex = _executor()

    def boom(call: object) -> None:
        raise OSError("disque")

    ex.on("git", "show", "origin/main:pyproject.toml", handler=boom)

    outcome = _bump(ex, tmp_path)

    assert outcome.status is Status.ECHEC
    assert "disque" in outcome.detail


def test_jeton_ssh_masque_dans_detail_et_journal_du_refus(
    tmp_path: Path,
) -> None:
    url = "ssh://git:jetonssh@github.com/fred/app.git"
    logger = MagicMock()
    bumper = _bumper_avec_logger(_executor(fetch_url=url), tmp_path, logger)

    outcome = bumper.bump(Consumer("app", tmp_path / "app"))

    assert outcome.status is Status.REFUSE
    assert "jetonssh" not in outcome.detail
    assert "jetonssh" not in str(logger.mock_calls)
    assert "ssh://***@github.com" in outcome.detail


def test_jeton_masque_sur_le_chemin_d_exception_generique(
    tmp_path: Path,
) -> None:
    ex = _executor()

    def boom(call: object) -> None:
        raise OSError("échec sur https://tok:s3cret@github.com/fred/app.git")

    ex.on("git", "show", "origin/main:pyproject.toml", handler=boom)
    logger = MagicMock()
    bumper = _bumper_avec_logger(ex, tmp_path, logger)

    outcome = bumper.bump(Consumer("app", tmp_path / "app"))

    assert outcome.status is Status.ECHEC
    assert "s3cret" not in outcome.detail
    assert "https://***@github.com" in outcome.detail
    logger.log_error.assert_called_once()
    journal = str(logger.log_error.call_args)
    assert "s3cret" not in journal
    assert "https://***@github.com" in journal


@pytest.mark.parametrize(
    "tag", ["v2.11", "2.11.1", "v2.11.1; rm", "v2.11.1\n"]
)
def test_tag_invalide_refuse_a_la_construction(
    tmp_path: Path, tag: str
) -> None:
    with pytest.raises(ValueError, match="tag"):
        _bumper(ScriptedExecutor(), tmp_path, tag=tag)


@pytest.mark.parametrize(
    "co_author",
    [
        "x\ny <a@b.c>",
        "sans-adresse",
        "<a@b.c>",
        "X <a b@c.d>",
        "X <a@b.c>\n",
    ],
)
def test_co_author_invalide_refuse_a_la_construction(
    tmp_path: Path, co_author: str
) -> None:
    with pytest.raises(ValueError, match="co-auteur"):
        ConsumerBumper(
            ScriptedExecutor(),
            MagicMock(),
            tag="v2.11.1",
            root=tmp_path,
            dry_run=True,
            push=True,
            co_author=co_author,
        )
