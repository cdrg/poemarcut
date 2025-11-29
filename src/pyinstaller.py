"""PyInstaller build script."""

import shutil
from pathlib import Path

import PyInstaller.__main__

PROJ_ROOT = Path(__file__).parent.parent.absolute()
path_to_main = str(PROJ_ROOT / "src" / "poemarcut.py")


def install() -> None:
    """Build release executable using PyInstaller and package it + config file into a zip file."""
    # delete contents of existing dist directory so it's clean
    if (PROJ_ROOT / "dist").exists():
        shutil.rmtree(PROJ_ROOT / "dist")

    # build exe with pyinstaller
    PyInstaller.__main__.run(
        [
            path_to_main,
            "--onefile",
            "--workpath=" + str(PROJ_ROOT / "build"),
            "--distpath=" + str(PROJ_ROOT / "dist"),
            "--icon=" + str(PROJ_ROOT / "icon.ico"),
        ]
    )

    # copy yaml files to dist directly (since PyInstaller run --add-data is not suitable for enduser-editable files)
    if (PROJ_ROOT / "dist").exists():
        shutil.copy(PROJ_ROOT / "src" / "settings.yaml", PROJ_ROOT / "dist")

    # make a zip of the dist directory contents. need to create in other dir then move or the zip will contain itself.
    shutil.make_archive(base_name="poemarcut", format="zip", root_dir=PROJ_ROOT / "dist")
    shutil.move("poemarcut.zip", PROJ_ROOT / "dist")
