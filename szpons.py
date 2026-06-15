#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SourceForge Mirror Speed Checker
=================================
Sprawdza dostępne mirrory SourceForge i wybiera najszybszy do pobrania.
"""

import sys
import time
import re
import os
import argparse
import concurrent.futures
import subprocess
import urllib.parse


# ─── Auto-install wymaganych pakietów ────────────────────────────────────────


def _ensure_packages():
    for pkg in ["requests", "rich"]:
        try:
            __import__(pkg)
        except ImportError:
            print(f"[setup] Instaluję pakiet: {pkg}...")
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

# ─── Stałe ───────────────────────────────────────────────────────────────────

DEFAULT_WORKERS = 6  # ile mirrorów testować jednocześnie
DEFAULT_TEST_KB = 512  # ile KB pobierać przy teście szybkości
REQUEST_TIMEOUT = (5, 12)  # (connect, read) timeout w sekundach

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8",
}

# Maksymalnie rozbudowana, globalna lista znanych mirrorów SourceForge
FALLBACK_MIRRORS = [
    # Najważniejsze i najszybsze w Europie / blisko nas
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
    # Ameryka Północna (USA / Kanada)
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
    # Azja / Australia / Reszta Świata
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


# ─── Parsowanie URL ───────────────────────────────────────────────────────────


def parse_sf_url(url: str) -> dict | None:
    """
    Wyciąga projekt, oryginalną zakodowaną ścieżkę oraz tokeny (query string).
    """
    url = url.strip()

    # Wyciągamy query string (tokeny typu ts=..., fid=...) jeśli istnieją
    query = url.split("?")[1] if "?" in url else ""

    # 1. Format standardowej strony pobierania projektu
    m_proj = re.search(
        r"sourceforge\.net/projects/([^/]+)/files/([^?#]+)", url, re.IGNORECASE
    )
    if m_proj:
        project = m_proj.group(1)
        raw_path = m_proj.group(2)
        if raw_path.lower().endswith("/download"):
            raw_path = raw_path[:-9].rstrip("/")
        return {"project": project, "raw_path": raw_path, "query": query}

    # 2. Format bezpośrednich linków (downloads lub subdomeny mirrorów)
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


# ─── Pobieranie listy mirrorów ────────────────────────────────────────────────


def get_mirrors(project: str, raw_path: str) -> list[str]:
    """
    Pobiera listę mirrorów z HTML strony pobierania SourceForge.
    Przy błędzie wraca do rozbudowanej listy zapasowej.
    """
    url = f"https://sourceforge.net/projects/{project}/files/{raw_path}/download"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        r.raise_for_status()

        # Szukamy kodów mirrorów w HTML
        found = list(dict.fromkeys(re.findall(r"use_mirror=([a-z0-9\-]+)", r.text)))

        if len(found) >= 2:
            return found

        console.print(
            "[yellow]⚠  Nie znaleziono mirrorów na stronie – używam pełnej listy zapasowej.[/yellow]"
        )

    except Exception:
        console.print(
            "[yellow]⚠  Błąd pobierania strony (brak dostępu do listy online) – używam pełnej listy zapasowej.[/yellow]"
        )

    return FALLBACK_MIRRORS


# ─── Test szybkości ───────────────────────────────────────────────────────────


def test_mirror(
    code: str, project: str, raw_path: str, query: str, test_kb: int
) -> dict:
    """
    Sprawdza jeden mirror, dołączając oryginalne tokeny autoryzacyjne sesji.
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

        # Pobierz próbkę danych
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


# ─── Pobieranie pliku ─────────────────────────────────────────────────────────


def download_file(
    project: str, raw_path: str, query: str, mirror_code: str, output_dir: str
) -> str:
    """Pobiera plik z wybranego mirrora z paskiem postępu."""
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
            f"Pobieranie [cyan]{os.path.basename(filename)}[/cyan]...",
            total=total or None,
        )
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                progress.advance(task, len(chunk))

    return filename


