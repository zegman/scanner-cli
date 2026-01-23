#!/usr/bin/env python
# pylint: disable=missing-module-docstring
from __future__ import annotations

# pylint: disable=missing-module-docstring, missing-function-docstring
# pylint: disable=too-many-locals, too-many-branches, bare-except
# pylint: disable=too-many-statements, missing-class-docstring

import argparse
import sys
import json
import time
import subprocess
import os
import datetime
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Set, Tuple
from pathlib import Path

import papersize
import requests
import xmltodict
import zeroconf

try:
    import tomllib as TOML_LIB  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    try:
        import tomli as TOML_LIB
    except ModuleNotFoundError:
        TOML_LIB = None  # type: ignore[assignment]


CONFIG_ENV_VAR = 'SCANNER_CONFIG'
CONFIG_DIRNAME = 'scanner'
CONFIG_FILENAME = 'config.toml'
CONFIGURABLE_ARGUMENT_KEYS: Set[str] = {
    'source',
    'format',
    'resolution',
    'region',
}


def get_config_path() -> Optional[Path]:
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path).expanduser()

    if os.name == 'nt':
        appdata = os.environ.get('APPDATA')
        if not appdata:
            return None
        return Path(appdata) / CONFIG_DIRNAME / CONFIG_FILENAME

    config_home = os.environ.get('XDG_CONFIG_HOME')
    if config_home:
        config_home_path = Path(config_home)
    else:
        config_home_path = Path.home() / '.config'
    return config_home_path / CONFIG_DIRNAME / CONFIG_FILENAME


def load_config_defaults(valid_keys: Set[str]) -> Dict[str, Any]:
    config_path = get_config_path()
    if not config_path or not config_path.is_file():
        return {}

    if TOML_LIB is None:
        print(
            'Configuration file support requires the "tomli" package for '
            'Python versions earlier than 3.11.',
            file=sys.stderr,
        )
        sys.exit(1)

    decode_error_cls = getattr(TOML_LIB, 'TOMLDecodeError', ValueError)

    try:
        with config_path.open('rb') as config_file:
            config_data = TOML_LIB.load(config_file)
    except OSError as exc:
        print(f'Failed to read config file {config_path}: {exc}', file=sys.stderr)
        sys.exit(1)
    except (decode_error_cls, ValueError) as exc:
        print(f'Failed to parse config file {config_path}: {exc}', file=sys.stderr)
        sys.exit(1)

    defaults_section = config_data.get('defaults', {})
    if defaults_section is None:
        return {}
    if not isinstance(defaults_section, dict):
        print(
            f'Invalid config file {config_path}: [defaults] must be a table',
            file=sys.stderr,
        )
        sys.exit(1)

    filtered: Dict[str, Any] = {}
    unknown_keys = []
    for key, value in defaults_section.items():
        if key in valid_keys:
            filtered[key] = value
        else:
            unknown_keys.append(key)

    if unknown_keys:
        print(
            f'Ignoring unknown config option(s) in {config_path}: '
            f"{', '.join(sorted(unknown_keys))}",
            file=sys.stderr,
        )

    return filtered



# See: https://mopria.org/MopriaeSCLSpecDownload.php


def resolve_scanner() -> Optional[zeroconf.ServiceInfo]:
    class ZCListener:
        def __init__(self) -> None:
            self.info: Optional[zeroconf.ServiceInfo] = None

        def update_service(self, _zc: zeroconf.Zeroconf, _type: str, _name: str) -> None:
            pass

        def remove_service(self, _zc: zeroconf.Zeroconf, _type: str, _name: str) -> None:
            pass

        def add_service(self, _zc: zeroconf.Zeroconf, _type: str, name: str) -> None:
            self.info = _zc.get_service_info(_type, name)
    with zeroconf.Zeroconf() as zc:
        listener = ZCListener()
        zeroconf.ServiceBrowser(
            zc, "_uscan._tcp.local.", listener=listener)
        try:
            for _ in range(0, 10 * 10):
                if listener.info:
                    break
                time.sleep(.1)
        except:
            pass
    return listener.info


