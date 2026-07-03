# Makefile pour linuxtools

.PHONY: help install install-dev uninstall test test-verbose test-cov lint clean build all

# Cible par défaut
help:
	@echo "Commandes disponibles:"
	@echo "  make install        Installer la bibliothèque en local"
	@echo "  make install-dev    Installer avec dépendances de développement"
	@echo "  make uninstall      Désinstaller la bibliothèque"
	@echo "  make test           Lancer les tests"
	@echo "  make test-verbose   Lancer les tests en mode verbose"
	@echo "  make test-cov       Lancer les tests avec couverture"
	@echo "  make lint           Vérifier le style PEP8"
	@echo "  make clean          Nettoyer les fichiers générés"
	@echo "  make build          Construire le package"
	@echo "  make all            Lint + tests + build"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

uninstall:
	pip uninstall -y linuxtools

# Tests
test:
	pytest tests/

test-verbose:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=linuxtools --cov-report=term-missing

# Linting
lint:
	pycodestyle src/linuxtools/

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
	python -m build

# Tout lancer
all: lint test build
