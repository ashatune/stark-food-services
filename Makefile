PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
PYTHONPATH := src

.PHONY: help venv generate validate load deploy clean

help:
	@echo "Stark Food Services (SFS) targets:"
	@echo "  make venv      - Create Python virtual environment in .venv"
	@echo "  make generate  - Generate deterministic synthetic supply-chain data in data/"
	@echo "  make validate  - Run data-quality and referential integrity checks on data/"
	@echo "  make load      - Load all data/*.jsonl files into BigQuery dataset sfs_demo"
	@echo "  make deploy    - Build and deploy sfs-mcp MCP Toolbox server to Cloud Run"
	@echo "  make clean     - Remove generated data files"

venv:
	python3 -m venv .venv

generate:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m sfs.generate

validate:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m sfs.validate

load:
	./scripts/load_bq.sh

deploy:
	./scripts/deploy_cloud_run.sh

clean:
	rm -rf data/*.jsonl data/*.parquet data/*.csv
