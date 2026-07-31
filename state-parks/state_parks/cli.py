"""Command line entry points.

    python -m state_parks.cli verify NC       # probe a provider, report findings
    python -m state_parks.cli discover MD     # build a catalog from a live API
    python -m state_parks.cli refresh --months 12
    python -m state_parks.cli search --arrival 2026-09-04 --departure 2026-09-06
    python -m state_parks.cli serve
    python -m state_parks.cli schedule

``verify`` is the important one for this project: several providers ship with
unconfirmed wire formats (see docs/PLATFORMS.md), and this is how you confirm or
correct them from a machine with unrestricted network access.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from state_parks.config import settings
from state_parks.database import Database, Repository
from state_parks.models import SearchQuery
from state_parks.providers import PROVIDER_CLASSES, all_providers, get_provider
from state_parks.services import RefreshService, SearchService

FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


async def cmd_verify(args: argparse.Namespace) -> int:
    states = [args.state] if args.state else list(PROVIDER_CLASSES)
    exit_code = 0

    for code in states:
        provider = get_provider(code)
        print(f"\n=== {code} ({provider.platform}) {provider.base_url}")
        try:
            report = await provider.verify()
        except Exception as exc:  # noqa: BLE001 - a probe should never crash
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            exit_code = 1
            continue
        finally:
            await provider.aclose()

        for check in report.get("checks", []):
            mark = "ok  " if check.get("ok") else "FAIL"
            print(f"  [{mark}] {check['check']}: {check.get('detail', '')}")
            if not check.get("ok"):
                exit_code = 1

        for finding in report.get("endpoint_probe", []):
            mark = "ok  " if finding.get("ok") else "----"
            extra = finding.get("json_keys") or finding.get("detail", "")
            print(
                f"  [{mark}] probe {finding['path']}: "
                f"{finding.get('content_type', '')} {extra}"
            )

        if report.get("next_step"):
            print(f"  NEXT: {report['next_step']}")

        if args.save_fixture and report.get("raw_sample"):
            FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
            path = FIXTURE_DIR / f"{code.lower()}_live_sample.txt"
            path.write_text(report["raw_sample"])
            print(f"  saved sample -> {path}")

    return exit_code


async def cmd_discover(args: argparse.Namespace) -> int:
    """Build a park/location catalog from a provider's live API."""
    provider = get_provider(args.state)
    try:
        if not hasattr(provider, "discover"):
            print(
                f"{args.state}: this provider has a static catalog; edit "
                f"state_parks/providers/{args.state.lower()}.py instead."
            )
            return 1
        catalog = await provider.discover()  # type: ignore[attr-defined]
    finally:
        await provider.aclose()

    output = args.output or Path(f"{args.state.lower()}_catalog.json")
    Path(output).write_text(json.dumps(catalog, indent=2))
    print(f"{args.state}: wrote {len(catalog)} entries -> {output}")
    print("Paste these into the provider's catalog attribute.")
    return 0


async def cmd_refresh(args: argparse.Namespace) -> int:
    settings.ensure_dirs()
    db = Database()
    try:
        service = RefreshService(Repository(db.conn))
        providers = all_providers([args.state] if args.state else None)
        results = await service.refresh_all(
            providers, months=args.months, force=args.force
        )
        for result in results:
            status = result.skipped or (
                f"{result.windows_ok}/{result.windows_attempted} windows, "
                f"{result.cabins_found} cabins, {result.rows_written} rows"
            )
            print(f"{result.provider}: {status}")
            for error in result.errors[:3]:
                print(f"    ! {error}")
        await asyncio.gather(
            *(p.aclose() for p in providers), return_exceptions=True
        )
    finally:
        db.close()
    return 0


async def cmd_search(args: argparse.Namespace) -> int:
    db = Database()
    try:
        service = SearchService(Repository(db.conn))
        query = SearchQuery(
            arrival=args.arrival,
            departure=args.departure,
            guests=args.guests,
            pets=args.pets,
            states=args.state,
            waterfront=args.waterfront,
        )
        cabins = (
            await service.search_live(query)
            if args.live
            else await service.search(query)
        )
        if not cabins:
            print("No cabins found. (Have you run `refresh` yet?)")
            return 0
        for cabin in cabins:
            rate = (
                f"${cabin.nightly_rate:.0f}/night"
                if cabin.nightly_rate
                else "rate ?"
            )
            print(
                f"{cabin.state}  {cabin.park:<38} "
                f"{cabin.cabin_name:<22} "
                f"{rate:<14} {cabin.reservation_url}"
            )
        print(f"\n{len(cabins)} cabins")
    finally:
        db.close()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "state_parks.api.app:app", host=args.host, port=args.port, reload=args.reload
    )
    return 0


async def cmd_schedule(args: argparse.Namespace) -> int:
    from state_parks.scheduler import run_forever

    await run_forever()
    return 0


def _date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="state_parks", description=__doc__.split("\n")[0]
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser(
        "verify", help="probe providers and report what their endpoints return"
    )
    p_verify.add_argument("state", nargs="?", help="e.g. NC (default: all)")
    p_verify.add_argument(
        "--save-fixture",
        action="store_true",
        help="write a sample response into tests/fixtures/",
    )
    p_verify.set_defaults(func=cmd_verify, is_async=True)

    p_discover = sub.add_parser(
        "discover", help="build a park catalog from a provider's live API"
    )
    p_discover.add_argument("state")
    p_discover.add_argument("--output", type=Path)
    p_discover.set_defaults(func=cmd_discover, is_async=True)

    p_refresh = sub.add_parser("refresh", help="refresh availability into SQLite")
    p_refresh.add_argument("--state")
    p_refresh.add_argument("--months", type=int, default=settings.refresh_months)
    p_refresh.add_argument(
        "--force", action="store_true", help="ignore freshness and refetch everything"
    )
    p_refresh.set_defaults(func=cmd_refresh, is_async=True)

    p_search = sub.add_parser("search", help="search the local cache (or --live)")
    p_search.add_argument("--arrival", type=_date, required=True)
    p_search.add_argument("--departure", type=_date, required=True)
    p_search.add_argument("--state", action="append")
    p_search.add_argument("--guests", type=int, default=2)
    p_search.add_argument("--pets", action="store_true")
    p_search.add_argument("--waterfront", action="store_true", default=None)
    p_search.add_argument("--live", action="store_true")
    p_search.set_defaults(func=cmd_search, is_async=True)

    p_serve = sub.add_parser("serve", help="run the FastAPI app")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=cmd_serve, is_async=False)

    p_schedule = sub.add_parser("schedule", help="run the background refresh loop")
    p_schedule.set_defaults(func=cmd_schedule, is_async=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    if getattr(args, "is_async", False):
        return asyncio.run(args.func(args))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
