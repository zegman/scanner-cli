
# scanner-cli
A MacOS/Linux CLI client for scanning documents using a network scanner supporting the [Mopria Alliance eSCL Scan Technical Specification](https://mopria.org/MopriaeSCLSpecDownload.php)

Known to work with at least:
- HP Deskjet 4640 series
- HP OfficeJet Pro 9010 series
- HP OfficeJet Pro 9120 series
- Canon Pixma G3260
- Brother MFC-L2710DW
- Brother DCP-L3550CDW

## Installation
```
pip install -f requirements.txt
```

## Usage
```
usage: scanner.py [-h] [--source {feeder,flatbed,automatic}] [--format {pdf,jpeg}] [--grayscale] [--resolution {75,100,200,300,600}] [--debug] [--no-open]
                  [--quiet] [--duplex]
                  filename

positional arguments:
  filename

optional arguments:
  -h, --help            show this help message and exit
  --source {feeder,flatbed,automatic}, -S {feeder,flatbed,automatic}
  --format {pdf,jpeg}, -f {pdf,jpeg}
  --grayscale, -g
  --resolution {75,100,200,300,600}, -r {75,100,200,300,600}
  --debug, -d
  --no-open, -o
  --quiet, -q
  --duplex, -D
  --today, -t           Prepend date to file name in ISO format
  --region, -R REGION   Specify a region to scan. Either a paper size as
                        understood by the papersize library
                        (https://papersize.readthedocs.io) or the format
                        "Xoffset:Yoffset:Width:Height", with units understood
                        by the papersize library. For example:
                        1cm:1.5cm:10cm:20cm
```

## Configuration

`scanner.py` reads an optional configuration file using [TOML](https://toml.io/). The lookup order is:

1. A path specified via the `SCANNER_CONFIG` environment variable.
2. `$XDG_CONFIG_HOME/scanner/config.toml` (or `~/.config/scanner/config.toml` when `XDG_CONFIG_HOME` is unset).
3. `%APPDATA%\scanner\config.toml` on Windows.

Only a `[defaults]` table is recognised. Keys map to CLI options and keep the same values and choices; command-line flags always win when provided. Supported keys are `source`, `format`, `resolution`, and `region`.

Example:

```toml
[defaults]
source = "feeder"
format = "pdf"
resolution = 300
region = "letter"
```
