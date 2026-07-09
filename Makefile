.PHONY: test api backend frontend dev dev-home track track-all refresh-metadata cache-artwork deploy

PYTHON := ./.venv/bin/python
NODE_BIN ?= $(HOME)/.nvm/versions/node/v22.22.0/bin
FRONTEND_DIR := frontend
FRONTEND_HOST := 127.0.0.1
FRONTEND_PORT := 5173
BACKEND_HOST := 127.0.0.1
BACKEND_PORT := 8000
BACKEND_URL := http://$(BACKEND_HOST):$(BACKEND_PORT)
HOME_MODE ?= 0
DEV_HOME_URLS := scripts/dev_home_urls.py

test:
	$(PYTHON) -m unittest discover -t . -s tests -p "test*.py" -v

api: backend

backend:
	$(PYTHON) -m uvicorn backend.app.main:app --reload --host $(BACKEND_HOST) --port $(BACKEND_PORT)

frontend:
	VITE_API_PROXY_TARGET="$(BACKEND_URL)" PATH="$(NODE_BIN):$$PATH" npm --prefix $(FRONTEND_DIR) run dev -- --host $(FRONTEND_HOST) --port $(FRONTEND_PORT) --strictPort

dev:
	@set -e; \
	$(PYTHON) -c 'exec("import socket, sys\nports = [(\"$(BACKEND_HOST)\", $(BACKEND_PORT)), (\"$(FRONTEND_HOST)\", $(FRONTEND_PORT))]\nbusy = []\nfor host, port in ports:\n    sock = socket.socket()\n    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\n    try:\n        sock.bind((host, port))\n    except OSError:\n        busy.append(f\"{host}:{port}\")\n    finally:\n        sock.close()\nif busy:\n    sys.exit(\"Ports already in use: \" + \", \".join(busy))")'; \
	$(MAKE) backend & backend_pid=$$!; \
	until curl -fsS "$(BACKEND_URL)/api/health" >/dev/null 2>&1; do \
		if ! kill -0 $$backend_pid 2>/dev/null; then \
			wait $$backend_pid; \
			exit $$?; \
		fi; \
		sleep 0.5; \
	done; \
	if [ "$(HOME_MODE)" = "1" ]; then \
		$(PYTHON) $(DEV_HOME_URLS) --backend-url "$(BACKEND_URL)" --frontend-port "$(FRONTEND_PORT)"; \
	fi; \
	$(MAKE) frontend & frontend_pid=$$!; \
	trap 'kill $$backend_pid $$frontend_pid 2>/dev/null || true' INT TERM EXIT; \
	wait $$backend_pid $$frontend_pid

dev-home:
	$(MAKE) dev FRONTEND_HOST=0.0.0.0 HOME_MODE=1

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
