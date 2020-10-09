# Copyright 2020 Mike Purvis
# Copyright 2016-2020 Dirk Thomas
# Licensed under the Apache License, Version 2.0

import asyncio
import concurrent.futures
import os
import pathlib

from colcon_core.argument_default import is_default_value
from colcon_core.argument_default import wrap_default_value
from colcon_core.package_descriptor import PackageDescriptor
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
            tasks = set()
            def _add_task_paths(paths):
                for path in paths:
                    tasks.add(loop.run_in_executor(pool, _discover_path, identification_extensions, path))

            _add_task_paths(base_paths)
            package_descriptors = set()
            while tasks:
                completed, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in completed:
                    result = task.result()
                    if isinstance(result, PackageDescriptor):
                        package_descriptors.add(result)
                    elif isinstance(result, list):
                        _add_task_paths(result)
                    else:
                        assert result == None
            return package_descriptors

def _discover_path(identification_extensions, path):
    # If we find a package at this location, return it; otherwise return a list
    # of subdirectories found.
    try:
        result = identify(identification_extensions, path)
    except IgnoreLocationException:
        return None
    if result:
        return result

    with os.scandir(path) as scanner:
        return [entry.path for entry in scanner
            if entry.is_dir() and not entry.name.startswith('.')]
