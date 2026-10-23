"""Inspect TCP listeners and stop explicitly selected processes."""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys


def port_number(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Ports must be integers") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Ports must be between 1 and 65535")
    return port


def clean(value):
    return "".join(c if c.isprintable() else "?" for c in str(value))


def parse_lsof(output):
    rows, pid, command = [], None, "?"
    for line in output.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid, command = int(line[1:]), "?"
        elif line.startswith("c"):
            command = line[1:]
        elif line.startswith("n") and pid:
            address = line[1:]
            match = re.search(r":(\d+)$", address)
            if match:
                rows.append({"port": int(match[1]), "pid": pid, "command": command, "address": address})
    return rows


def parse_ss(output):
    rows = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        address = parts[3]
        match = re.search(r":(\d+)$", address)
        if not match:
            continue
        processes = re.findall(r'\("([^"]+)"[^)]*?pid=(\d+)', line)
        for command, pid in processes or [("?", None)]:
            rows.append({"port": int(match[1]), "pid": int(pid) if pid else None, "command": command, "address": address})
    return rows


def listeners(ports=()):
    if shutil.which("lsof"):
        result = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpcn"], capture_output=True, text=True)
        if result.returncode not in (0, 1) or (result.returncode and result.stderr.strip()):
            raise RuntimeError("lsof could not inspect listeners: " + clean(result.stderr.strip()))
        rows = parse_lsof(result.stdout)
    elif shutil.which("ss"):
        result = subprocess.run(["ss", "-H", "-ltnp"], capture_output=True, text=True, check=True)
        rows = parse_ss(result.stdout)
    else:
        raise RuntimeError("Install lsof (or iproute2 on Linux), or rerun ./install.sh")
    unique = {(r["port"], r["pid"], r["address"]): r for r in rows if not ports or r["port"] in ports}
    return sorted(unique.values(), key=lambda r: (r["port"], r["pid"] or 0, r["address"]))


def display(rows):
    print(f"{'PORT':<7} {'PID':<9} {'COMMAND':<22} ADDRESS")
    for row in rows:
        print(f"{row['port']:<7} {str(row['pid'] or '?'):<9} {clean(row['command']):<22} {clean(row['address'])}")
    if not rows:
        print("No matching TCP listeners.")


def process_identity(pid):
    try:
        with open(f"/proc/{pid}/stat") as stream:
            return stream.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def stop(ports, force=False, yes=False):
    rows = listeners(ports)
    display(rows)
    pids = sorted({r["pid"] for r in rows if r["pid"]})
    if not pids:
        if rows:
            raise RuntimeError("The OS did not expose process IDs; run this as the listener's owner")
        return 0
    identities = {pid: process_identity(pid) for pid in pids}
    name = "SIGKILL" if force else "SIGTERM"
    if not yes:
        if not sys.stdin.isatty():
            raise RuntimeError("Confirmation requires a terminal; use --yes explicitly for automation")
        if input(f"Send {name} to these {len(pids)} process(es)? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0
    current = {r["pid"] for r in listeners(ports)}
    failed = False
    for pid in pids:
        if pid <= 1 or pid == os.getpid():
            print(f"Refusing to signal protected PID {pid}.", file=sys.stderr)
            failed = True
            continue
        if pid not in current or (identities[pid] is not None and process_identity(pid) != identities[pid]):
            print(f"Skipping PID {pid}: listener changed during confirmation.")
            continue
        try:
            os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
            print(f"Sent {name} to PID {pid}.")
        except ProcessLookupError:
            print(f"PID {pid} has already exited.")
        except PermissionError:
            print(f"Permission denied for PID {pid}; run as its owner.", file=sys.stderr)
            failed = True
    return int(failed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=["list", "kill"], default="list")
    parser.add_argument("ports", nargs="*", type=port_number)
    parser.add_argument("--json", action="store_true", help="List listeners as JSON")
    parser.add_argument("--yes", "-y", action="store_true", help="Confirm signalling the displayed processes")
    parser.add_argument("--force", action="store_true", help="Use SIGKILL instead of SIGTERM")
    args = parser.parse_intermixed_args(argv)
    try:
        if args.action == "kill":
            if not args.ports:
                parser.error("kill requires at least one explicit port")
            if args.json:
                parser.error("--json is only supported for list")
            return stop(args.ports, args.force, args.yes)
        if args.force or args.yes:
            parser.error("--force and --yes are only supported for kill")
        rows = listeners(args.ports)
        if args.json:
            print(json.dumps(rows))
        else:
            display(rows)
        return 0
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"dev-ports: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 130
