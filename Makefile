VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup run test compile ci build smoke-ui brand-assets telegram-brand-sync cloud-prepare-ssh deploy-vps

setup:
	python3 -m venv $(VENV)
	$(PIP) install -e .

run:
	$(VENV)/bin/docmolder

test:
	$(PYTHON) -m unittest discover -s tests

compile:
	$(PYTHON) -m compileall src tests

ci:
	bash scripts/ci_verify.sh

build:
	$(PYTHON) -m build

brand-assets:
	$(PYTHON) scripts/render_brand_assets.py

telegram-brand-sync:
	$(PYTHON) scripts/sync_telegram_branding.py

smoke-ui:
	$(PYTHON) scripts/smoke_telegram_desktop.py --plan full

cloud-prepare-ssh:
	bash scripts/setup_codex_ssh.sh

deploy-vps:
	bash scripts/deploy_vps_from_codex.sh $(TARGET_REF)
