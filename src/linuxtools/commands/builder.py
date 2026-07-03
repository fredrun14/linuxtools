"""Constructeur fluent pour assembler des commandes système.

Ce module fournit la classe CommandBuilder qui permet de construire
des commandes sous forme de liste de chaînes de caractères via
une API fluent.

Example:
    Construction d'une commande rsync :

        from linuxtools.commands import CommandBuilder

        cmd = (
            CommandBuilder("rsync")
            .with_options(["-av", "--delete"])
            .with_option("--compress-level", "3")
            .with_flag("--stats")
            .with_args(["/src/", "/dest/"])
            .build()
        )
        # Résultat : ["rsync", "-av", "--delete",
        #             "--compress-level=3", "--stats",
        #             "/src/", "/dest/"]
"""


class CommandBuilder:
    """Constructeur fluent pour assembler des commandes système."""

    def __init__(self, program: str) -> None:
        """Initialise le constructeur avec le programme.

        Args:
            program: Nom ou chemin du programme à exécuter.

        Raises:
            ValueError: Si program est vide.
        """
        if not program or not program.strip():
            raise ValueError("Le programme est requis.")
        self._program: str = program
        self._options: list[str] = []
        self._args: list[str] = []

    def with_options(self, options: list[str]) -> "CommandBuilder":
        """Ajoute une liste d'options.

        Args:
            options: Liste d'options (ex: ['-av', '--del']).

        Returns:
            L'instance courante pour le chaînage.
        """
        self._options.extend(options)
        return self

    def with_flag(self, flag: str) -> "CommandBuilder":
        """Ajoute un flag simple.

        Args:
            flag: Flag à ajouter (ex: '--stats').

        Returns:
            L'instance courante pour le chaînage.
        """
        self._options.append(flag)
        return self

    def with_option(self, key: str, value: str) -> "CommandBuilder":
        """Ajoute une option clé=valeur.

        Produit le format 'clé=valeur' dans la commande.

        Args:
            key: Clé de l'option (ex: '--compression').
            value: Valeur de l'option (ex: 'lz4').

        Returns:
            L'instance courante pour le chaînage.
        """
        self._options.append(f"{key}={value}")
        return self

    def with_option_if(
        self,
        key: str,
        value: str | None,
        condition: bool = True,
    ) -> "CommandBuilder":
        """Ajoute une option seulement si la condition est vraie.

        L'option est ignorée si condition est False ou si
        value est None.

        Args:
            key: Clé de l'option.
            value: Valeur de l'option (peut être None).
            condition: Condition d'ajout (défaut: True).

        Returns:
            L'instance courante pour le chaînage.
        """
        if condition and value is not None:
            self._options.append(f"{key}={value}")
        return self

    def with_args(self, args: list[str]) -> "CommandBuilder":
        """Ajoute les arguments positionnels finaux.

        Args:
            args: Liste d'arguments positionnels.

        Returns:
            L'instance courante pour le chaînage.
        """
        self._args.extend(args)
        return self

    def build(self) -> list[str]:
        """Construit et retourne la commande sous forme de liste.

        Returns:
            Liste de chaînes représentant la commande complète.
        """
        return [self._program] + self._options + self._args