def parse_region(region_spec: str) -> Dict[str, int]:
    region_spec = region_spec.lower()
    try:
        if region_spec in papersize.SIZES:
            paper_size = papersize.parse_papersize(region_spec)
            region_decimals: Dict[str, Decimal] = {
                'x': Decimal('0'),
                'y': Decimal('0'),
                'width': paper_size[0],
                'height': paper_size[1],
            }
        else:
            parts = region_spec.split(':')
            if len(parts) != 4:
                raise papersize.CouldNotParse(region_spec)
            parsed_parts = [papersize.parse_length(p) for p in parts]
            region_decimals = {
                'x': parsed_parts[0],
                'y': parsed_parts[1],
                'width': parsed_parts[2],
                'height': parsed_parts[3],
            }
    except papersize.CouldNotParse:
        print(f'Could not parse {region_spec}', file=sys.stderr)
        sys.exit(1)

    c: Decimal = papersize.UNITS['in'] / 300  # ThreeHundredthsOfInches
    region_ints: Dict[str, int] = {k: int(v / c) for k, v in region_decimals.items()}
    return region_ints


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--source', '-S',
        choices=['feeder', 'flatbed', 'automatic'], default='automatic')
    parser.add_argument(
        '--format', '-f', choices=['pdf', 'jpeg'], default='pdf')
    parser.add_argument('--grayscale', '-g', action='store_true')
    parser.add_argument(
        '--resolution', '-r', type=int, default=200,
        choices=[75, 100, 200, 300, 600])
    parser.add_argument('--debug', '-d', action='store_true')
    parser.add_argument('--no-open', '-o', action='store_false', dest='open')
    parser.add_argument('--quiet', '-q', action='store_true')
    parser.add_argument('--duplex', '-D', action='store_true')
    parser.add_argument('--today', '-t', action='store_true',
                        help='Prepend date to file name in ISO format')
    parser.add_argument(
        '--region', '-R',
        help='Specify a region to scan. Either a paper size as understood by '
            'the papersize library (https://papersize.readthedocs.io) or the format '
            '"Xoffset:Yoffset:Width:Height", with units understood by the '
            'papersize library. For example: 1cm:1.5cm:10cm:20cm')
    parser.add_argument('filename')

    config_defaults = load_config_defaults(CONFIGURABLE_ARGUMENT_KEYS)
    if config_defaults:
        parser.set_defaults(**config_defaults)

    args = parser.parse_args()

    if args.today:
        args.filename = (
            datetime.date.today().isoformat() + '-' + args.filename)

    basename, fsuffix = os.path.splitext(args.filename)
    if args.format == 'jpeg':
        if fsuffix not in {'', '.jpeg', '.jpg'}:
            print(f'Improper file suffix {fsuffix}', file=sys.stderr)
            sys.exit(1)
        if fsuffix == '':
            fsuffix = '.jpg'

    region: Dict[str, int] = {}
    if args.region:
        region = parse_region(args.region)

    info = resolve_scanner()
    if not info:
        print('No scanner found')
        sys.exit(1)
    props: Mapping[bytes, bytes] = info.properties
    if not args.quiet:
        suffix = '._uscan._tcp.local.'
        name = info.name
        if info.name.endswith(suffix):
            name = info.name[:-len(suffix)]
        print(f'Using {name}')
    if args.duplex and props[b'duplex'] != b'T':
        print('Duplex not supported', file=sys.stderr)
        sys.exit(1)

    session = requests.Session()

    if args.debug:
        print(info, file=sys.stderr)

    rs = props[b'rs'].decode()
    if rs[0] != '/':
        rs = '/' + rs
    base_url = f'http://{info.server}:{info.port}{rs}'
    if args.debug:
        print(base_url, file=sys.stderr)

    def get_status(
        job_uuid: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        resp = session.get(f'{base_url}/ScannerStatus')
        resp.raise_for_status()
        status: Dict[str, Any] = xmltodict.parse(
            resp.text, force_list=('scan:JobInfo', ))['scan:ScannerStatus']
        if job_uuid is None:
            return status, None

        uuid_prefix = "urn:uuid:"  # Seen in a Brother MFC device
        for jobinfo in status['scan:Jobs']['scan:JobInfo']:
            current_uuid: str = jobinfo['pwg:JobUuid']
            if current_uuid.startswith(uuid_prefix):
                current_uuid = current_uuid[len(uuid_prefix):]

            if current_uuid == job_uuid:
                return status, jobinfo
        raise RuntimeError('Job not found')

    resp = session.get(f'{base_url}/ScannerCapabilities')
    resp.raise_for_status()
    if args.debug:
        print(resp.text, file=sys.stderr)

    status, _ = get_status()
    if status['pwg:State'] != 'Idle':
        print('Scanner is not idle', file=sys.stderr)
        return 1

    source = {
        'automatic': '',
        'feeder': '<pwg:InputSource>Feeder</pwg:InputSource>',
        'flatbed': '<pwg:InputSource>Platen</pwg:InputSource>',
    }[args.source]
    doc_format = {
        'pdf': 'application/pdf',
        'jpeg': 'image/jpeg',
    }[args.format]

    if args.grayscale:
        color = 'Grayscale8'
    else:
        color = 'RGB24'

    job = f'''
    <?xml version="1.0" encoding="UTF-8"?>
    <scan:ScanSettings xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03"
      xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
      <pwg:Version>2.0</pwg:Version>
      <scan:Intent>TextAndGraphic</scan:Intent>
      <pwg:DocumentFormat>{doc_format}</pwg:DocumentFormat>
      {source}
      <scan:ColorMode>{color}</scan:ColorMode>
      <scan:Duplex>{str(args.duplex).lower()}</scan:Duplex>
      <scan:XResolution>{args.resolution}</scan:XResolution>
      <scan:YResolution>{args.resolution}</scan:YResolution>
    '''
    if region:
        job += f'''
          <pwg:ScanRegions>
            <pwg:ScanRegion>
              <pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>
              <pwg:XOffset>{region['x']}</pwg:XOffset>
              <pwg:YOffset>{region['y']}</pwg:YOffset>
              <pwg:Width>{region['width']}</pwg:Width>
              <pwg:Height>{region['height']}</pwg:Height>
            </pwg:ScanRegion>
          </pwg:ScanRegions>
        '''
    job += '</scan:ScanSettings>'
    if args.debug:
        print(job, file=sys.stderr)
    resp = session.post(f'{base_url}/ScanJobs', data=job)
    resp.raise_for_status()

    job_uri = resp.headers['location']
    job_uuid = job_uri.split('/')[-1]
    page = 1
    while True:
        status, jobinfo = get_status(job_uuid=job_uuid)
        if args.debug:
            print(json.dumps(jobinfo, indent=2), file=sys.stderr)

        retry_count = 0
        while True:
            resp = session.get(f'{job_uri}/NextDocument')
            if resp.status_code != 503:
                break
            retry_count += 1
            if args.debug:
                print(
                    f'503 from NextDocument (attempt {retry_count})',
                    file=sys.stderr,
                )
                print(resp.text, file=sys.stderr)
            if retry_count >= 100:
                print('Scanner returned 503 for NextDocument', file=sys.stderr)
                print(resp.text, file=sys.stderr)
                resp.raise_for_status()
            time.sleep(1)

        if resp.status_code == 404:
            # We are done
            break
        resp.raise_for_status()

        if args.format == 'pdf':
            with open(args.filename, 'wb') as f:
                f.write(resp.content)
        else:
            with open(f'{basename}-{page}{fsuffix}', 'wb') as f:
                f.write(resp.content)
            page += 1
        if status['pwg:State'] != 'Processing':
            break
        time.sleep(1)

    status, jobinfo = get_status(job_uuid=job_uuid)
    job_reason = jobinfo['pwg:JobStateReasons']['pwg:JobStateReason']
    if args.debug:
        print(job_reason, file=sys.stderr)
    if job_reason != 'JobCompletedSuccessfully':
        return 1

    if args.open:
        if args.format == 'pdf':
            subprocess.run(['open', args.filename], check=False)
        else:
            subprocess.run(['open', f'{basename}-1{fsuffix}'], check=False)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
