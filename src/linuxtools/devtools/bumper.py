"""Montée du pin linuxtools dans un projet consommateur.

``ConsumerBumper.bump`` ne lève jamais d'exception métier : tout est
converti en ``BumpOutcome`` (statut + détail).
"""

# stdlib
import re
import shutil
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

# local
from linuxtools.commands.base import CommandExecutor, CommandResult
from linuxtools.devtools.changelog import add_modified_entry
from linuxtools.devtools.discovery import Consumer
from linuxtools.devtools.lockfile import unexpected_lock_changes
from linuxtools.devtools.manifest import (
    ConsumerManifest,
    ManifestError,
    SiblingDep,
    pinned_linuxtools_tags,
    rewrite_pin,
)
from linuxtools.devtools.report import BumpOutcome, Status, mask_userinfo
from linuxtools.logging.base import Logger
from linuxtools.updates.version_compare import parse_version

FORGEJO_HOST = "git.ricfasohel.fr"
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+\Z")
CO_AUTHOR_RE = re.compile(r"^[^<>\n]+ <[^<>\s]+@[^<>\s]+>\Z")

# Liste blanche des formes d'URL d'origin, lues comme git les lit : le
# userinfo ne contient ni `/`, `?`, `#`, `@` ni `\` (git ignore ce qui
# suit `#` ou `?`, donc `https://a#@b/` contacte `a`, pas `b`).
_HOST_RES = (
    re.compile(
        r"^(?:https|ssh)://(?:[^/?#@\\\s]*@)?"
        r"(?P<host>[^/?#@:\\\s]+)(?::\d+)?/\S*\Z"
    ),
    re.compile(r"^(?:[^/?#@:\\\s]+@)?(?P<host>[^/?#@:\\\s]+):(?!//)\S+\Z"),
)
_DEFAULT_BRANCH_RE = re.compile(
    r"^ref:\s+refs/heads/(?P<branch>\S+)\s+HEAD\s*$", re.MULTILINE
)
_SAFE_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_UNRELEASED = "## [Non publié]"
_BUMP_FILES = frozenset({"pyproject.toml", "CHANGELOG.md", "uv.lock"})


