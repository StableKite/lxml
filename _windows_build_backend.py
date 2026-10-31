"""Original lxml source backend with a pinned, local Windows CPython 3.15t SDK."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import sysconfig
import tempfile
from urllib.request import urlopen
import zipfile
from typing import Any, Generator, cast

from setuptools import build_meta

ROOT = Path(__file__).resolve().parent
SDK_MANIFEST = ROOT / 'windows_build_sdk.json'
CONTROLS = (
    'STATIC_DEPS', 'STATICBUILD', 'STATIC', 'LIBXML2_VERSION', 'LIBXSLT_VERSION',
    'LIBICONV_VERSION', 'ZLIB_VERSION', 'DOWNLOAD_DIR', 'LXML_STATIC_INCLUDE_DIRS',
    'LXML_STATIC_LIBRARY_DIRS', 'LXML_STATIC_CFLAGS', 'LXML_STATIC_BINARIES',
)


def _verified_archive(path: Path, asset: dict[str, Any]) -> bool:
    if not path.is_file() or path.stat().st_size != asset['bytes']:
        return False
    if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
        return False
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            name = item.filename
            relative = PurePosixPath(name)
            if (relative.is_absolute() or '..' in relative.parts or '\\' in name
                    or ':' in name or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError('Unsafe SDK archive entry: ' + name)
        if archive.testzip() is not None:
            raise ValueError('SDK archive CRC mismatch: ' + str(path))
    return True


def _sdk_directory() -> tuple[Path, dict[str, Any]]:
    data = cast(dict[str, Any], json.loads(SDK_MANIFEST.read_text(encoding='utf8')))
    destination = ROOT / 'libs' / 'cp315t-win64-' / data['release']
    destination.mkdir(parents=True, exist_ok=True)
    for asset in data['assets']:
        target = destination / asset['filename']
        if _verified_archive(target, asset):
            continue
        descriptor, temporary = tempfile.mkstemp(prefix='sdk-', suffix='.zip', dir=destination)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, 'wb') as output, urlopen(asset['url'], timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if not _verified_archive(temporary_path, asset):
                raise ValueError('SDK download digest/size mismatch: ' + asset['filename'])
            temporary_path.replace(target)
        finally:
            temporary_path.unlink(missing_ok=True)
    return destination, data


def _compiler_environment(toolset: str) -> dict[str, str]:
    # The official static SDK contains MSVC /GL objects and requires its toolset.
    installer = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))
    vswhere = installer / 'Microsoft Visual Studio/Installer/vswhere.exe'
    result = subprocess.run(
        [str(vswhere), '-latest', '-products', '*', '-requires',
         'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'],
        capture_output=True, text=True, check=True, timeout=30)
    vcvars = Path(result.stdout.strip()) / 'VC/Auxiliary/Build/vcvarsall.bat'
    if not vcvars.is_file() or any(char in str(vcvars) for char in '\"&|^\r\n'):
        raise RuntimeError('A valid Visual Studio C++ installation is required for source builds')
    if not re.fullmatch(r'[0-9]+\.[0-9]+', toolset):
        raise ValueError('Invalid pinned MSVC toolset')
    comspec = os.environ.get('COMSPEC', 'C:/Windows/System32/cmd.exe')
    if any(char in comspec for char in '\"&|^\r\n'):
        raise ValueError('Invalid command processor path')
    command = f'"{comspec}" /d /s /c ""{vcvars}" x64 -vcvars_ver={toolset} >nul && set"'
    result = subprocess.run(
        command,
        capture_output=True, text=True, timeout=120)
    # Never expose the full environment captured from vcvars.
    if result.returncode:
        raise RuntimeError('The official SDK requires installed MSVC toolset ' + toolset)
    allowed = {'path', 'include', 'lib', 'libpath', 'vctoolsversion', 'vcinstalldir',
               'vsinstalldir', 'windowssdkdir', 'windowssdkversion', 'ucrtversion',
               'vctoolsinstalldir', 'visualstudioversion', 'universalcrtsdkdir',
               'vscmd_arg_tgt_arch', 'vscmd_arg_host_arch'}
    updates: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition('=')
        if separator and key.lower() in allowed:
            updates[key] = value
    version = next((v for k, v in updates.items() if k.lower() == 'vctoolsversion'), '')
    if not version.startswith(toolset + '.'):
        raise RuntimeError('The selected MSVC version does not match the official SDK')
    updates['DISTUTILS_USE_SDK'] = '1'
    return updates


@contextmanager
def _environment() -> Generator[None, None, None]:
    use_sdk = (sys.platform == 'win32' and sys.version_info[:2] == (3, 15)
               and sysconfig.get_config_var('Py_GIL_DISABLED')
               and sysconfig.get_platform() == 'win-amd64'
               and not any(os.environ.get(name) for name in CONTROLS))
    if not use_sdk:
        yield
        return
    destination, data = _sdk_directory()
    updates = {'STATIC_DEPS': 'true', 'DOWNLOAD_DIR': str(destination), 'LXML_CSTD': 'c11'}
    updates.update(data['versions'])
    updates.update(_compiler_environment(data['msvc_toolset']))
    previous = {name: os.environ.get(name) for name in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def get_requires_for_build_wheel(config_settings: dict[str, Any] | None = None) -> list[str]:
    with _environment():
        return build_meta.__legacy__.get_requires_for_build_wheel(config_settings)


def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings: dict[str, Any] | None = None) -> str:
    with _environment():
        return build_meta.__legacy__.prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def build_wheel(wheel_directory: str, config_settings: dict[str, Any] | None = None, metadata_directory: str | None = None) -> str:
    with _environment():
        return build_meta.__legacy__.build_wheel(wheel_directory, config_settings, metadata_directory)


get_requires_for_build_sdist = build_meta.__legacy__.get_requires_for_build_sdist
build_sdist = build_meta.__legacy__.build_sdist
