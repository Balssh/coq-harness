"""Quick test script for the MCP client.

Run this after starting Qud with the mod to verify the connection works:

    python -m mcp.test_client

It will:
1. Connect to the MCP server
2. Get the current game state
3. Print a summary
4. Optionally send a test command
"""

import sys
import time

from mcp.client import McpClient, McpError, GameStateData


def test_connection(host: str = "127.0.0.1", port: int = 47321) -> bool:
    print(f"[test] Connecting to {host}:{port}...")
    try:
        client = McpClient(host=host, port=port, timeout=10.0)
        client.connect()
        print("[test] Connected!")
    except Exception as exc:
        print(f"[test] Connection failed: {exc}")
        print("[test] Make sure Qud is running with the mod enabled and you've taken one step.")
        return False

    try:
        print("[test] Requesting game state...")
        state = client.get_state(timeout=10.0)
        print(f"[test] State received!")
        print()
        print(state.format_for_prompt(max_cells=30, max_messages=15))
        print()

        p = state.player
        if p:
            print(f"[test] Player: {p.get('name', '?')}")
            print(f"[test] HP: {p.get('hp', '?')}/{p.get('hpMax', '?')}")
            print(f"[test] Level: {p.get('level', '?')}")
            print(f"[test] Location: {p.get('location', '?')}")
            print(f"[test] Position: {state.position}")
            print(f"[test] In Combat: {state.in_combat}")
            print(f"[test] Nearby creatures: {len(state.creatures_nearby())}")
            print(f"[test] Hostiles nearby: {len(state.hostile_nearby())}")
            print(f"[test] Items on ground: {len(state.items_on_ground())}")
            print(f"[test] Inventory items: {len(state.inventory)}")
            print(f"[test] Abilities: {len(state.abilities)}")

        client.close()
        return True

    except McpError as exc:
        print(f"[test] MCP error: {exc}")
        client.close()
        return False
    except Exception as exc:
        print(f"[test] Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        client.close()
        return False


def test_command(host: str = "127.0.0.1", port: int = 47321) -> bool:
    """Test sending a command (wait 1 turn)."""
    print(f"\n[test] Testing command (wait 1 turn)...")
    try:
        client = McpClient(host=host, port=port, timeout=30.0)
        client.connect()

        state_before = client.get_state(timeout=10.0)
        print(f"[test] Before: HP {state_before.hp}, pos {state_before.position}")

        result = client.send_command("wait", turns=1)
        print(f"[test] Command result: {result}")

        time.sleep(1.0)

        state_after = client.get_state(timeout=10.0)
        print(f"[test] After: HP {state_after.hp}, pos {state_after.position}")

        client.close()
        return True

    except Exception as exc:
        print(f"[test] Command test failed: {exc}")
        return False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Test CoQ MCP client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47321)
    parser.add_argument("--command", action="store_true",
                        help="Also test sending a command (wait 1 turn)")
    args = parser.parse_args()

    ok = test_connection(args.host, args.port)
    if not ok:
        sys.exit(1)

    if args.command:
        ok = test_command(args.host, args.port)
        if not ok:
            sys.exit(1)

    print("\n[test] All tests passed!")


if __name__ == "__main__":
    main()
