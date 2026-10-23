"""CoQ Harness entry point.

Usage:
    python main.py [--host localhost] [--port 9090] [--episode 1] [--skip-chargen]
    python main.py --force-bridge   # force redeploy of Windows bridge

Auto-deploys the WSL relay and Windows bridge before starting.
"""

import argparse
import sys

from bridge.deploy import ensure_all
from run.manager import main

if __name__ == "__main__":
    # Parse just the --force-bridge flag here; the rest is handled by run.manager
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--force-bridge", action="store_true",
                     help="Force redeploy of the Windows bridge")
    pre_args, remaining = pre.parse_known_args()
    sys.argv = [sys.argv[0]] + remaining

    # Auto-deploy infrastructure (relay + bridge + Qud window check)
    try:
        ensure_all(force_bridge=pre_args.force_bridge)
    except Exception as exc:
        print(f"[main] Auto-deploy failed: {exc}")
        print("[main] Continuing anyway — you may need to start the bridge manually.")
        try:
            input("Press Enter to continue, or Ctrl+C to quit...")
        except (KeyboardInterrupt, EOFError):
            sys.exit(1)

    main()
