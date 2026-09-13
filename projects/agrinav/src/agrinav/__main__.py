"""Enable ``python -m agrinav`` as an alias for the ``agrinav`` console script."""

from agrinav.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
