"""Download data dependencies for the microgrid simulator.

  python -m scripts.fetch_data nrel --lat 30.27 --lon -97.74 --year 2024 \\
    --out data/nrel_solar/austin_2024.csv

  python -m scripts.fetch_data resstock --state TX --building-ids 1 2 3 \\
    --out-dir data/resstock/

NREL NSRDB (solar irradiance):
  Requires NREL_API_KEY + NREL_EMAIL env vars. Free key at
  https://developer.nrel.gov/signup/ (2-minute signup, no affiliation needed).

NREL ResStock (residential load):
  Free, no signup, public S3 bucket. Each building is a ~3 MB parquet file
  containing one year of 15-min electricity consumption. Default subset:
  resstock_amy2018_release_2 (Actual Meteorological Year 2018).

Pecan Street load (real measured smart-meter data):
  Requires a researcher account at https://www.pecanstreet.org/dataport/
  with university or commercial affiliation. NOT downloadable by this script
  — apply manually, export the 15-min table to data/pecan_street/.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

# NREL deprecated psm3-2-2 in favor of the v4 GOES-aggregated dataset (2024).
NSRDB_URL = (
    "https://developer.nrel.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
)


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
    r = requests.get(NSRDB_URL, params=params, timeout=120, allow_redirects=True)
    r.raise_for_status()
    # NSRDB v4 prefixes the CSV with 2 metadata lines before the actual data
    # header (`Year,Month,Day,Hour,Minute,GHI`). Strip them so the file matches
    # what sim.adapters.nrel_solar.NRELSolar expects.
    lines = r.text.splitlines()
    if len(lines) >= 3 and lines[0].startswith("Source,"):
        lines = lines[2:]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out_path} ({len(lines)} rows)", file=sys.stderr)


_RESSTOCK_LIST_URL = (
    "https://oedi-data-lake.s3.amazonaws.com/?prefix=nrel-pds-building-stock/"
    "end-use-load-profiles-for-us-building-stock/2024/resstock_amy2018_release_2/"
    "timeseries_individual_buildings/by_state/upgrade=0/state={state}/"
)
_RESSTOCK_FILE_URL = (
    "https://oedi-data-lake.s3.amazonaws.com/nrel-pds-building-stock/"
    "end-use-load-profiles-for-us-building-stock/2024/resstock_amy2018_release_2/"
    "timeseries_individual_buildings/by_state/upgrade=0/state={state}/{filename}"
)


def _list_resstock_files(state: str) -> list[str]:
    """List all ResStock building filenames available for a state. Each call hits S3."""
    import re

    state = state.upper()
    keys: list[str] = []
    marker = ""
    while True:
        url = _RESSTOCK_LIST_URL.format(state=state)
        if marker:
            url += f"&marker={marker}"
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        body = r.text
        page_keys = re.findall(r"<Key>([^<]+)</Key>", body)
        if not page_keys:
            break
        for k in page_keys:
            fname = k.rsplit("/", 1)[-1]
            if fname:
                keys.append(fname)
        truncated = "<IsTruncated>true</IsTruncated>" in body
        if not truncated:
            break
        marker = page_keys[-1]
    return keys


def fetch_resstock(*, state: str, n_buildings: int, out_dir: Path) -> list[str]:
    """Download the first n_buildings ResStock parquet files for a state.

    Returns the list of filenames written, which you can paste into your scenario
    YAML's `house_building_files`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    state = state.upper()
    print(f"  Listing ResStock files for state={state}…", file=sys.stderr)
    all_files = _list_resstock_files(state)
    print(
        f"  Found {len(all_files)} buildings available; downloading first {n_buildings}",
        file=sys.stderr,
    )
    chosen = all_files[:n_buildings]
    for fname in chosen:
        url = _RESSTOCK_FILE_URL.format(state=state, filename=fname)
        local = out_dir / fname
        if local.exists():
            print(f"  exists: {local}", file=sys.stderr)
            continue
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        local.write_bytes(r.content)
        print(f"  wrote {local} ({len(r.content) / 1024:.0f} KB)", file=sys.stderr)
    return chosen


def _cmd_nrel(args: argparse.Namespace) -> None:
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


def _cmd_resstock(args: argparse.Namespace) -> None:
    files = fetch_resstock(state=args.state, n_buildings=args.n, out_dir=args.out_dir)
    print(f"\nDownloaded {len(files)} ResStock buildings to {args.out_dir}.", file=sys.stderr)
    print("\nFor your scenario YAML's house_building_files, paste:", file=sys.stderr)
    print("house_building_files:", file=sys.stdout)
    for f in files:
        print(f"  - {f}", file=sys.stdout)


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    pn = sub.add_parser("nrel", help="Download NREL NSRDB solar irradiance for a location+year")
    pn.add_argument("--lat", type=float, default=30.27, help="Latitude (default: Austin TX)")
    pn.add_argument("--lon", type=float, default=-97.74, help="Longitude (default: Austin TX)")
    pn.add_argument("--year", type=int, default=2024)
    pn.add_argument(
        "--out",
        type=Path,
        default=Path("data/nrel_solar/austin_2024.csv"),
        help="Output CSV path",
    )
    pn.set_defaults(func=_cmd_nrel)

    pr = sub.add_parser(
        "resstock", help="Download NREL ResStock residential building load profiles"
    )
    pr.add_argument("--state", type=str, default="TX", help="2-letter US state code (default: TX)")
    pr.add_argument(
        "-n",
        type=int,
        default=30,
        help="Number of buildings to download (default: 30, matching the 5x6 scenario grid). "
        "Files are picked in S3-listing order; same state -> same first-N files (deterministic).",
    )
    pr.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/resstock/"),
        help="Output directory for the parquet files (default: data/resstock/)",
    )
    pr.set_defaults(func=_cmd_resstock)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
