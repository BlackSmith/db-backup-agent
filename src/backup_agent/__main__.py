"""Module entrypoint for `python -m backup_agent`."""

from .app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
