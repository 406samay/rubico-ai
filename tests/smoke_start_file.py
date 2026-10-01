"""Starts Rubico the way a person on a laptop does, with the start file for this
system, and checks it really comes up. The GitHub check runs this on Windows,
Mac and Linux, and you can run it yourself:

    python tests/smoke_start_file.py

It installs into .venv the first time (about a minute), uses a spare port, and
stops Rubico again at the end. Nothing is sent anywhere and no keys are needed.
"""

import http.client
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WAIT_SECONDS = 300  # the first run installs everything


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_command():
    system = platform.system()
    if system == "Windows":
        return ["cmd", "/c", "call", str(ROOT / "start.bat")]
    if system == "Darwin":
        return [str(ROOT / "start.command")]
    return [str(ROOT / "start.sh")]


def get(port, path, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers={"Host": host} if host else {})
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    result = (resp.status, resp.getheader("Location"), body)
    conn.close()
    return result


def stop(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def port_is_closed(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def main():
    port = free_port()
    config_file = ROOT / "config.yaml"
    made_config = not config_file.exists()
    if made_config:
        config_file.write_text(f"dashboard:\n  port: {port}\n", encoding="utf-8")
    else:
        sys.exit("config.yaml already exists here. Run this in a fresh copy so it can't touch your settings.")

    env = {k: v for k, v in os.environ.items() if not k.startswith(("RUBICO_", "RAILWAY_"))}
    env.update(RUBICO_NO_BROWSER="1", RUBICO_NO_PAUSE="1", PYTHONUNBUFFERED="1")
    log_path = ROOT / "smoke_start_file.log"
    failures = []
    proc = None
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            kwargs = {"start_new_session": True} if os.name != "nt" else {}
            proc = subprocess.Popen(start_command(), cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, **kwargs)

            deadline = time.time() + WAIT_SECONDS
            up = False
            while time.time() < deadline and proc.poll() is None:
                try:
                    if get(port, "/healthz")[0] == 200:
                        up = True
                        break
                except OSError:
                    pass
                time.sleep(2)
            if not up:
                failures.append("Rubico never came up")
            else:
                status, location, _ = get(port, "/")
                if (status, location) != (303, "/setup"):
                    failures.append(f"first visit should go to /setup, got {status} {location}")
                status, _, body = get(port, "/setup")
                if status != 200 or "Claude API key" not in body:
                    failures.append(f"/setup should show the setup page, got {status}")
                status, _, _ = get(port, "/setup", host="evil.example.com")
                if status != 403:
                    failures.append(f"a foreign website name must be refused, got {status}")
    finally:
        if proc:
            stop(proc)
        time.sleep(1)
        output = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        if made_config:
            config_file.unlink(missing_ok=True)

    if "Running on this computer" not in output:
        failures.append("the log never said it was running on this computer")
    if not port_is_closed(port):
        failures.append("Rubico was still listening after it was stopped")

    print("---- start file output ----")
    print("\n".join(output.splitlines()[-25:]))
    print("---------------------------")
    if failures:
        print("FAILED:\n  " + "\n  ".join(failures))
        return 1
    print(f"OK: {start_command()[-1]} started Rubico, showed setup, refused a foreign name and stopped cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