# ─── Główna logika ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="SourceForge Mirror Speed Checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="URL pliku na SourceForge")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        metavar="N",
        help=f"Równoległe testy mirrorów (domyślnie: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--test-kb",
        type=int,
        default=DEFAULT_TEST_KB,
        metavar="KB",
        help=f"Rozmiar próbki do testu szybkości w KB (domyślnie: {DEFAULT_TEST_KB})",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        metavar="FOLDER",
        help="Folder docelowy pobrania (domyślnie: bieżący)",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Pokazuje absolutnie wszystkie przetestowane mirrory w tabeli (wyłącza skracanie błędów)",
    )
    parser.add_argument(
        "--list-mirrors",
        action="store_true",
        help="Wypisuje pełną lista wbudowanych mirrorów SourceForge i kończy działanie",
    )
    args = parser.parse_args()

    # Wyświetlanie wbudowanej bazy danych mirrorów i natychmiastowe wyjście
    if args.list_mirrors:
        console.print(
            Panel(
                Align.center(
                    f"[bold cyan]Baza wbudowanych mirrorów SourceForge ({len(FALLBACK_MIRRORS)} pozycji)[/bold cyan]"
                ),
                border_style="cyan",
            )
        )
        console.print(Columns(FALLBACK_MIRRORS, equal=True, padding=(0, 2)))
        console.print()
        sys.exit(0)

    # ── Banner ──
    console.print(
        Panel(
            Align.center(
                "[bold cyan]SourceForge Mirror Speed Checker[/bold cyan]\n"
                "[dim]Testuje mirrory i wybiera najszybszy do pobrania[/dim]"
            ),
            border_style="cyan",
            padding=(1, 6),
        )
    )

    url = args.url
    if not url:
        console.print(
            "\n[dim]Przykładowy link:[/dim]\n"
            "[dim]https://sourceforge.net/projects/sevenzip/files/"
            "7-Zip/24.09/7z2409-x64.exe/download[/dim]\n"
        )
        url = console.input(
            "[bold cyan]🔗 Podaj link do pliku SF:[/bold cyan] "
        ).strip()

    if not url:
        console.print("[red]❌ Nie podano URL![/red]")
        sys.exit(1)

    parsed = parse_sf_url(url)
    if not parsed:
        console.print(
            "[red]❌ Nie rozpoznano URL SourceForge.[/red]\n"
            "[dim]Akceptowane formaty:\n"
            "  https://sourceforge.net/projects/{projekt}/files/{plik}/download\n"
            "  https://downloads.sourceforge.net/project/{projekt}/{plik}\n"
            "  https://{mirror}.dl.sourceforge.net/project/{projekt}/{plik}[/dim]"
        )
        sys.exit(1)

    project = parsed["project"]
    raw_path = parsed["raw_path"]
    query = parsed["query"]
    filename = urllib.parse.unquote(raw_path.split("/")[-1])

    console.print(f"\n[green]✓[/green] Projekt: [bold]{project}[/bold]")
    console.print(f"[green]✓[/green] Plik:    [bold]{filename}[/bold]")

    console.print("\n[cyan]⏳ Pobieram listę mirrorów...[/cyan]")
    mirrors = get_mirrors(project, raw_path)
    console.print(
        f"[green]✓[/green] Załadowano [bold]{len(mirrors)}[/bold] mirrorów do przetestowania.\n"
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
            "[cyan]Testuję szybkość mirrorów...[/cyan]",
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
            "[red]❌ Żaden mirror nie odpowiedział poprawnie. Token wygasł lub link jest błędny.[/red]"
        )
        sys.exit(1)

    console.print()
    tbl = Table(
        title=f"[bold]Ranking mirrorów – {filename}[/bold]",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    tbl.add_column("#", justify="center", width=5)
    tbl.add_column("Mirror", style="white", min_width=16)
    tbl.add_column("Szybkość", justify="right", min_width=11)
    tbl.add_column("Pasek", justify="left", min_width=20)
    tbl.add_column("Latencja", justify="right", min_width=9)
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

    # Wyświetlanie błędów: albo wszystkie (flaga --show-all), albo tylko pierwsze 4
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
            f"[dim]… i {len(failed_results) - 4} więcej błędów (uruchom skrypt z --show-all, aby zobaczyć wszystkie)[/dim]",
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
            f"[bold]Szybkość:[/bold] [bold green]{best['speed_mbps']:.2f} MB/s[/bold green]"
            + (
                f"   |   Latencja: {best['latency_ms']:.0f} ms"
                if best.get("latency_ms")
                else ""
            )
            + f"\n[bold]Link:    [/bold][dim]{best_url}[/dim]",
            title="[bold]🏆 Najszybszy mirror[/bold]",
            border_style="green",
            padding=(1, 2),
        )
    )

    console.print()
    try:
        choice = (
            console.input("[bold]Pobrać plik teraz? ([cyan]T[/cyan]/n): [/bold]")
            .strip()
            .lower()
        )
    except (EOFError, KeyboardInterrupt):
        choice = "n"

    if choice in ("", "t", "tak", "y", "yes"):
        os.makedirs(args.output_dir, exist_ok=True)
        console.print()
        try:
            saved = download_file(
                project, raw_path, query, best["code"], args.output_dir
            )
            size_mb = os.path.getsize(saved) / (1024 * 1024)
            abs_path = os.path.abspath(saved)
            console.print(
                Panel(
                    f"[bold green]Pobrano:[/bold green]  [bold]{os.path.basename(saved)}[/bold]\n"
                    f"[bold]Rozmiar:[/bold]  {size_mb:.2f} MB\n"
                    f"[bold]Lokalizacja:[/bold] {abs_path}",
                    title="[bold]✅ Pobieranie zakończone[/bold]",
                    border_style="green",
                    padding=(1, 2),
                )
            )
        except Exception as exc:
            console.print(f"[red]❌ Błąd podczas pobierania: {exc}[/red]")
            console.print(f"[dim]Możesz pobrać ręcznie:[/dim]\n[cyan]{best_url}[/cyan]")
            sys.exit(1)
    else:
        console.print(f"\n[dim]Link do ręcznego pobrania:[/dim]")
        console.print(f"[cyan]{best_url}[/cyan]")

    console.print("\n[bold green]Gotowe! ✨[/bold green]\n")


if __name__ == "__main__":
    main()
