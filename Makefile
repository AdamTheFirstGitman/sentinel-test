.PHONY: dev smoke

dev:
	uv run uvicorn app.main:app --reload

smoke:
	uv run python scripts/smoke_jev.py
