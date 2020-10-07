# Copyright 2020 Mike Purvis
# Copyright 2016-2020 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import asyncio
import concurrent.futures
import os
import pathlib

from colcon_core.argument_default import is_default_value
from colcon_core.argument_default import wrap_default_value
from colcon_core.package_discovery import logger
from colcon_core.package_discovery import PackageDiscoveryExtensionPoint
from colcon_core.package_identification import identify
from colcon_core.package_identification import IgnoreLocationException
from colcon_core.plugin_system import satisfies_version


class MultiProcessRecursiveDiscoveryExtension(PackageDiscoveryExtensionPoint):
    """Crawl paths recursively for packages."""

    # the priority needs to be higher than the path based discovery extension
    # so that when no arguments are provided this extension is the default
    PRIORITY = 120

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            PackageDiscoveryExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def has_default(self):  # noqa: D102
        return True

    def add_arguments(self, *, parser, with_default):  # noqa: D102
        parser.add_argument(
            '--mp-base-paths',
            nargs='*',
            metavar='PATH',
            default=wrap_default_value(['.']) if with_default else None,
            help='The base paths to recursively crawl for packages' +
                 (' (default: .)' if with_default else ''))

    def has_parameters(self, *, args):  # noqa: D102
        return not is_default_value(args.mp_base_paths) and \
            bool(args.mp_base_paths)

    def discover(self, *, args, identification_extensions):  # noqa: D102
        if args.mp_base_paths is None:
            return set()
        return asyncio.run(self._discover(args.mp_base_paths, identification_extensions))

    async def _discover(self, base_paths, identification_extensions):
        logger.info(
            'Beginning multiprocess recursive crawl for packages in %s',
            ', '.join([
                "'%s'" % os.path.abspath(p) for p in base_paths
            ]))

        loop = asyncio.get_event_loop()
        with concurrent.futures.ProcessPoolExecutor() as pool:
            async def _discover_path(path):
                try:
                    result = await loop.run_in_executor(pool, identify, identification_extensions, path)
                except IgnoreLocationException:
                    return set()
                if result:
                    return set((result,))

                def subdirs():
                    with os.scandir(path) as scanner:
                        for entry in scanner:
                            if entry.is_dir() and not entry.name.startswith('.'):
                                yield path / entry.name
                subdir_results = await _discover_paths(subdirs())
                return set().union(subdir_results)

            async def _discover_paths(paths):
                dir_results = await asyncio.gather(*[_discover_path(p) for p in paths])
                return set().union(*dir_results)

            return await _discover_paths(pathlib.Path(p) for p in base_paths)
