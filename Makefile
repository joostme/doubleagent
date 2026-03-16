PYTHON ?= python

.PHONY: install test run help

help:
	@printf "Targets:\n"
	@printf "  install  Install Python dependencies\n"
	@printf "  test     Run unit and integration tests\n"
	@printf "  run      Run doubleagent in local test mode\n"

install:
	$(PYTHON) -m pip install --no-cache-dir -r requirements.txt

test:
	$(PYTHON) -m unittest discover -s tests -v

run:
	PYTHONPATH=. $(PYTHON) -m doubleagent.main --skip-iptables --config /config/config.json
