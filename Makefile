VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup run test compile smoke-ui cloud-prepare-ssh deploy-vps

setup:
	python3 -m venv $(VENV)
	$(PIP) install -e .

run:
	$(VENV)/bin/docmolder

test:
	$(PYTHON) -m unittest discover -s tests

compile:
	$(PYTHON) -m compileall src tests

smoke-ui:
	$(PYTHON) scripts/smoke_telegram_desktop.py --plan full

cloud-prepare-ssh:
	bash scripts/setup_codex_ssh.sh

deploy-vps:
	bash scripts/deploy_vps_from_codex.sh $(TARGET_REF)
