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

If u want to check all of mirrors use this command
```bash
python3 szpons-eng.py --list-mirrors

```
## 🇵🇱 SourceForge Mirror Booster (Po Polsku)

Szybki, współbieżny program CLI do sprawdzania prędkości mirrorów SourceForge i pobierania plików, wyposażony w estetyczny interfejs graficzny w terminalu.

Narzędzie automatycznie testuje dostępne serwery lustrzane (mirrory) SourceForge w tym samym czasie, mierzy ich opóźnienia oraz prędkość pobierania na podstawie małej próbki, a następnie pozwala na pobranie pliku z najszybszego węzła z maksymalną prędkością.

### ✨ Funkcje
- **Równoległe testowanie:** Sprawdza wiele mirrorów jednocześnie przy użyciu puli wątków, zapewniając maksymalną wydajność.
- **Obejście blokad anty-botowych i tokenów:** Automatycznie wyciąga i przekazuje aktywne tokeny sesyjne (`ts`, `fid` itp.), dzięki czemu pobieranie dużych lub zabezpieczonych plików nie kończy się błędem HTTP 403 Forbidden.
- **Ogromna wbudowana baza:** Zawiera prekonfigurowaną listę 44 globalnych mirrorów jako koło ratunkowe, jeśli lista online nie może zostać pobrana.
- **Podgląd wszystkich mirrorów:** Oferuje dedykowane opcje pozwalające na natychmiastowe wyświetlenie całej wbudowanej bazy 44 serwerów lub pokazanie pełnej listy przetestowanych mirrorów (w tym tych, które zwróciły błąd lub przekroczyły czas połączenia) w tabeli końcowej.
- **Piękny interfejs Rich UI:** Wykorzystuje bibliotekę `rich` do wyświetlania animowanych pasków postępu, tabel, wykresów i posortowanego rankingu mirrorów bezpośrednio w konsoli.

### 📦 Instalacja
Skrypt automatycznie wykrywa i instaluje brakujące pakiety przy uruchomieniu. Możesz je także zainstalować ręcznie przed uruchomieniem:
```bash
pip install requests rich

Jezeli chcesz zobaczyc wszystkie mirrory to uzyj tej komendy 
```bash
python3 szpons.py --list-mirrors
