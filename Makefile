VENV := .venv
PYTHON_BOOTSTRAP ?= $(shell command -v python3.13 2>/dev/null || command -v python3)
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: setup lock lock-check run test compile ci ci-static ci-quality ci-test build smoke-ui brand-assets telegram-brand-sync cloud-prepare-ssh deploy-vps classify-changes preflight-publish publish-doctor publish-docs cleanup-branches codex-dev-report github-maintenance ops-report profile-processing

setup:
	$(PYTHON_BOOTSTRAP) -m venv $(VENV)
	$(PIP) install --require-hashes -r requirements-build.lock
	$(PIP) install --require-hashes -r requirements-dev.lock
	$(PIP) install -e . --no-deps --no-build-isolation

lock:
	uv pip compile pyproject.toml --upgrade --universal --python-version 3.11 --generate-hashes --no-header -o requirements.lock
	uv pip compile pyproject.toml --extra dev --constraint requirements.lock --upgrade --universal --python-version 3.11 --generate-hashes --no-header -o requirements-dev.lock
	uv pip compile requirements-tools.in --upgrade --universal --python-version 3.11 --generate-hashes --no-header -o requirements-tools.lock
	uv pip compile requirements-build.in --upgrade --universal --python-version 3.11 --generate-hashes --no-header -o requirements-build.lock

lock-check:
	bash scripts/check_lock_sync.sh

run:
	$(VENV)/bin/docmolder

test:
	$(PYTHON) -m unittest discover -s tests

compile:
	$(PYTHON) -m compileall src tests

ci:
	bash scripts/ci_verify.sh

ci-static:
	bash scripts/ci_static_verify.sh

ci-quality:
	bash scripts/ci_quality.sh

ci-test:
	bash scripts/ci_test.sh --coverage

build:
	$(PYTHON) -m build --no-isolation

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

classify-changes:
	$(PYTHON) scripts/classify_changes.py --working-tree

preflight-publish:
	bash scripts/preflight_publish.sh

publish-doctor:
	$(PYTHON) scripts/publish_doctor.py --fail

publish-docs:
	@test -n "$(TITLE)" || (echo 'Uso: make publish-docs TITLE="chore(docs): descrizione"' >&2; exit 2)
	bash scripts/publish_change.sh "$(TITLE)"

cleanup-branches:
	bash scripts/cleanup_merged_branches.sh

codex-dev-report:
	$(PYTHON) scripts/codex_dev_report.py

github-maintenance:
	$(PYTHON) scripts/github_maintenance_report.py

ops-report:
	$(PYTHON) scripts/ops_report.py

profile-processing:
	$(PYTHON) scripts/profile_processing_flows.py
