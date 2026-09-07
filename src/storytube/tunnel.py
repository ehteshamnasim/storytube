"""A short-lived public URL for a local port.

Instagram's video_url publishing flow makes Meta's own servers cURL the video, so the
file has to be reachable from the internet for the few minutes publishing takes - this
app otherwise only ever runs on 127.0.0.1. ngrok already being installed and configured
(brew install ngrok && ngrok config add-authtoken <token>, done once) is all this needs.
"""

from __future__ import annotations

import re
import subprocess
import time

BOOT_TIMEOUT = 20
URL_PATTERN = re.compile(r"url=(https://\S+)")


class TunnelError(RuntimeError):
    pass


class Tunnel:
    def __init__(self, process: subprocess.Popen, public_url: str):
        self.process = process
        self.public_url = public_url.rstrip("/")

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()


def open_tunnel(port: int) -> Tunnel:
    try:
        process = subprocess.Popen(
            ["ngrok", "http", str(port), "--log", "stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError as exc:
        raise TunnelError(
            "ngrok is not installed. Instagram needs a public link to fetch the video from - "
            "install it with `brew install ngrok`, run `ngrok config add-authtoken <token>` once "
            "(free at ngrok.com), then try posting again."
        ) from exc

    lines: list[str] = []
    deadline = time.time() + BOOT_TIMEOUT
    while time.time() < deadline:
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                break
            continue
        lines.append(line)
        match = URL_PATTERN.search(line)
        if match:
            return Tunnel(process, match.group(1))

    process.terminate()
    detail = "".join(lines[-6:]).strip()
    raise TunnelError(f"Could not open a public link for Instagram to fetch the video from.\n{detail}".strip())
