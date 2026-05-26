"""
Nucleus pull script — syncs content from a Nucleus server to local disk.

Run via Kit in headless mode (pullnucleus.bat handles this):
  kit.exe source/apps/younite.usd_viewer_streaming_base.kit --exec pullnucleus.py
          --no-window --/app/auto_load_usd=""

The script defers execution to after Kit startup so that omni.client
(loaded as part of the Kit extension stack) is available.
"""

import asyncio
import json
import os
import sys


def _load_repo_dotenv() -> None:
    """Merge repo-root .env into os.environ if Nucleus vars are missing.

    pullnucleus.bat sets variables in cmd.exe, but kit.exe may not pass them to
    the embedded Python — loading the file here keeps sync working when .env exists.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.normpath(os.path.join(script_dir, "..", ".env"))
    if not os.path.isfile(env_path):
        return
    keys_needed = ("NUCLEUS_SERVER", "NUCLEUS_USERNAME", "NUCLEUS_PASSWORD")
    try:
        with open(env_path, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key not in keys_needed:
                    continue
                # Prefer non-empty values from .env (Kit may pass empty env vars)
                if val:
                    os.environ[key] = val
    except OSError as e:
        print(f"[pullnucleus] WARNING: could not read {env_path}: {e}")


def _ensure_local_dir(path: str):
    """Create local directory tree if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


def _sync_file(remote_url: str, local_path: str, stats: dict):
    """Download a single file from Nucleus if it's new or changed."""
    import omni.client

    remote_result, remote_entry = omni.client.stat(remote_url)
    if remote_result != omni.client.Result.OK:
        print(f"  SKIP (cannot stat remote): {remote_url}")
        stats["skipped"] += 1
        return

    remote_size = remote_entry.size

    if os.path.exists(local_path):
        local_size = os.path.getsize(local_path)
        if local_size == remote_size:
            stats["unchanged"] += 1
            return

    _ensure_local_dir(os.path.dirname(local_path))

    result, _, content = omni.client.read_file(remote_url)
    if result != omni.client.Result.OK:
        print(f"  ERROR reading: {remote_url} ({result})")
        stats["errors"] += 1
        return

    with open(local_path, "wb") as f:
        f.write(memoryview(content))

    stats["downloaded"] += 1
    size_kb = len(content) / 1024
    print(f"  Downloaded ({size_kb:.0f} KB): {os.path.basename(local_path)}")


def _sync_directory(remote_url: str, local_dir: str, recursive: bool, stats: dict):
    """Sync a remote Nucleus directory to a local directory."""
    import omni.client

    result, entries = omni.client.list(remote_url)
    if result != omni.client.Result.OK:
        print(f"  ERROR listing: {remote_url} ({result})")
        stats["errors"] += 1
        return

    for entry in entries:
        name = entry.relative_path
        if not name:
            continue

        remote_child = remote_url.rstrip("/") + "/" + name
        local_child = os.path.join(local_dir, name)

        if entry.flags & omni.client.ItemFlags.CAN_HAVE_CHILDREN:
            if recursive:
                _ensure_local_dir(local_child)
                _sync_directory(remote_child, local_child, recursive, stats)
        else:
            _sync_file(remote_child, local_child, stats)


async def _run_sync():
    """Main sync logic — runs after Kit startup so omni.client is available."""
    import omni.client
    import omni.kit.app

    app = omni.kit.app.get_app()

    # Wait a few frames for all extensions to finish loading
    for _ in range(10):
        await app.next_update_async()

    _load_repo_dotenv()

    server = os.environ.get("NUCLEUS_SERVER", "").strip()
    username = os.environ.get("NUCLEUS_USERNAME", "").strip()
    password = os.environ.get("NUCLEUS_PASSWORD", "").strip()

    if not server:
        print("[pullnucleus] ERROR: NUCLEUS_SERVER environment variable not set.")
        app.post_quit()
        return

    if not username:
        print("[pullnucleus] ERROR: NUCLEUS_USERNAME environment variable not set.")
        app.post_quit()
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "nucleus_sync.json")

    if not os.path.exists(config_path):
        print(f"[pullnucleus] ERROR: Sync config not found: {config_path}")
        app.post_quit()
        return

    with open(config_path, "r") as f:
        config = json.load(f)

    print(f"\n{'='*60}")
    print(f"[pullnucleus] Nucleus Pull — {server}")
    print(f"{'='*60}")

    # Register authentication callback — returns (username, password) for matching server
    def _auth_callback(url_prefix):
        if server.replace("omniverse://", "") in url_prefix:
            return (username, password)
        return None

    auth_sub = omni.client.register_authentication_callback(_auth_callback)
    print(f"[pullnucleus] Auth callback registered for {server}")

    total_stats = {"downloaded": 0, "unchanged": 0, "skipped": 0, "errors": 0}

    for rule in config.get("sync_rules", []):
        name = rule.get("name", "unnamed")
        remote_path = rule.get("remote_path", "")
        local_path = rule.get("local_path", "")
        recursive = rule.get("recursive", True)

        if not remote_path or not local_path:
            print(f"\n[pullnucleus] SKIP rule '{name}': missing remote_path or local_path")
            continue

        remote_url = server.rstrip("/") + remote_path
        local_abs = os.path.join(script_dir, local_path)

        print(f"\n--- {name} ---")
        print(f"  Remote: {remote_url}")
        print(f"  Local:  {local_abs}")

        stats = {"downloaded": 0, "unchanged": 0, "skipped": 0, "errors": 0}

        if remote_path.endswith("/"):
            _ensure_local_dir(local_abs)
            _sync_directory(remote_url, local_abs, recursive, stats)
        else:
            _ensure_local_dir(os.path.dirname(local_abs))
            _sync_file(remote_url, local_abs, stats)

        print(f"  Result: {stats['downloaded']} downloaded, "
              f"{stats['unchanged']} unchanged, "
              f"{stats['skipped']} skipped, "
              f"{stats['errors']} errors")

        for k in total_stats:
            total_stats[k] += stats[k]

    print(f"\n{'='*60}")
    print(f"[pullnucleus] Total: {total_stats['downloaded']} downloaded, "
          f"{total_stats['unchanged']} unchanged, "
          f"{total_stats['skipped']} skipped, "
          f"{total_stats['errors']} errors")
    print(f"{'='*60}\n")

    app.post_quit()


# Schedule the sync to run after Kit startup (omni.client needs extensions loaded)
asyncio.ensure_future(_run_sync())
