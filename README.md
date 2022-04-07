# scanner-cli
A CLI for controlling scanners on MacOS

```
usage: scanner.py [-h] [--source {feeder,flatbed,automatic}] [--format {pdf,jpeg}] [--grayscale] [--resolution {75,100,200,300,600}]
                  [--debug] [--no-open]
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
```