.PHONY: test api track track-all refresh-metadata cache-artwork deploy

PYTHON := ./.venv/bin/python

test:
	$(PYTHON) -m unittest discover -t . -s tests -p "test*.py" -v

api:
	$(PYTHON) -m uvicorn backend.app.main:app --reload

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
