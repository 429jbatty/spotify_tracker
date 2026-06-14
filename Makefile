.PHONY: test api backend frontend dev track track-all refresh-metadata cache-artwork deploy

PYTHON := ./.venv/bin/python
NODE_BIN ?= $(HOME)/.nvm/versions/node/v22.22.0/bin
FRONTEND_DIR := frontend
FRONTEND_HOST := 127.0.0.1
FRONTEND_PORT := 5173
BACKEND_HOST := 127.0.0.1
BACKEND_PORT := 8000
BACKEND_URL := http://$(BACKEND_HOST):$(BACKEND_PORT)

test:
	$(PYTHON) -m unittest discover -t . -s tests -p "test*.py" -v

api: backend

backend:
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)

frontend:
	VITE_API_PROXY_TARGET="$(BACKEND_URL)" PATH="$(NODE_BIN):$$PATH" npm --prefix $(FRONTEND_DIR) run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT) --strictPort

dev:
	@set -e; \
	$(PYTHON) -c 'import socket, sys; ports = [("$(BACKEND_HOST)", $(BACKEND_PORT)), ("$(FRONTEND_HOST)", $(FRONTEND_PORT))]; busy = [f"{host}:{port}" for host, port in ports if socket.socket().connect_ex((host, port)) == 0]; sys.exit("Ports already in use: " + ", ".join(busy)) if busy else None'; \
	$(MAKE) backend & backend_pid=$$!; \
	until curl -fsS "$(BACKEND_URL)/api/health" >/dev/null 2>&1; do \
		if ! kill -0 $$backend_pid 2>/dev/null; then \
			wait $$backend_pid; \
			exit $$?; \
		fi; \
		sleep 0.5; \
	done; \
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
