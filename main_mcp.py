"""CoQ MCP Harness entry point.

Usage:
    python main_mcp.py              # deploy mod + run agent
    python main_mcp.py --check      # check mod deployment
    python main_mcp.py --no-deploy  # skip mod deployment
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CoQ MCP Harness — ML4 plays Caves of Qud via in-game MCP server"
    )
    parser.add_argument("--check", action="store_true",
                        help="Check mod deployment status and exit")
    parser.add_argument("--no-deploy", action="store_true",
                        help="Skip mod deployment")
    parser.add_argument("--force-deploy", action="store_true",
                        help="Force redeploy the mod")
    parser.add_argument("--host", default="127.0.0.1",
                        help="MCP server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=47321,
                        help="MCP server port (default: 47321)")
    parser.add_argument("--episode", type=int, default=1,
                        help="Starting episode number (default: 1)")
    args, remaining = parser.parse_known_args()

    if args.check:
        from mcp.deploy import check
        check()
        return

    if not args.no_deploy:
        from mcp.deploy import deploy
        deploy(force=args.force_deploy)
        print()

    from mcp.run import run_episode
    episode_num = args.episode
    while True:
        try:
            run_episode(
                episode_num,
                mcp_host=args.host,
                mcp_port=args.port,
            )
        except RuntimeError as exc:
            print(f"\n[run] Error: {exc}")
            try:
                input("Press Enter to retry, or Ctrl+C to quit...")
            except (KeyboardInterrupt, EOFError):
                break
        except KeyboardInterrupt:
            print("\n[run] Interrupted by user.")
            break

        print(f"\n--- Episode {episode_num} ended ---")
        try:
            input("Press Enter to start a new episode, or Ctrl+C to quit...")
        except (KeyboardInterrupt, EOFError):
            break
        episode_num += 1


if __name__ == "__main__":
    main()
