#!/usr/bin/env python3
"""
Supplychain Watchtower

Reads:
  - all YAML files from the watch/ directory  (list of repo URLs to watch)
  - state.yaml  (mapping of repo URL -> last seen version tag)

Does:
  - For each repo, fetch the latest version (release tag preferred; else latest tag)
  - If different from state, add to process.yaml and update state.yaml

Writes:
  - process.yaml (only repos that changed this run)
  - state.yaml   (updated "last seen" versions)

Env:
  - GITHUB_TOKEN (required) – token with read access for public repos
  - WATCH_FILE / STATE_FILE / PROCESS_FILE (optional) – override default filenames
  - INCLUDE_PRERELEASE (optional, default "false") – set to "true" to consider pre-releases as latest

Key Functions:
parse_repo_url() - extracts owner and repo name from various GitHub URL formats (HTTPS, SSH)
latest_version_for_repo() - determines the latest version by:
  - First checking for the latest non-draft release
  - Falling back to the most recent tag if no releases exist
  - Can optionally include pre-releases if INCLUDE_PRERELEASE=true
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import yaml
from github import Github
from github.GithubException import GithubException


# ---------- Config ----------
# Load configuration from environment variables with sensible defaults

WATCH_FILE = Path(os.environ.get("WATCH_FILE", "watch"))  # Default to directory
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.yaml"))
PROCESS_FILE = Path(os.environ.get("PROCESS_FILE", "process.yaml"))
INCLUDE_PRERELEASE = os.environ.get("INCLUDE_PRERELEASE", "false").lower() == "true"


# ---------- Helpers ----------


def die(msg: str, code: int = 1) -> None:
    """
    Terminate the program with an error message.

    Args:
        msg: The error message to display to the user
        code: The exit code to return to the OS (default 1 for error)
              Use 0 for success, non-zero for various error conditions

    Returns:
        None (this function never returns - it exits the program)

    Example:
        die("Configuration file not found")
        # Program terminates here with exit code 1
    """
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)  # Exit immediately with the specified code


def ensure_github() -> Github:
    """
    Create and return an authenticated GitHub API client.

    This function checks for a GitHub personal access token in the environment
    variables and creates a PyGithub client object for making API requests.
    The token is required for API rate limits and accessing private repos if needed.

    Checks these environment variables in order:
        1. GITHUB_TOKEN (preferred)
        2. GH_TOKEN (alternative, used by GitHub CLI)

    Returns:
        Github: An authenticated PyGithub client object ready to make API calls

    Raises:
        SystemExit: If neither GITHUB_TOKEN nor GH_TOKEN is set (via die())

    Example:
        gh = ensure_github()
        repo = gh.get_repo("owner/repo")
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        die("GITHUB_TOKEN (or GH_TOKEN) env var not set")
    return Github(token)


def load_yaml(path: Path, default: Any) -> Any:
    """
    Load and parse a YAML file, returning a default value if file doesn't exist.

    This function safely handles missing files and empty YAML files by returning
    a default value instead of crashing. This is useful for optional config files
    or when initializing state on first run.

    Args:
        path: Path object pointing to the YAML file to load
        default: Value to return if file doesn't exist or is empty/null

    Returns:
        The parsed YAML data (typically a dict or list), or the default value

    Example:
        config = load_yaml(Path("config.yaml"), default={})
        # Returns {} if config.yaml doesn't exist or is empty

        repos = load_yaml(Path("repos.yaml"), default=[])
        # Returns [] if repos.yaml doesn't exist
    """
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or default
    return data


def dump_yaml(path: Path, obj: Any) -> None:
    """
    Write a Python object to a YAML file with consistent formatting.

    This function serializes Python data structures (dicts, lists, etc.) to YAML
    format with settings optimized for version control and human readability:
    - Sorts keys alphabetically for consistent diffs
    - Preserves Unicode characters
    - Uses safe serialization (no Python-specific types)

    Args:
        path: Path object where the YAML file should be written
        obj: Python object to serialize (dict, list, str, int, etc.)

    Returns:
        None

    Example:
        data = {"repo": "owner/name", "version": "v1.0.0"}
        dump_yaml(Path("output.yaml"), data)
        # Creates output.yaml with sorted keys
    """
    # pretty, stable ordering for diffs
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, sort_keys=True, allow_unicode=True)


def parse_repo_url(url: str) -> Tuple[str, str]:
    """
    Accepts formats like:
      https://github.com/owner/repo
      https://github.com/owner/repo.git
      git@github.com:owner/repo.git
    Returns: (owner, repo)
    """
    u = url.strip()

    # SSH format
    if u.startswith("git@github.com:"):
        u = u.split("git@github.com:", 1)[1]

    # HTTPS format
    if "github.com/" in u:
        u = u.split("github.com/", 1)[1]

    # Remove query/fragments and trailing .git or slashes
    u = u.split("#")[0].split("?")[0].strip("/")
    if u.endswith(".git"):
        u = u[:-4]

    parts = u.split("/")
    if len(parts) < 2:
        raise ValueError(f"Could not parse GitHub repo from URL: {url}")
    owner, repo = parts[0], parts[1]
    return owner, repo


