"""Double de ``CommandExecutor`` qui rejoue des résultats par argv."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from linuxtools.commands.base import CommandExecutor, CommandResult


@dataclass(frozen=True)
class Call:
    """Appel enregistré par le double."""

    argv: tuple[str, ...]
    env: dict[str, str] | None
    cwd: str | None
    timeout: int | None
    probe: bool
    stdin: str | None


Handler = Callable[[Call], CommandResult | None]


class ScriptedExecutor(CommandExecutor):
    """Rejoue des ``CommandResult`` choisis par préfixe d'argv.

    La règle déclarée en dernier l'emporte, ce qui permet à un test de
    surcharger un scénario par défaut. Une commande sans règle fait
    échouer le test (``AssertionError``).
    """

    def __init__(self) -> None:
        self.calls: list[Call] = []
        self._rules: list[tuple[tuple[str, ...], CommandResult | Handler]] = []

    def on(
        self,
        *prefix: str,
        stdout: str = "",
        stderr: str = "",
        rc: int = 0,
        handler: Handler | None = None,
    ) -> ScriptedExecutor:
        """Déclare la réponse aux commandes commençant par ``prefix``.

        Un ``handler`` reçoit l'appel et peut produire des effets de
        bord ; s'il retourne None, le résultat ``rc/stdout/stderr``
        est utilisé.
        """
        result = CommandResult(prefix, rc, stdout, stderr, rc == 0, 0.0)
        if handler is None:
            self._rules.append((prefix, result))
        else:

            def wrapped(call: Call) -> CommandResult | None:
                return handler(call) or result

            self._rules.append((prefix, wrapped))
        return self

    def run(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
        probe: bool = False,
        stdin: str | None = None,
    ) -> CommandResult:
        call = Call(tuple(command), env, cwd, timeout, probe, stdin)
        self.calls.append(call)
        for prefix, response in reversed(self._rules):
            if call.argv[: len(prefix)] == prefix:
                if isinstance(response, CommandResult):
                    return response
                produced = response(call)
                assert produced is not None
                return produced
        raise AssertionError(f"commande inattendue : {call.argv}")

    def run_streaming(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | None = None,
        merge_stderr: bool = False,
    ) -> CommandResult:
        raise NotImplementedError

    def argvs(self) -> list[tuple[str, ...]]:
        """Liste les argv appelés, dans l'ordre."""
        return [c.argv for c in self.calls]
