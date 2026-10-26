"""Deploy the CoQ MCP Bridge mod to the Caves of Qud mods folder.

This copies the C# mod files from the mod/ directory to Qud's mods folder.
The mod compiles at Qud startup — no build step needed.

Usage:
    python -m mcp.deploy              # deploy the mod
    python -m mcp.deploy --check      # check if mod is deployed
    python -m mcp.deploy --force      # force redeploy
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MOD_SRC = PROJECT_ROOT / "mod"


def get_mods_dir() -> Path:
    """Get the Caves of Qud mods directory for the current OS."""
    if sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", "")) / "AppData" / "LocalLow" / "Freehold Games" / "CavesOfQud"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "com.FreeholdGames.CavesOfQud"
    else:
        base = Path.home() / ".config" / "unity3d" / "Freehold Games" / "CavesOfQud"

    return base / "Mods" / "CoQMcpBridge"


def is_deployed() -> bool:
    """Check if the mod is deployed and up to date."""
    mods_dir = get_mods_dir()
    if not mods_dir.exists():
        return False

    manifest_src = MOD_SRC / "manifest.json"
    manifest_dst = mods_dir / "manifest.json"
    if not manifest_dst.exists():
        return False

    try:
        src_data = json.loads(manifest_src.read_text())
        dst_data = json.loads(manifest_dst.read_text())
        if src_data.get("Version") != dst_data.get("Version"):
            return False
    except Exception:
        return False

    for cs_file in MOD_SRC.glob("*.cs"):
        dst_file = mods_dir / cs_file.name
        if not dst_file.exists():
            return False
        if cs_file.read_text() != dst_file.read_text():
            return False

    return True


def deploy(force: bool = False) -> Path:
    """Deploy the mod to Qud's mods folder. Returns the mod directory path."""
    mods_dir = get_mods_dir()

    if is_deployed() and not force:
        print(f"[deploy] Mod already deployed and up to date: {mods_dir}")
        return mods_dir

    print(f"[deploy] Deploying mod to: {mods_dir}")
    mods_dir.mkdir(parents=True, exist_ok=True)

    for src_file in MOD_SRC.iterdir():
        if src_file.suffix in (".cs", ".json"):
            dst_file = mods_dir / src_file.name
            shutil.copy2(src_file, dst_file)
            print(f"[deploy]   {src_file.name} -> {dst_file}")

    print(f"[deploy] Mod deployed successfully.")
    print(f"[deploy]")
    print(f"[deploy] Next steps:")
    print(f"[deploy]   1. Launch Caves of Qud")
    print(f"[deploy]   2. Go to Options → Modding → enable 'Allow scripting mods'")
    print(f"[deploy]   3. Enable the 'CoQ MCP Bridge' mod in Mod Configuration")
    print(f"[deploy]   4. Start or load a game")
    print(f"[deploy]   5. Take one step in-game to activate the mod")
    print(f"[deploy]   6. Run: python -m mcp.run")

    return mods_dir


def check() -> None:
    """Check if the mod is deployed."""
    mods_dir = get_mods_dir()
    print(f"[check] Mods directory: {mods_dir}")
    if mods_dir.exists():
        print(f"[check] Directory exists.")
        for f in sorted(mods_dir.iterdir()):
            print(f"[check]   {f.name} ({f.stat().st_size} bytes)")
    else:
        print(f"[check] Directory does NOT exist. Run: python -m mcp.deploy")

    if is_deployed():
        print(f"[check] Mod is deployed and up to date.")
    else:
        print(f"[check] Mod is NOT deployed or out of date. Run: python -m mcp.deploy")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy CoQ MCP Bridge mod")
    parser.add_argument("--force", action="store_true", help="Force redeploy even if up to date")
    parser.add_argument("--check", action="store_true", help="Check deployment status")
    args = parser.parse_args()

    if args.check:
        check()
    else:
        deploy(force=args.force)


if __name__ == "__main__":
    main()
