.PHONY: test api import-json-to-sqlite export-sqlite-to-json track refresh-metadata

PYTHON := ./.venv/bin/python

test:
	$(PYTHON) -m unittest discover -t . -s tests -p "test*.py" -v

api:
	$(PYTHON) -m uvicorn backend.app.main:app --reload

import-json-to-sqlite:
	$(PYTHON) -m one_time_scripts._import_json_to_sqlite

export-sqlite-to-json:
	$(PYTHON) -m one_time_scripts._export_sqlite_to_json

track:
	$(PYTHON) main.py

refresh-metadata:
	$(PYTHON) -m one_time_scripts._refresh_metadata
