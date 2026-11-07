# Makefile pour linuxtools

.PHONY: help install install-dev uninstall test test-unit test-integration test-verbose test-cov lint clean build all hooks

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
lint:
	uv run ruff check src/
	uv run ruff format --check src/
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

# Tout lancer
all: lint test build
