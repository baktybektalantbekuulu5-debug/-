"""Find the BeamNG.drive installation and user folder on Windows."""

from __future__ import annotations

import os
import re
import string
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psutil

STEAM_APP_ID = "284160"  # BeamNG.drive on Steam
BINARIES = ("BeamNG.drive.exe", "Bin64/BeamNG.drive.x64.exe", "Bin64/BeamNG.x64.exe",
            "BeamNG.tech.exe", "Bin64/BeamNG.tech.x64.exe")


@dataclass
class GameInstall:
    home: Path
    binary: Path
    source: str                      # how it was found
    steam_build_id: str | None = None


@dataclass
class LocateResult:
    installs: list[GameInstall] = field(default_factory=list)
    user_folders: list[Path] = field(default_factory=list)
    user_versions: list[str] = field(default_factory=list)
    running_exe: Path | None = None

    @property
    def best(self) -> GameInstall | None:
        return self.installs[0] if self.installs else None


def _binary_in(home: Path) -> Path | None:
    for b in BINARIES:
        p = home / b
        if p.is_file():
            return p
    return None


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "win32":
        import winreg
        for hive, key, value in (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
        ):
            try:
                with winreg.OpenKey(hive, key) as k:
                    roots.append(Path(winreg.QueryValueEx(k, value)[0]))
            except OSError:
                pass
    roots += [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    out: list[Path] = []
    for r in roots:
        r = Path(os.path.normpath(r))
        if r.is_dir() and r not in out:
            out.append(r)
    return out


def _steam_libraries() -> list[Path]:
    libs: list[Path] = []
    for root in _steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            text = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r'"path"\s+"([^"]+)"', text):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
    # Typical extra libraries on other drives.
    if sys.platform == "win32":
        for d in string.ascii_uppercase:
            for sub in ("SteamLibrary", "Steam", "Games/Steam", "Games/SteamLibrary"):
                p = Path(f"{d}:/") / sub
                if p.is_dir():
                    libs.append(p)
    uniq: list[Path] = []
    for p in libs:
        p = Path(os.path.normpath(p))
        if p not in uniq:
            uniq.append(p)
    return uniq


def _build_id(lib: Path) -> str | None:
    acf = lib / "steamapps" / f"appmanifest_{STEAM_APP_ID}.acf"
    if acf.is_file():
        m = re.search(r'"buildid"\s+"(\d+)"', acf.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(1)
    return None


def _shallow_search(base: Path, depth: int = 3) -> list[Path]:
    """Look for a BeamNG folder in user-facing places (Desktop, Downloads, Games)."""
    found: list[Path] = []
    if not base.is_dir():
        return found
    stack = [(base, 0)]
    while stack:
        d, lvl = stack.pop()
        try:
            for child in d.iterdir():
                if not child.is_dir() or child.name.startswith("."):
                    continue
                if "beamng" in child.name.lower() and _binary_in(child):
                    found.append(child)
                elif lvl < depth:
                    stack.append((child, lvl + 1))
        except (PermissionError, OSError):
            continue
    return found


def locate() -> LocateResult:
    res = LocateResult()
    seen: set[Path] = set()

    def add(home: Path, source: str, build: str | None = None) -> None:
        home = Path(os.path.normpath(home))
        b = _binary_in(home)
        if b and home not in seen:
            seen.add(home)
            res.installs.append(GameInstall(home, b, source, build))

    # 1. Game already running.
    for proc in psutil.process_iter(["name", "exe"]):
        name = (proc.info.get("name") or "").lower()
        if name.startswith("beamng") and proc.info.get("exe"):
            exe = Path(proc.info["exe"])
            res.running_exe = exe
            add(exe.parent.parent if exe.parent.name.lower() == "bin64" else exe.parent, "running")

    # 2. Steam libraries.
    for lib in _steam_libraries():
        add(lib / "steamapps" / "common" / "BeamNG.drive", "steam", _build_id(lib))

    # 3. Common manual locations.
    home = Path.home()
    for base in (Path("C:/BeamNG.drive"), Path("C:/Games"), Path("D:/Games"),
                 Path("C:/Program Files"), home / "Desktop", home / "Downloads",
                 home / "Games", home / "OneDrive" / "Desktop"):
        if base.name.lower().startswith("beamng"):
            add(base, "manual")
        else:
            for p in _shallow_search(base, depth=2):
                add(p, "search")

    # User folder (mods, settings, levels). Version sub-folders tell the game version.
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    for uf in (local / "BeamNG" / "BeamNG.drive", local / "BeamNG.drive",
               home / "Documents" / "BeamNG.drive"):
        if uf.is_dir():
            res.user_folders.append(uf)
            for v in sorted(uf.iterdir()):
                if v.is_dir() and re.fullmatch(r"\d+\.\d+", v.name):
                    res.user_versions.append(v.name)
    return res
