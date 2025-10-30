"""PyInstaller build script."""

import shutil
from pathlib import Path

import PyInstaller.__main__

HERE = Path(__file__).parent.absolute()
path_to_main = str(HERE / "poemarcut.py")


def install() -> None:
    """Build release executable using PyInstaller and package it + config file into a zip file."""
    # clean up old dist directory
    if (HERE / "dist").exists():
        shutil.rmtree(HERE / "dist")

    # build exe with pyinstaller
    PyInstaller.__main__.run(
        [
            path_to_main,
            "--onefile",
            "--icon=icon.ico",
            #'--add-data', # ---add-data is apparently not intended for enduser-editable files
            #'*.yaml' + os.pathsep + 'dist',
        ]
    )

    # copy yaml files to dist directly instead
    shutil.copy(HERE / "settings.yaml", HERE / "dist")

    # make a zip of the dist directory contents
    shutil.make_archive(base_name="poemarcut", format="zip", root_dir=HERE / "dist")
    shutil.move(HERE / "poemarcut.zip", HERE / "dist")
