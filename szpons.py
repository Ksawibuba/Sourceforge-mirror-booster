#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SourceForge Mirror Speed Checker
=================================
Benchmarks available SourceForge mirrors and automatically downloads the file from the fastest one.
"""

import sys
import time
import re
import os
import argparse
import concurrent.futures
import subprocess
import urllib.parse


# ─── Auto-install Required Packages ──────────────────────────────────────────


def _ensure_packages():
    for pkg in ["requests", "rich"]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"[setup] Installing package: {pkg}...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pkg, "-q"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


_ensure_packages()

import requests
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TaskProgressColumn,
)
from rich.panel import Panel
from rich.align import Align
from rich import box
from rich.columns import Columns

# ─── Constants ───────────────────────────────────────────────────────────────

DEFAULT_WORKERS = 6  # How many mirrors to test simultaneously
DEFAULT_TEST_KB = 512  # Sample chunk size to download for testing speed
REQUEST_TIMEOUT = (5, 12)  # (connect, read) timeout in seconds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,pl-PL;q=0.8",
}

# Fully extended global list of known SourceForge mirrors
FALLBACK_MIRRORS = [
    # Europe & Closest regions
    "altushost-swe",
    "pilotfiber",
    "cfhcable",
    "netcologne",
    "freefr",
    "heanet",
    "kent",
    "rwthaachen",
    "switch",
    "netix",
    "garr",
    "leaseweb",
    "ignum",
    "cznic",
    "dfn",
    "spline",
    "kumisystems",
    "tcpdiag",
    # North America (USA / Canada)
    "phoenixnap",
    "versaweb",
    "ayera",
    "astuteinternet",
    "iweb",
    "cytranet",
    "liquidtelecom",
    "xmission",
    "umd",
    "unc",
    "colocrossing",
    "hivelocity",
    "webnx",
    "constant",
    "newcontinuum",
    "innoscale",
    "softlayer",
    # Asia / Australia / Rest of World
    "jaist",
    "nchc",
    "excellmedia",
    "nav",
    "tenet",
    "fastbull",
    "internode",
    "waix",
    "saix",
    "ufpr",
    "master",
    "downloads",
]

console = Console()


# ─── URL Parsing ──────────────────────────────────────────────────────────────


def parse_sf_url(url: str) -> dict | None:
    """
    Extracts the project, original encoded file path, and session query string tokens.
    """
    url = url.strip()

    # Extract query string (tokens like ts=..., fid=...) if they exist
    query = url.split("?")[1] if "?" in url else ""

    # 1. Standard project download page format
    m_proj = re.search(
        r"sourceforge\.net/projects/([^/]+)/files/([^?#]+)", url, re.IGNORECASE
    )
    if m_proj:
        project = m_proj.group(1)
        raw_path = m_proj.group(2)
        if raw_path.lower().endswith("/download"):
            raw_path = raw_path[:-9].rstrip("/")
        return {"project": project, "raw_path": raw_path, "query": query}

    # 2. Direct download link formats (downloads or mirror subdomains)
    m_direct = re.search(
        r"(?:downloads|[\w\-]+\.dl)\.sourceforge\.net/(?:project/)?([^/]+)/([^?#]+)",
        url,
        re.IGNORECASE,
    )
    if m_direct:
        project = m_direct.group(1)
        raw_path = m_direct.group(2).rstrip("/")
        return {"project": project, "raw_path": raw_path, "query": query}

    return None


# ─── Fetching Mirror List ─────────────────────────────────────────────────────


def get_mirrors(project: str, raw_path: str) -> list[str]:
    """
    Fetches the mirror list directly from the HTML code of the download page.
    Falls back to the built-in database upon network error.
    """
    url = f"https://sourceforge.net/projects/{project}/files/{raw_path}/download"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        r.raise_for_status()

        # Extract mirror codes from HTML
        found = list(dict.fromkeys(re.findall(r"use_mirror=([a-z0-9\-]+)", r.text)))

        if len(found) >= 2:
            return found

        console.print(
            "[yellow]⚠  No mirrors found on page – using the built-in fallback database.[/yellow]"
        )

    except Exception:
        console.print(
            "[yellow]⚠  Failed to reach page (no online access) – using the built-in fallback database.[/yellow]"
        )

    return FALLBACK_MIRRORS


# ─── Speed Benchmarking ───────────────────────────────────────────────────────


def test_mirror(
    code: str, project: str, raw_path: str, query: str, test_kb: int
) -> dict:
    """
    Benchmarks a single mirror by forwarding original session tokens to pass auth.
    """
    sf_url = f"https://{code}.dl.sourceforge.net/project/{project}/{raw_path}"
    if query:
        sf_url = f"{sf_url}?{query}"

    result = {
        "code": code,
        "speed_mbps": None,
        "latency_ms": None,
        "final_url": None,
        "status": "unknown",
    }

    try:
        t0 = time.perf_counter()
        r = requests.get(
            sf_url,
            headers=HEADERS,
            stream=True,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        result["latency_ms"] = (time.perf_counter() - t0) * 1000
        result["final_url"] = r.url

        if r.status_code not in (200, 206):
            result["status"] = f"HTTP {r.status_code}"
            r.close()
            return result

        # Stream chunk sample data
        test_bytes = test_kb * 1024
        downloaded = 0
        t_dl = time.perf_counter()

        for chunk in r.iter_content(chunk_size=8192):
            downloaded += len(chunk)
            if downloaded >= test_bytes:
                break

        elapsed = time.perf_counter() - t_dl
        r.close()

        if elapsed > 0 and downloaded > 0:
            result["speed_mbps"] = (downloaded / elapsed) / (1024 * 1024)

        result["status"] = "ok"

    except requests.Timeout:
        result["status"] = "timeout"
    except Exception as exc:
        result["status"] = str(exc)[:50]

    return result


# ─── Downloading File ─────────────────────────────────────────────────────────


def download_file(
    project: str, raw_path: str, query: str, mirror_code: str, output_dir: str
) -> str:
    """Downloads the file with a rich progress bar indicator."""
    dl_url = f"https://{mirror_code}.dl.sourceforge.net/project/{project}/{raw_path}"
    if query:
        dl_url = f"{dl_url}?{query}"

    filename_clean = urllib.parse.unquote(raw_path.split("/")[-1])
    filename = os.path.join(output_dir, filename_clean)

    r = requests.get(
        dl_url, stream=True, timeout=(10, 120), headers=HEADERS, allow_redirects=True
    )
    r.raise_for_status()

    total = int(r.headers.get("content-length", 0))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Downloading [cyan]{os.path.basename(filename)}[/cyan]...",
            total=total or None,
        )
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                progress.advance(task, len(chunk))

    return filename


# ─── Main Execution Program Flow ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="SourceForge Mirror Speed Checker & Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="SourceForge file download URL")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        metavar="N",
        help=f"Number of parallel mirror checks (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--test-kb",
        type=int,
        default=DEFAULT_TEST_KB,
        metavar="KB",
        help=f"Sample size to download for testing speed in KB (default: {DEFAULT_TEST_KB})",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        metavar="FOLDER",
        help="Target folder for the download destination (default: current)",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Display absolutely all benchmarked mirrors inside the leaderboard table",
    )
    parser.add_argument(
        "--list-mirrors",
        action="store_true",
        help="List the entire built-in mirror array database grid layout and exit",
    )
    args = parser.parse_args()

    # Display database array items and trigger exit execution
    if args.list_mirrors:
        console.print(
            Panel(
                Align.center(
                    f"[bold cyan]Built-in SourceForge Mirror Database ({len(FALLBACK_MIRRORS)} nodes)[/bold cyan]"
                ),
                border_style="cyan",
            )
        )
        console.print(Columns(FALLBACK_MIRRORS, equal=True, padding=(0, 2)))
        console.print()
        sys.exit(0)

    # ── Banner UI ──
    console.print(
        Panel(
            Align.center(
                "[bold cyan]SourceForge Mirror Speed Checker[/bold cyan]\n"
                "[dim]Benchmarks mirrors and selects the fastest one for download[/dim]"
            ),
            border_style="cyan",
            padding=(1, 6),
        )
    )

    url = args.url
    if not url:
        console.print(
            "\n[dim]Example link:[/dim]\n"
            "[dim]https://sourceforge.net/projects/sevenzip/files/"
            "7-Zip/24.09/7z2409-x64.exe/download[/dim]\n"
        )
        url = console.input(
            "[bold cyan]🔗 Enter SourceForge file URL: [/bold cyan] "
        ).strip()

    if not url:
        console.print("[red]❌ No URL provided![/red]")
        sys.exit(1)

    parsed = parse_sf_url(url)
    if not parsed:
        console.print(
            "[red]❌ Unrecognized SourceForge URL format.[/red]\n"
            "[dim]Accepted Formats:\n"
            "  https://sourceforge.net/projects/{project}/files/{file}/download\n"
            "  https://downloads.sourceforge.net/project/{project}/{file}\n"
            "  https://{mirror}.dl.sourceforge.net/project/{project}/{file}[/dim]"
        )
        sys.exit(1)

    project = parsed["project"]
    raw_path = parsed["raw_path"]
    query = parsed["query"]
    filename = urllib.parse.unquote(raw_path.split("/")[-1])

    console.print(f"\n[green]✓[/green] Project: [bold]{project}[/bold]")
    console.print(f"[green]✓[/green] File:    [bold]{filename}[/bold]")

    console.print("\n[cyan]⏳ Fetching mirror targets...[/cyan]")
    mirrors = get_mirrors(project, raw_path)
    console.print(
        f"[green]✓[/green] Loaded [bold]{len(mirrors)}[/bold] mirror hosts for speed benchmarks.\n"
    )

    results: list[dict] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Benchmarking mirror speeds...[/cyan]",
            total=len(mirrors),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            future_map = {
                ex.submit(test_mirror, m, project, raw_path, query, args.test_kb): m
                for m in mirrors
            }
            for future in concurrent.futures.as_completed(future_map):
                results.append(future.result())
                progress.advance(task)

    ok_results = sorted(
        [r for r in results if r["status"] == "ok" and r["speed_mbps"] is not None],
        key=lambda x: x["speed_mbps"],
        reverse=True,
    )
    failed_results = [r for r in results if r["status"] != "ok"]

    if not ok_results:
        console.print(
            "[red]❌ No mirrors responded correctly. Session token expired or path is invalid.[/red]"
        )
        sys.exit(1)

    console.print()
    tbl = Table(
        title=f"[bold]Mirror Leaderboard – {filename}[/bold]",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    tbl.add_column("#", justify="center", width=5)
    tbl.add_column("Mirror", style="white", min_width=16)
    tbl.add_column("Speed", justify="right", min_width=11)
    tbl.add_column("Bar", justify="left", min_width=20)
    tbl.add_column("Latency", justify="right", min_width=9)
    tbl.add_column("Status", justify="center", min_width=6)

    medals = ["🥇", "🥈", "🥉"]
    max_speed = ok_results[0]["speed_mbps"]

    for i, r in enumerate(ok_results):
        rank = medals[i] if i < 3 else f"  {i + 1}."
        ratio = r["speed_mbps"] / max_speed

        if ratio > 0.70:
            clr = "bold green"
        elif ratio > 0.40:
            clr = "yellow"
        else:
            clr = "dim red"

        bar_full = int(ratio * 20)
        bar_empty = 20 - bar_full
        bar = f"[{clr}]{'█' * bar_full}[/{clr}][dim]{'░' * bar_empty}[/dim]"

        lat = f"{r['latency_ms']:.0f} ms" if r.get("latency_ms") else "—"

        tbl.add_row(
            rank,
            r["code"],
            f"[{clr}]{r['speed_mbps']:.2f} MB/s[/{clr}]",
            bar,
            lat,
            "[green]✓[/green]",
        )

    # Error logging handler layout conditions
    displayed_failed = failed_results if args.show_all else failed_results[:4]
    for r in displayed_failed:
        tbl.add_row(
            "—",
            r["code"],
            "—",
            "",
            "—",
            f"[red]✗[/red] [dim]{r['status'][:18]}[/dim]",
        )

    if not args.show_all and len(failed_results) > 4:
        tbl.add_row(
            "",
            f"[dim]… and {len(failed_results) - 4} more errors (run script with --show-all flag to view all logs)[/dim]",
            "",
            "",
            "",
            "",
        )

    console.print(tbl)

    best = ok_results[0]
    best_url = f"https://{best['code']}.dl.sourceforge.net/project/{project}/{raw_path}"
    if query:
        best_url = f"{best_url}?{query}"

    console.print(
        Panel(
            f"[bold]Mirror:  [/bold][bold cyan]{best['code']}[/bold cyan]\n"
            f"[bold]Speed:   [/bold] [bold green]{best['speed_mbps']:.2f} MB/s[/bold green]"
            + (
                f"   |   Latency: {best['latency_ms']:.0f} ms"
                if best.get("latency_ms")
                else ""
            )
            + f"\n[bold]Link:    [/bold][dim]{best_url}[/dim]",
            title="[bold]🏆 Fastest Mirror Winner[/bold]",
            border_style="green",
            padding=(1, 2),
        )
    )

    # ── Automatic Direct Downloading ──
    console.print(
        "\n[cyan]🚀 Automatically starting download from the fastest mirror...[/cyan]\n"
    )
    os.makedirs(args.output_dir, exist_ok=True)
    try:
        saved = download_file(project, raw_path, query, best["code"], args.output_dir)
        size_mb = os.path.getsize(saved) / (1024 * 1024)
        abs_path = os.path.abspath(saved)
        console.print(
            Panel(
                f"[bold green]Downloaded:[/bold green]  [bold]{os.path.basename(saved)}[/bold]\n"
                f"[bold]Size:      [/bold]  {size_mb:.2f} MB\n"
                f"[bold]Location:  [/bold]  {abs_path}",
                title="[bold]✅ Download Completed[/bold]",
                border_style="green",
                padding=(1, 2),
            )
        )
    except Exception as exc:
        console.print(f"[red]❌ Error during download stream: {exc}[/red]")
        console.print(
            f"[dim]Fallback manual download link:[/dim]\n[cyan]{best_url}[/cyan]"
        )
        sys.exit(1)

    console.print("\n[bold green]Done! ✨[/bold green]\n")


if __name__ == "__main__":
    main()
