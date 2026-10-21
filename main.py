"""CoQ Harness entry point.

Usage:
    python main.py [--host localhost] [--port 9090] [--episode 1]

Prerequisites:
    1. Start the bridge on Windows:  python -m bridge.server
    2. Launch Caves of Qud on Windows
    3. Set MISTRAL_API_KEY environment variable
    4. Run this script from WSL
"""

from run.manager import main

if __name__ == "__main__":
    main()
