# Makefile pour linuxtools

.PHONY: help install install-dev uninstall test test-unit test-integration test-verbose test-cov lint clean build all hooks bump-consumers

# Cible par défaut
help:
	@echo "Commandes disponibles:"
	@echo "  make install        Installer le projet et tous les extras (uv sync --all-extras)"
	@echo "  make install-dev    Alias de install + activation des hooks Git"
	@echo "  make uninstall      Retirer linuxtools du venv (uv pip uninstall)"
	@echo "  make test           Lancer les tests"
	@echo "  make test-unit      Lancer uniquement les tests unitaires"
	@echo "  make test-integration  Lancer uniquement les tests d'intégration"
	@echo "  make test-verbose   Lancer les tests en mode verbose"
	@echo "  make test-cov       Lancer les tests avec couverture"
	@echo "  make lint           Vérifier le style PEP8, ruff et le typage (mypy)"
	@echo "  make clean          Nettoyer les fichiers générés"
	@echo "  make build          Construire wheel + sdist (uv build)"
	@echo "  make hooks          Activer les hooks Git versionnés (.githooks)"
	@echo "  make all            Lint + tests + build"
	@echo "  make bump-consumers TAG=vX.Y.Z [ARGS=...]  Monter le pin des consommateurs"

# Installation
# `--all-extras` est obligatoire : uv sync est « exact » et désinstallerait
# les extras non demandés (ex. webapitools, requis par mypy).
install:
	uv sync --all-extras

# Alias : les dépendances de dev sont des extras, déjà couverts par install.
install-dev: install hooks

# Hooks Git versionnés : pointe core.hooksPath vers .githooks/ et rend
# les hooks exécutables. À lancer une fois après un clone.
hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/*
	@echo "Hooks Git activés (core.hooksPath -> .githooks)"

# Effet temporaire : le prochain `uv run` (test, lint...) réinstalle le projet
# dans le venv. Cible conservée pour un retrait ponctuel.
uninstall:
	uv pip uninstall linuxtools

# Tests
test:
	uv run pytest tests/

test-unit:
	uv run pytest tests/unit/ -m "not integration"

test-integration:
	uv run pytest tests/integration/ -m integration --no-cov

test-verbose:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov-report=term-missing

# Linting
# Le gate de format couvre src/ et les tests de linuxtools.devtools (le
# reste de tests/ n'est pas encore formaté : 57 fichiers hérités).
DEVTOOLS_TESTS := tests/unit/scripted_executor.py $(wildcard tests/unit/test_devtools_*.py) tests/integration/test_devtools_bumper.py
lint:
	uv run ruff check src/
	uv run ruff format --check src/ $(DEVTOOLS_TESTS)
	uv run bandit -ll -r src/linuxtools/
	uv run mypy src/linuxtools/ tests/

# Nettoyage
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Build
build: clean
	uv build

# Répercute un tag linuxtools sur les projets consommateurs (outil de
# mainteneur, sans point d'entrée). Exemple :
#   make bump-consumers TAG=v2.11.1 ARGS="--dry-run --only claudetools"
# TAG et ARGS passent par l'environnement (`$$TAG`) : le shell n'interprète
# jamais leur contenu comme du code. ARGS est découpé en mots (set -f :
# pas de glob) ; la validation du tag est faite côté Python.
bump-consumers: export TAG := $(TAG)
bump-consumers: export ARGS := $(ARGS)
bump-consumers:
	@test -n "$$TAG" || { echo "Usage: make bump-consumers TAG=vX.Y.Z [ARGS=...]"; exit 2; }
	@set -f; uv run python -m linuxtools.devtools bump-consumers "$$TAG" $$ARGS

# Tout lancer
all: lint test build
