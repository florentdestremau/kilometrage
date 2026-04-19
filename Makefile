.PHONY: dev test lint install

install:
	uv pip install -e ".[dev]"

dev:
	STORAGE_DIR=/tmp/route-compare-dev \
	uvicorn route_compare.main:app --reload --port 8000 \
	  --app-dir src

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/