def latest_version_for_repo(gh: Github, repo_url: str) -> Optional[str]:
    """
    Determine the latest version string for a repo.

    Priority:
      1. Latest non-draft release (exclude prerelease unless INCLUDE_PRERELEASE=true)
      2. Fallback to the most recent tag (by list order from API)
    """
    owner, name = parse_repo_url(repo_url)
    try:
        repo = gh.get_repo(f"{owner}/{name}")
    except GithubException as e:
        print(
            f"  - {repo_url}: cannot access repo ({e.data if hasattr(e, 'data') else e})"
        )
        return None

    # Try releases first
    try:
        releases = list(repo.get_releases())
        for rel in releases:
            if rel.draft:
                continue
            if not INCLUDE_PRERELEASE and rel.prerelease:
                continue
            if rel.tag_name:
                return rel.tag_name
            # Fallback: sometimes releases may lack tag_name – try name
            if rel.title:
                return rel.title
    except GithubException as e:
        print(f"  - {repo_url}: failed to list releases ({e})")

    # Fallback to tags
    try:
        tags = list(repo.get_tags())
        if tags:
            return tags[0].name  # GitHub returns most recent first
    except GithubException as e:
        print(f"  - {repo_url}: failed to list tags ({e})")

    return None


def load_watch_repositories(watch_path: Path) -> list:
    """
    Load repository list from either a single YAML file or a directory of YAML files.

    This supports two modes:
    1. Single file: watch.yaml with repositories list
    2. Directory: watch/ containing multiple .yaml files, each with repositories list

    Args:
        watch_path: Path to either a YAML file or directory containing YAML files

    Returns:
        Combined list of all repository URLs from all loaded files

    Example:
        # Single file mode
        repos = load_watch_repositories(Path("watch.yaml"))

        # Directory mode
        repos = load_watch_repositories(Path("watch"))
    """
    repositories = []

    # If it's a directory, load all .yaml files
    if watch_path.is_dir():
        yaml_files = sorted(watch_path.glob("*.yaml"))
        if not yaml_files:
            print(f"WARNING: No .yaml files found in {watch_path}")
            return repositories

        print(f"Loading from directory: {watch_path}")
        for yaml_file in yaml_files:
            print(f"  - Reading {yaml_file.name}")
            data = load_yaml(yaml_file, default={})
            repos = data.get("repositories") or []
            if isinstance(repos, list):
                repositories.extend(repos)
            else:
                print(
                    f"    WARNING: {yaml_file.name} does not contain a 'repositories' list"
                )

    # If it's a file, load it directly (backward compatibility)
    elif watch_path.is_file():
        print(f"Loading from file: {watch_path}")
        data = load_yaml(watch_path, default={})
        repos = data.get("repositories") or []
        if isinstance(repos, list):
            repositories = repos
        else:
            die(f"{watch_path} must contain a top-level 'repositories' list")

    # Path doesn't exist
    else:
        die(f"Watch path does not exist: {watch_path}")

    return repositories


# ---------- Main ----------


def main() -> int:
    # ===== Initialize GitHub API client =====
    gh = ensure_github()

    # ===== Load watch list (input) - supports both file and directory =====
    watch_repos = load_watch_repositories(WATCH_FILE)
    if not watch_repos:
        die(f"No repositories found in {WATCH_FILE}")

    # ===== Load state (previous run results) =====
    state = load_yaml(STATE_FILE, default={})
    state_map: Dict[str, str] = (
        (state.get("repositories") or {}) if isinstance(state, dict) else {}
    )
    if not isinstance(state_map, dict):
        state_map = {}

    # ===== Initialize output tracking =====
    process_map: Dict[str, str] = {}

    # ===== Print startup summary =====
    print(f"Loaded {len(watch_repos)} repositories from {WATCH_FILE}")
    print(f"Current state has {len(state_map)} entries in {STATE_FILE}")

    # ===== Check each repository for changes =====
    for repo_url in watch_repos:
        repo_url = str(repo_url).strip()
        if not repo_url:
            continue

        print(f"\nChecking {repo_url} ...")
        latest = latest_version_for_repo(gh, repo_url)
        if not latest:
            print(f"  - No version/release/tag found; skipping.")
            continue

        current = state_map.get(repo_url)
        if current != latest:
            print(f"  - CHANGE detected: {current!r} -> {latest!r}")
            process_map[repo_url] = latest
            state_map[repo_url] = latest
        else:
            print(f"  - Up to date at {latest}")

    #  ===== Write output files =====
    process_doc: Dict[str, Any] = {"repositories": process_map}
    state_doc: Dict[str, Any] = {"repositories": state_map}

    dump_yaml(PROCESS_FILE, process_doc)
    dump_yaml(STATE_FILE, state_doc)

    # ===== Print summary =====
    print(f"\nWrote {PROCESS_FILE} with {len(process_map)} change(s).")
    print(f"Updated {STATE_FILE} with {len(state_map)} total repo(s).")

    # Non-zero exit if there were changes? Typically we exit 0 either way.
    return 0


if __name__ == "__main__":
    sys.exit(main())
