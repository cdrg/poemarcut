"""PyInstaller build script."""

import os
import shutil
from pathlib import Path

import PyInstaller.__main__

SRC_ROOT = Path(__file__).parent.absolute()
PROJ_ROOT = SRC_ROOT.parent.absolute()

path_to_main = str(SRC_ROOT / "poemarcut_gui.py")


def install() -> None:
    """Build release executable using PyInstaller and package it + config file into a zip file.

    Returns:
        None

    """
    # delete contents of existing dist directory so it's clean
    if (PROJ_ROOT / "dist").exists():
        shutil.rmtree(PROJ_ROOT / "dist")

    # build exe with pyinstaller
    PyInstaller.__main__.run(
        [
            path_to_main,
            "--onefile",
            "--noconsole",
            "--workpath=" + str(PROJ_ROOT / "build"),
            "--distpath=" + str(PROJ_ROOT / "dist"),
            "--icon=" + str(PROJ_ROOT / "assets" / "icon.ico"),
            "--add-data=" + str(PROJ_ROOT / "assets" / "icon.ico") + os.pathsep + "assets",
            "--add-data=" + str(PROJ_ROOT / "assets" / "gear.ico") + os.pathsep + "assets",
            "--add-data=" + str(PROJ_ROOT / "assets" / "Fontin-Bold.otf") + os.pathsep + "assets",
            "--add-data=" + str(PROJ_ROOT / "assets" / "Fontin-Italic.otf") + os.pathsep + "assets",
            "--add-data=" + str(PROJ_ROOT / "assets" / "Fontin-Regular.otf") + os.pathsep + "assets",
            "--add-data=" + str(PROJ_ROOT / "assets" / "Fontin-SmallCaps.otf") + os.pathsep + "assets",
        ]
    )

    # make a zip of the dist directory contents. need to create in other dir then move or the zip will contain itself.
    shutil.make_archive(base_name="poemarcut", format="zip", root_dir=PROJ_ROOT / "dist")
    shutil.move("poemarcut.zip", PROJ_ROOT / "dist")
