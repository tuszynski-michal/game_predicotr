import argparse
from pathlib import Path

import uvicorn

from .api import create_app
from .catalog import Catalog

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    arguments = parser.parse_args()
    uvicorn.run(create_app(Catalog(arguments.snapshot)), host="127.0.0.1", port=8102)
