.PHONY: test

PYTHON := ./.venv/bin/python

test:
	$(PYTHON) -m unittest discover -t . -s tests -p "test*.py" -v
