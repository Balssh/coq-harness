#!/usr/bin/env python3
"""Test input end-to-end: grab -> send key -> wait_for_change -> grab -> compare."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))

from client.bridge_client import BridgeClient, BridgeError

def main():
    client = BridgeClient(host="localhost", port=9090, timeout=30.0)
    client.connect()
    
    # 1. Ping
    print("=== Ping ===")
    result = client.ping()
    print(f"  Ping: {result}")
    
    # 2. Grab before
    print("\n=== Grab before ===")
    frame_before = client.grab()
    print(f"  Got {len(frame_before)} bytes of PNG")
    with open("/tmp/before.png", "wb") as f:
        f.write(frame_before)
    
    # 3. Send Enter key (main menu: should start New Game or similar)
    print("\n=== Sending Enter ===")
    result = client.keys(["enter"])
    print(f"  Keys result: {result}")
    
    # 4. Wait for change (5s timeout)
    print("\n=== Wait for change (5s) ===")
    try:
        changed = client.wait_for_change(timeout=5.0)
        print(f"  Changed: {changed}")
    except BridgeError as e:
        print(f"  BridgeError: {e}")
        changed = None
    
    # 5. Grab after
    print("\n=== Grab after ===")
    time.sleep(0.5)
    frame_after = client.grab()
    print(f"  Got {len(frame_after)} bytes of PNG")
    with open("/tmp/after.png", "wb") as f:
        f.write(frame_after)
    
    # 6. Compare
    print("\n=== Compare ===")
    same = frame_before == frame_after
    print(f"  Identical: {same}")
    if not same:
        print(f"  Size before: {len(frame_before)}, after: {len(frame_after)}")
    
    client.close()
    return 0 if not same else 1

if __name__ == "__main__":
    sys.exit(main())
