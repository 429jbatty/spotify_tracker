.PHONY: test api backend frontend dev track track-all refresh-metadata cache-artwork deploy

PYTHON := ./.venv/bin/python
NODE_BIN ?= $(HOME)/.nvm/versions/node/v22.22.0/bin
FRONTEND_DIR := frontend
FRONTEND_HOST := 127.0.0.1
FRONTEND_PORT := 5173
BACKEND_HOST := 127.0.0.1
BACKEND_PORT := 8000

test:
	$(PYTHON) -m unittest discover -t . -s tests -p "test*.py" -v

api: backend

backend:
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)

frontend:
	PATH="$(NODE_BIN):$$PATH" npm --prefix $(FRONTEND_DIR) run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT)

dev:
	@set -e; \
	$(MAKE) backend & backend_pid=$$!; \
	$(MAKE) frontend & frontend_pid=$$!; \
	trap 'kill $$backend_pid $$frontend_pid 2>/dev/null || true' INT TERM EXIT; \
	wait $$backend_pid $$frontend_pid

track:
	$(PYTHON) main.py

track-all:
	$(PYTHON) -m backend.app.jobs.track_all_users

refresh-metadata:
	$(PYTHON) -m one_time_scripts._refresh_metadata

cache-artwork:
	$(PYTHON) -m one_time_scripts._cache_artwork

deploy:
	./deploy/deploy.sh
