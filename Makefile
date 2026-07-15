.PHONY: test lint format clean run

run:
	uv run pyharness

test:
	uv run pytest tests/ -v --tb=short

test-cov:
	uv run pytest tests/ -v --tb=short --cov=src/pyharness --cov-report=term-missing

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

fix:
	uv run ruff check --fix src/ tests/

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov dist build *.egg-info

all: lint test
