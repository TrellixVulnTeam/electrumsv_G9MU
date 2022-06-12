# ElectrumSV - lightweight Bitcoin SV client
# Copyright (C) 2019-2020 The ElectrumSV Developers
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

'''Platform-specific customization for ElectrumSV'''

import os
import platform as os_platform
import sys
from typing import NoReturn, Type

from .i18n import _
from .logs import logs
from . import startup

logger = logs.get_logger("platform")


class Platform(object):

    module_map = {
        'PyQt6': 'PyQt6',
        'SimpleWebSocketServer': 'SimpleWebSocketServer',
        'dateutil': 'python-dateutil',
        'electrumsv_secp256k1': 'electrumsv-secp256k1',
        'qrcode': 'qrcode',
        'requests': 'requests',
    }
    libzbar_name = 'libzbar.so.0'
    monospace_font = 'monospace'
    name = 'unset platform'

    def user_dir(self, prefer_local: bool=False) -> str:
        home_dir = os.environ.get("HOME", ".")
        return os.path.join(home_dir, ".electrum-sv")

    def dbb_user_dir(self) -> str:
        '''User directory for digital bitbox plugin.'''
        return os.path.join(os.environ["HOME"], ".dbb")

    def missing_import(self, exception: ImportError) -> NoReturn:
        module = exception.name
        if module is not None:
            # Only hint about a missing import if the failure was a missing module.
            for m, package in self.module_map.items():
                # because submodule could be imported instead
                if module.startswith(m):
                    sys.exit(_('cannot import module "{0}" - try running "pip3 install {1}"'
                            .format(module, package)))
        raise exception from None

    def extra_libzbar_paths(self) -> list[str]:
        return []


class Darwin(Platform):
    libzbar_name = 'libzbar.dylib'
    monospace_font = 'Monaco'
    name = 'MacOSX'

    def dbb_user_dir(self) -> str:
        return os.path.join(os.environ.get("HOME", ""), "Library", "Application Support", "DBB")


class Linux(Platform):
    name = 'Linux'


class Unix(Platform):
    name = 'Unix'


class Windows(Platform):
    libzbar_name = 'libzbar-0.dll'
    monospace_font = 'Consolas'
    name = 'Windows'

    def user_dir(self, prefer_local: bool=False) -> str:
        app_dir = os.environ.get("APPDATA")
        localapp_dir = os.environ.get("LOCALAPPDATA")
        if not app_dir or (localapp_dir and prefer_local):
            app_dir = localapp_dir
        return os.path.join(app_dir or ".", "ElectrumSV")

    def dbb_user_dir(self) -> str:
        return os.path.join(os.environ["APPDATA"], "DBB")

    def extra_libzbar_paths(self) -> list[str]:
        if not getattr(sys, "frozen", False):
            dll_path = os.path.join(startup.base_dir, "contrib", "build-windows", "prebuilt")
            if os.path.exists(dll_path):
                return [ dll_path ]
        return []


def _detect() -> Platform:
    system = os_platform.system()
    cls: Type[Platform]
    if system == 'Darwin':
        cls = Darwin
    elif system == 'Linux':
        cls = Linux
    elif system == 'Windows':
        cls = Windows
    elif system in ('FreeBSD', 'NetBSD', 'OpenBSD', 'DragonFly'):
        cls = Unix
    else:
        logger.warning(_('unknown system "{}"; falling back to Unix.  Please report this.')
                       .format(system))
        cls = Unix
    logs.root.debug(f'using platform class {cls.__name__} for system "{system}"')
    return cls()


platform = _detect()
