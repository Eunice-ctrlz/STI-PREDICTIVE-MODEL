#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
if os.name == "nt":
    OSGEO4W = r"C:\OSGeo4W"
    os.add_dll_directory(OSGEO4W + r"\bin")
    from ctypes import CDLL
    CDLL(OSGEO4W + r"\bin\gdal313.dll")  # force-load GDAL before anything else can grab conflicting DLLs

import sys



def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
