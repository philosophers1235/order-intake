.PHONY: install demo serve test

install:
	uv venv --python 3.12
	uv pip install -e ".[dev]"

demo:
	.venv/bin/intake demo

serve:
	.venv/bin/intake serve --fixtures

test:
	.venv/bin/pytest -q
