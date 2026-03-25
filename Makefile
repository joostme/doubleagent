UV ?= uv

.PHONY: install lock test run help

help:
	@printf "Targets:\n"
	@printf "  install  Sync Python environment with uv\n"
	@printf "  lock     Refresh uv.lock\n"
	@printf "  test     Run unit and integration tests\n"
	@printf "  run      Run doubleagent in local test mode\n"

install:
	$(UV) sync --locked

lock:
	$(UV) lock

test:
	$(UV) run python -m unittest discover -s tests -v

run:
	$(UV) run doubleagent --config /config/config.json
