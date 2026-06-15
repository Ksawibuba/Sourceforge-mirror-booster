# 🚀 SourceForge Mirror Booster

## 🇺🇸 SourceForge Mirror Booster (English)

A fast, parallel CLI SourceForge mirror speed checker and downloader featuring a beautiful terminal user interface.

This tool automatically benchmarks available SourceForge mirrors in parallel, measures their connection latency and download speed using a sample chunk, and lets you download your files from the fastest node at maximum velocity.

### ✨ Features
- **Parallel Benchmarking:** Tests multiple mirrors simultaneously using thread pools for maximum efficiency.
- **Anti-Bot & Token Protection Bypass:** Automatically extracts and forwards live session tokens (`ts`, `fid`, etc.) to prevent protected or large file downloads from failing with HTTP 403 Forbidden errors.
- **Massive Embedded Database:** Contains a pre-configured array of 44 global mirrors as an instant fallback if the live list cannot be fetched online.
- **View All Mirrors:** Includes dedicated options to instantly list the entire 44-mirror internal database layout or display every single tested mirror (including failed/timed-out ones) in the final ranking table.
- **Beautiful Rich Terminal UI:** Powered by the `rich` library to display elegant real-time progress bars, tables, charts, and a sorted mirror leaderboard directly in your console.

### 📦 Installation
The script automatically detects and installs missing dependencies on startup. However, you can also install them manually beforehand:
```bash
pip install requests rich
```
If u want to check all of mirrors use this command

```bash
python3 szpons-eng.py --list-mirrors

```