class _AbortError(Exception):
    """Arrêt de la montée avec un statut (interne à ce module)."""

    def __init__(
        self, status: Status, detail: str, *, checks: str = ""
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.checks = checks


@dataclass
class _State:
    """État partagé entre les étapes d'une montée."""

    old_pin: str = "?"


@dataclass(frozen=True)
class _Workspace:
    """Espace de travail jetable d'une montée réelle."""

    tmp: Path
    worktree: Path
    env: dict[str, str]


@dataclass(frozen=True)
class _Plan:
    """Ce que la montée d'un consommateur va faire."""

    default_branch: str
    branch: str
    manifest: ConsumerManifest
    lock_tracked: bool
    changelog: bool


def _output(result: CommandResult) -> str:
    """Sortie combinée (stdout puis stderr) d'une commande."""
    return "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )


def url_host(url: str) -> str:
    """Extrait le nom d'hôte d'une URL git (https, ssh ou scp).

    Retourne une chaîne vide si la forme n'est pas dans la liste blanche.
    """
    for pattern in _HOST_RES:
        match = pattern.match(url.strip())
        if match:
            return match.group("host").lower()
    return ""


class ConsumerBumper:
    """Monte le pin linuxtools d'un consommateur sur une branche dédiée.

    Les sondes (lecture seule) s'exécutent aussi en dry-run ; seul le
    chemin réel écrit, commit et pousse.
    """

    def __init__(
        self,
        executor: CommandExecutor,
        logger: Logger,
        *,
        tag: str,
        root: Path,
        dry_run: bool,
        push: bool,
        co_author: str,
        timeout: float = 600.0,
    ) -> None:
        """Initialise le bumper.

        Args:
            executor: Exécuteur de commandes (injecté).
            logger: Logger (injecté).
            tag: Tag cible ``vX.Y.Z``.
            root: Dossier contenant les dépôts frères.
            dry_run: Simuler sans écrire ni fetch.
            push: Pousser la branche vers ``origin``.
            co_author: Trailer ``Nom <adresse>`` du commit.
            timeout: Délai par commande, en secondes.

        Raises:
            ValueError: Tag ou co-auteur invalide.
        """
        if not TAG_RE.match(tag):
            raise ValueError(f"tag invalide : {tag!r}")
        if not CO_AUTHOR_RE.match(co_author):
            raise ValueError(f"co-auteur invalide : {co_author!r}")
        self._executor = executor
        self._logger = logger
        self._tag = tag
        self._root = root
        self._dry_run = dry_run
        self._push = push
        self._co_author = co_author
        self._timeout = int(timeout)
        self._branch = "chore/pin-linuxtools-" + tag[1:].replace(".", "-")

    def bump(self, consumer: Consumer) -> BumpOutcome:
        """Monte le pin d'un consommateur.

        Args:
            consumer: Consommateur à traiter.

        Returns:
            Résultat de la montée ; jamais d'exception métier.
        """
        state = _State()
        try:
            return self._bump(consumer, state)
        except _AbortError as stop:
            detail = mask_userinfo(stop.detail)
            self._logger.log_warning(
                f"{consumer.name} : {stop.status.value} : {detail}"
            )
            return BumpOutcome(
                consumer.name,
                state.old_pin,
                stop.status,
                checks=stop.checks,
                detail=detail,
            )
        except Exception as exc:  # frontière : tout devient un statut
            self._logger.log_error(mask_userinfo(f"{consumer.name} : {exc!r}"))
            return BumpOutcome(
                consumer.name,
                state.old_pin,
                Status.ECHEC,
                detail=mask_userinfo(f"{type(exc).__name__} : {exc}"),
            )

    # -- orchestration -------------------------------------------------

    def _bump(self, consumer: Consumer, state: _State) -> BumpOutcome:
        """Déroule sondes puis exécution (ou simulation)."""
        cwd = str(consumer.path)
        default = self._probe_origin(cwd)
        if not self._dry_run:
            self._fetch(cwd, default)
        manifest = self._read_manifest(cwd, default)
        state.old_pin = manifest.tag
        old, new = parse_version(manifest.tag), parse_version(self._tag)
        if old == new:
            return BumpOutcome(consumer.name, manifest.tag, Status.A_JOUR)
        if old is not None and new is not None and old > new:
            raise _AbortError(
                Status.REFUSE,
                f"rétrogradation refusée : pin {manifest.tag} > {self._tag}",
            )
        self._check_branch(cwd)
        plan = _Plan(
            default_branch=default,
            branch=self._branch,
            manifest=manifest,
            lock_tracked=self._tracked(cwd, default, "uv.lock"),
            changelog=self._has_unreleased(cwd, default),
        )
        self._check_siblings(manifest)
        if self._dry_run:
            return BumpOutcome(
                consumer.name,
                manifest.tag,
                Status.SIMULE,
                detail=self._describe(plan),
            )
        return self._apply(consumer, plan)

    def _apply(self, consumer: Consumer, plan: _Plan) -> BumpOutcome:
        """Chemin réel : worktree jetable, contrôles, commit, push.

        Le checkout de l'utilisateur n'est jamais modifié. En cas
        d'échec avant le commit abouti, la branche locale est supprimée.
        """
        tmp = Path(tempfile.mkdtemp(prefix="linuxtools-bump-"))  # 0700
        venv = tmp / "venv"
        space = _Workspace(
            tmp=tmp,
            worktree=tmp / "wt",
            env={
                "UV_PROJECT_ENVIRONMENT": str(venv),
                "VIRTUAL_ENV": str(venv),
                "UV_NO_SOURCES": "1",
            },
        )
        cwd = str(consumer.path)
        worktree = False
        drop = False
        try:
            self._add_worktree(cwd, plan, space)
            worktree = drop = True
            checks = self._prepare_and_check(plan, space)
            outcome = self._commit_and_push(consumer, plan, space, checks)
            drop = False
            return outcome
        except _AbortError as stop:
            drop = drop and stop.status is not Status.PUSH_ECHOUE
            raise
        finally:
            self._cleanup(cwd, space, plan.branch, worktree, drop)

    def _add_worktree(self, cwd: str, plan: _Plan, space: _Workspace) -> None:
        """Crée la branche et son worktree.

        ``worktree add -b`` peut créer la branche puis échouer au
        checkout : la branche n'existait pas avant (``_check_branch``),
        elle est donc à nous et on la supprime au nettoyage.
        """
        argv = [
            "git",
            "worktree",
            "add",
            "--no-track",
            "-b",
            plan.branch,
            str(space.worktree),
            f"origin/{plan.default_branch}",
        ]
        result = self._executor.run(argv, cwd=cwd, timeout=self._timeout)
        if not result.success:
            if self._branch_exists(cwd, plan.branch):
                self._delete_branch(cwd, plan.branch)
            raise _AbortError(
                Status.ECHEC,
                f"git worktree add a échoué "
                f"(code {result.return_code}) :\n{_output(result)}",
            )

    def _branch_exists(self, cwd: str, branch: str) -> bool:
        """Indique si la branche locale existe (sonde)."""
        ref = f"refs/heads/{branch}"
        return self._git(
            ["rev-parse", "--verify", "--quiet", ref], cwd, check=False
        ).success

    def _cleanup(
        self,
        cwd: str,
        space: _Workspace,
        branch: str,
        worktree: bool,
        drop_branch: bool,
    ) -> None:
        """Supprime worktree, dossier temporaire et branche si échec.

        Un échec de nettoyage est journalisé, jamais ignoré.
        """
        if worktree:
            self._cleanup_step(
                ["git", "worktree", "remove", "--force", str(space.worktree)],
                cwd,
            )
        shutil.rmtree(space.tmp, ignore_errors=True)
        if drop_branch:
            self._delete_branch(cwd, branch)

    def _delete_branch(self, cwd: str, branch: str) -> None:
        """Supprime la branche locale (échec journalisé)."""
        self._cleanup_step(["git", "branch", "-D", branch], cwd)

    def _cleanup_step(self, argv: list[str], cwd: str) -> None:
        """Lance une commande de nettoyage et journalise son échec."""
        result = self._executor.run(argv, cwd=cwd, timeout=self._timeout)
        if not result.success:
            self._logger.log_warning(
                f"nettoyage : {' '.join(argv[:3])} a échoué "
                f"(code {result.return_code}) : {_output(result)}"
            )

    def _step(
        self,
        argv: list[str],
        cwd: str,
        *,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> CommandResult:
        """Lance une commande qui écrit ; ``ECHEC`` si elle échoue."""
        result = self._executor.run(
            argv, env=env, cwd=cwd, timeout=self._timeout, stdin=stdin
        )
        if not result.success:
            raise _AbortError(
                Status.ECHEC,
                f"{' '.join(argv[:3])} a échoué "
                f"(code {result.return_code}) :\n{_output(result)}",
            )
        return result

    def _prepare_and_check(self, plan: _Plan, space: _Workspace) -> str:
        """Édite, verrouille, synchronise puis lance les contrôles."""
        wt = space.worktree
        cwd = str(wt)
        manifest = plan.manifest
        pyproject = wt / "pyproject.toml"
        pyproject.write_bytes(
            rewrite_pin(
                pyproject.read_bytes().decode("utf-8"), self._tag
            ).encode("utf-8")
        )
        if plan.changelog:
            changelog = wt / "CHANGELOG.md"
            entry = (
                f"chore(deps): `linuxtools` épinglée en {self._tag} "
                f"(était {manifest.tag})"
            )
            changelog.write_bytes(
                add_modified_entry(
                    changelog.read_bytes().decode("utf-8"), entry
                ).encode("utf-8")
            )
        if plan.lock_tracked:
            self._relock(wt, space.env)
        sync = ["uv", "sync", "--no-sources"]
        if plan.lock_tracked:
            sync.append("--locked")
        self._step([*sync, *manifest.sync_args], cwd, env=space.env)
        venv_bin = space.tmp / "venv" / "bin"
        done: list[str] = []
        for check in manifest.checks:
            result = self._executor.run(
                [str(venv_bin / check[0]), *check[1:]],
                env=space.env,
                cwd=cwd,
                timeout=self._timeout,
            )
            if not result.success:
                done.append(f"{check[0]}:KO")
                raise _AbortError(
                    Status.ECHEC,
                    f"contrôle {' '.join(check)} en échec "
                    f"(code {result.return_code}) :\n{_output(result)}",
                    checks=" ".join(done),
                )
            done.append(f"{check[0]}:ok")
        return " ".join(done)

    def _relock(self, wt: Path, env: dict[str, str]) -> None:
        """Régénère ``uv.lock`` et refuse les changements hors linuxtools."""
        lock = wt / "uv.lock"
        old = lock.read_text(encoding="utf-8")
        self._step(["uv", "lock", "--no-sources"], str(wt), env=env)
        new = lock.read_text(encoding="utf-8")
        unexpected = unexpected_lock_changes(old, new)
        if unexpected:
            raise _AbortError(
                Status.ECHEC,
                "uv.lock modifié hors de linuxtools : "
                + ", ".join(unexpected),
            )
        if tomllib.loads(old).get("revision") != tomllib.loads(new).get(
            "revision"
        ):
            self._logger.log_warning(
                "en-tête revision d'uv.lock modifié (uv local différent)"
            )

    def _commit_and_push(
        self,
        consumer: Consumer,
        plan: _Plan,
        space: _Workspace,
        checks: str,
    ) -> BumpOutcome:
        """Commit (hooks actifs), contrôle du contenu, push vérifié."""
        cwd = str(space.worktree)
        files = ["pyproject.toml"]
        if plan.changelog:
            files.append("CHANGELOG.md")
        if plan.lock_tracked:
            files.append("uv.lock")
        self._step(["git", "add", "--", *files], cwd)
        message = (
            f"chore(deps): épingler linuxtools en {self._tag}\n\n"
            f"Co-Authored-By: {self._co_author}\n"
        )
        self._step(
            ["git", "commit", "-F", "-"],
            cwd,
            env={**space.env, "UV_FROZEN": "1"},
            stdin=message,
        )
        touched = set(
            self._step(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r"]
                + ["HEAD"],
                cwd,
            ).stdout.split()
        )
        extra = touched - set(files)
        if extra:
            raise _AbortError(
                Status.ECHEC,
                "le commit touche des fichiers inattendus : "
                + ", ".join(sorted(extra))
                + " (le hook post-commit a pu pousser la branche)",
                checks=checks,
            )
        if not self._push:
            return BumpOutcome(
                consumer.name,
                plan.manifest.tag,
                Status.COMMITE,
                checks=checks,
            )
        head = self._step(["git", "rev-parse", "HEAD"], cwd).stdout.strip()
        return self._push_branch(consumer, plan, cwd, head, checks)

    def _push_branch(
        self,
        consumer: Consumer,
        plan: _Plan,
        cwd: str,
        head: str,
        checks: str,
    ) -> BumpOutcome:
        """Pousse la branche et vérifie son SHA sur ``origin``."""
        ref = f"refs/heads/{plan.branch}"
        pushed = self._executor.run(
            ["git", "push", "origin", f"{ref}:{ref}"],
            cwd=cwd,
            timeout=self._timeout,
        )
        remote = self._executor.run(
            ["git", "ls-remote", "origin", ref],
            cwd=cwd,
            timeout=self._timeout,
            probe=True,
        )
        remote_sha = remote.stdout.split()[:1]
        if remote.success and remote_sha == [head]:
            return BumpOutcome(
                consumer.name, plan.manifest.tag, Status.POUSSE, checks=checks
            )
        raise _AbortError(
            Status.PUSH_ECHOUE,
            f"push non vérifié sur origin (branche {plan.branch} "
            f"conservée) :\n{_output(pushed)}",
            checks=checks,
        )

    # -- exécution -----------------------------------------------------

    def _git(
        self, args: list[str], cwd: str | None, *, check: bool = True
    ) -> CommandResult:
        """Lance une sonde git (lecture seule, même en dry-run)."""
        result = self._executor.run(
            ["git", *args], cwd=cwd, timeout=self._timeout, probe=True
        )
        if check and not result.success:
            raise _AbortError(
                Status.ECHEC,
                f"git {' '.join(args[:3])} a échoué "
                f"(code {result.return_code}) : {result.stderr.strip()}",
            )
        return result

    # -- sondes --------------------------------------------------------

    def _probe_origin(self, cwd: str) -> str:
        """Vérifie les URL d'origin et retourne la branche par défaut."""
        for args in (
            ["remote", "get-url", "origin"],
            ["remote", "get-url", "--push", "origin"],
        ):
            url = self._git(args, cwd).stdout.strip()
            if url_host(url) != FORGEJO_HOST:
                raise _AbortError(
                    Status.REFUSE,
                    f"origin ({url}) n'est pas sur {FORGEJO_HOST}",
                )
        out = self._git(["ls-remote", "--symref", "origin", "HEAD"], cwd)
        match = _DEFAULT_BRANCH_RE.search(out.stdout)
        if match is None or not _SAFE_BRANCH_RE.match(match["branch"]):
            raise _AbortError(
                Status.REFUSE, "branche par défaut d'origin illisible"
            )
        return match["branch"]

    def _fetch(self, cwd: str, default: str) -> None:
        """Met à jour ``origin/<défaut>`` (chemin réel seulement)."""
        self._step(["git", "fetch", "--no-tags", "origin", default], cwd)

    def _read_manifest(self, cwd: str, default: str) -> ConsumerManifest:
        """Lit et analyse le pyproject de ``origin/<défaut>``."""
        out = self._git(["show", f"origin/{default}:pyproject.toml"], cwd)
        try:
            return ConsumerManifest.parse(out.stdout)
        except ManifestError as exc:
            raise _AbortError(Status.REFUSE, str(exc)) from exc

    def _check_branch(self, cwd: str) -> None:
        """Refuse si la branche cible existe déjà (origin ou local).

        Une branche déjà poussée n'est « en attente » que si son
        sommet est un vrai commit de bump (cf. ``_verify_remote_bump``).
        """
        ref = f"refs/heads/{self._branch}"
        remote = self._git(["ls-remote", "--heads", "origin", ref], cwd)
        if remote.stdout.strip():
            self._verify_remote_bump(cwd, ref, remote.stdout.split()[0])
        local = self._git(
            ["rev-parse", "--verify", "--quiet", ref], cwd, check=False
        )
        if local.success:
            raise _AbortError(
                Status.REFUSE, f"la branche locale {self._branch} existe"
            )

    def _verify_remote_bump(self, cwd: str, ref: str, sha: str) -> None:
        """Statue sur une branche de bump déjà poussée sur origin.

        Lève ``EN_ATTENTE`` si son sommet pin le tag cible et ne
        touche que les fichiers attendus, ``REFUSE`` sinon. En dry-run
        (aucun fetch), un objet absent localement reste non vérifié.
        """
        name = self._branch
        if not self._dry_run:
            self._step(["git", "fetch", "--no-tags", "origin", ref], cwd)
        if not self._git(
            ["cat-file", "-e", f"{sha}^{{commit}}"], cwd, check=False
        ).success:
            if self._dry_run:
                raise _AbortError(
                    Status.EN_ATTENTE,
                    f"{name} est déjà poussée sur origin "
                    "(contenu non vérifié : dry-run, objet absent)",
                )
            raise _AbortError(
                Status.REFUSE,
                f"{name} existe sur origin mais son commit {sha[:12]} "
                "est introuvable",
            )
        shown = self._git(["show", f"{sha}:pyproject.toml"], cwd, check=False)
        try:
            tags = (
                pinned_linuxtools_tags(shown.stdout) if shown.success else ()
            )
        except ManifestError:
            tags = ()
        if tags != (self._tag,):
            raise _AbortError(
                Status.REFUSE,
                f"{name} existe sur origin mais ne pin pas {self._tag} "
                "(pyproject illisible ou autre version) : "
                "à examiner ou supprimer",
            )
        touched = set(
            self._git(
                ["diff-tree", "--no-commit-id", "--name-only", "-r", sha],
                cwd,
            ).stdout.split()
        )
        extra = touched - _BUMP_FILES
        if extra:
            raise _AbortError(
                Status.REFUSE,
                f"{name} existe sur origin mais son commit touche des "
                "fichiers inattendus : " + ", ".join(sorted(extra)),
            )
        raise _AbortError(
            Status.EN_ATTENTE, f"{name} est déjà poussée sur origin"
        )

    def _tracked(self, cwd: str, default: str, name: str) -> bool:
        """Indique si ``name`` est suivi sur ``origin/<défaut>``."""
        out = self._git(
            ["ls-tree", "--name-only", f"origin/{default}", name], cwd
        )
        return bool(out.stdout.strip())

    def _has_unreleased(self, cwd: str, default: str) -> bool:
        """CHANGELOG suivi avec une section ``[Non publié]``."""
        if not self._tracked(cwd, default, "CHANGELOG.md"):
            return False
        out = self._git(["show", f"origin/{default}:CHANGELOG.md"], cwd)
        return _UNRELEASED in out.stdout.splitlines()

    def _check_siblings(self, manifest: ConsumerManifest) -> None:
        """Bloque si une dépendance maison épingle une autre version."""
        for sibling in manifest.siblings:
            if self._sibling_conflicts(sibling):
                raise _AbortError(
                    Status.BLOQUE,
                    f"{sibling.name}@{sibling.tag} épingle une autre "
                    f"version de linuxtools que {self._tag}",
                )

    def _sibling_conflicts(self, sibling: SiblingDep) -> bool:
        """Lit le pyproject de la dépendance maison à son tag."""
        out = self._git(
            [
                "-C",
                str(self._root / sibling.repo),
                "show",
                f"{sibling.tag}:pyproject.toml",
            ],
            None,
            check=False,
        )
        where = f"{sibling.name}@{sibling.tag}"
        if not out.success:
            raise _AbortError(
                Status.REFUSE,
                f"dépendance maison {where} introuvable dans "
                f"{self._root / sibling.repo} (dépôt ou tag absent) : "
                f"{out.stderr.strip()}",
            )
        try:
            tags = pinned_linuxtools_tags(out.stdout)
        except ManifestError as exc:
            raise _AbortError(
                Status.REFUSE,
                f"dépendance maison {where} : pyproject illisible ({exc})",
            ) from exc
        return any(tag != self._tag for tag in tags)

    # -- simulation ----------------------------------------------------

    def _describe(self, plan: _Plan) -> str:
        """Plan d'exécution rendu en dry-run."""
        manifest = plan.manifest
        lines = [
            f"branche {plan.branch} depuis origin/{plan.default_branch}",
            f"basé sur origin/{plan.default_branch} local non rafraîchi "
            "(dry-run sans fetch : le réel peut différer)",
            f"pin linuxtools {manifest.tag} -> {self._tag}",
        ]
        if plan.changelog:
            lines.append("CHANGELOG.md : entrée « Modifié »")
        if plan.lock_tracked:
            lines.append("uv.lock : régénéré (uv lock --no-sources)")
        sync = " ".join(manifest.sync_args)
        lines.append(f"uv sync --no-sources {sync}".rstrip())
        lines.append(
            "contrôles : "
            + " ; ".join(" ".join(check) for check in manifest.checks)
        )
        lines.append("push : " + ("origin" if self._push else "désactivé"))
        return "\n".join(lines)
