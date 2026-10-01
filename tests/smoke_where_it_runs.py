"""Checks the "Railway or this computer?" question in a real terminal.

A normal test can't do this, because Rubico only asks when a person is sitting
at a terminal. This opens a pseudo terminal, types the answers like a person
would and reads what comes back. Mac and Linux only (Windows has no pty), and
the GitHub check runs it there:

    python tests/smoke_where_it_runs.py

It uses a throwaway settings file and data folder, so it can't touch yours.
"""

import os
import pty
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Session:
    """Rubico running at a pseudo terminal that we can type into."""

    def __init__(self, config_file, data_dir):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("RUBICO_", "RAILWAY_"))}
        for key in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DASHBOARD_PASSWORD"):
            env.pop(key, None)
        env.update(RUBICO_CONFIG=str(config_file), RUBICO_DATA_DIR=str(data_dir),
                   RUBICO_NO_BROWSER="1", PYTHONUNBUFFERED="1")
        self.master, self.slave = pty.openpty()
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--local"], cwd=ROOT, env=env,
                                     stdin=self.slave, stdout=self.slave, stderr=self.slave, close_fds=True,
                                     start_new_session=True)
        # We keep our own end of the terminal open until the very end. On a Mac, a
        # terminal whose far end has closed can throw away its last lines of output,
        # and a real person's terminal window stays open, so this matches real life.
        self.output = ""

    def read_until(self, text, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if text in self.output:
                return True
            if select.select([self.master], [], [], 0.5)[0]:
                try:
                    chunk = os.read(self.master, 4096)
                except OSError:
                    return text in self.output
                if not chunk:
                    return text in self.output
                self.output += chunk.decode("utf-8", "replace")
            elif self.proc.poll() is not None:
                return text in self.output
        return text in self.output

    def type(self, line):
        os.write(self.master, (line + "\n").encode())

    def drain(self):
        """Reads whatever is left, so we see what Rubico printed just before it exited."""
        while select.select([self.master], [], [], 0.5)[0]:
            try:
                chunk = os.read(self.master, 4096)
            except OSError:
                break
            if not chunk:
                break
            self.output += chunk.decode("utf-8", "replace")

    def wait_exit(self, timeout=30):
        try:
            code = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            code = None
        self.drain()
        return code

    def stop(self):
        if self.proc.poll() is None:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        os.close(self.master)
        os.close(self.slave)


def dashboard_up(port, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=3) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(1)
    return False


def main():
    failures = []
    port = free_port()
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "config.yaml"
        data_dir = Path(tmp) / "data"
        config_file.write_text(f"dashboard:\n  port: {port}\n", encoding="utf-8")

        # 1. Choosing Railway: a wrong answer is asked again, then the guide is shown and it stops.
        s = Session(config_file, data_dir)
        try:
            if not s.read_until("Type 1 or 2"):
                failures.append("it never asked where Rubico should run")
            s.type("maybe")
            if not s.read_until("Please type 1 or 2"):
                failures.append("a wrong answer was not asked again")
            s.type("1")
            code = s.wait_exit()
            if code != 0:
                failures.append(f"choosing Railway should end with exit code 0, got {code}")
            if "deploy-railway.md" not in s.output or "$5 a month" not in s.output:
                failures.append("choosing Railway did not show the guide")
            if "where" in config_file.read_text(encoding="utf-8"):
                failures.append("choosing Railway must not be remembered")
        finally:
            s.stop()

        # 2. Choosing this computer: it carries on, and remembers.
        s = Session(config_file, data_dir)
        try:
            if not s.read_until("Type 1 or 2"):
                failures.append("it did not ask again after Railway was chosen")
            s.type("2")
            if not s.read_until("setting Rubico up on this computer"):
                failures.append("choosing this computer did not carry on")
            if not dashboard_up(port):
                failures.append("Rubico did not come up after choosing this computer")
            if "where: laptop" not in config_file.read_text(encoding="utf-8"):
                failures.append("the answer was not remembered in config.yaml")
        finally:
            s.stop()

        # 3. The next start must not ask again.
        s = Session(config_file, data_dir)
        try:
            if not dashboard_up(port):
                failures.append("Rubico did not come up on the second start")
            if "Type 1 or 2" in s.output:
                failures.append("it asked again even though the answer was remembered")
        finally:
            s.read_until("Waiting for setup", timeout=5)
            if "Type 1 or 2" in s.output:
                failures.append("it asked again even though the answer was remembered")
            s.stop()

    print("---- last output ----")
    print("\n".join(s.output.splitlines()[-15:]))
    print("---------------------")
    if failures:
        print("FAILED:\n  " + "\n  ".join(failures))
        return 1
    print("OK: it asks, Railway shows the guide and stops, this computer carries on and is remembered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
