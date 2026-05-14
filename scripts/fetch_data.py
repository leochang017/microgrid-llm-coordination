"""Download NREL NSRDB hourly solar irradiance for a location + year.

Usage:
  export NREL_API_KEY=...   # https://developer.nrel.gov/signup/
  export NREL_EMAIL=you@example.com
  python -m scripts.fetch_data --lat 30.27 --lon -97.74 --year 2024 \
      --out data/nrel_solar/austin_2024.csv

Pecan Street load data requires a researcher account at
https://www.pecanstreet.org/dataport/ and is NOT downloaded by this script.
After approval, export the 15-min residential table to
data/pecan_street/<filename>.csv with columns:
  dataid, local_15min, grid, solar, use
…and reference the path from your scenario YAML's data_paths.load_csv.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

NSRDB_URL = "https://developer.nrel.gov/api/nsrdb/v2/solar/psm3-2-2-download.csv"


def fetch_nrel(
    *,
    api_key: str,
    email: str,
    lat: float,
    lon: float,
    year: int,
    out_path: Path,
) -> None:
    params = {
        "api_key": api_key,
        "email": email,
        "wkt": f"POINT({lon} {lat})",
        "names": str(year),
        "interval": "60",
        "utc": "true",
        "attributes": "ghi",
        "leap_day": "false",
    }
    print(f"Requesting NREL NSRDB for ({lat}, {lon}) {year}…", file=sys.stderr)
    r = requests.get(NSRDB_URL, params=params, timeout=120)
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    print(f"Wrote {out_path}", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lat", type=float, default=30.27, help="Latitude (default: Austin TX)")
    p.add_argument("--lon", type=float, default=-97.74, help="Longitude (default: Austin TX)")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument(
        "--out",
        type=Path,
        default=Path("data/nrel_solar/austin_2024.csv"),
        help="Output CSV path (default: data/nrel_solar/austin_2024.csv)",
    )
    args = p.parse_args()

    api_key = os.environ.get("NREL_API_KEY")
    email = os.environ.get("NREL_EMAIL")
    if not api_key or not email:
        raise SystemExit(
            "Set NREL_API_KEY and NREL_EMAIL env vars. Get a free key at "
            "https://developer.nrel.gov/signup/"
        )
    fetch_nrel(
        api_key=api_key, email=email, lat=args.lat, lon=args.lon, year=args.year, out_path=args.out
    )

    print(
        "\nPecan Street load data requires a researcher account at "
        "https://www.pecanstreet.org/dataport/. After approval, export the "
        "15-min residential table for ~30 houses to "
        "data/pecan_street/<filename>.csv with columns: "
        "dataid, local_15min, grid, solar, use.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
