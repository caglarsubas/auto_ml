"""Drive the synthetic reviewer through a controlling terminal without logging input."""

import errno
import fcntl
import os
import select
import signal
import subprocess
import sys
import termios
import time


class Terminal:
    def __init__(self, command: list[str], cwd, env):
        self.command = command
        self.cwd = cwd
        self.env = env
        self.pending = bytearray()
        self.secrets = set()
        self.stage = "startup"

    def __enter__(self):
        self.fd, slave = os.openpty()
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-I", "-S", os.path.abspath(__file__), *self.command],
                cwd=self.cwd,
                env=self.env,
                start_new_session=True,
                stdin=slave,
                stdout=slave,
                stderr=slave,
            )
        except BaseException:
            os.close(self.fd)
            raise
        finally:
            os.close(slave)
        return self

    def __exit__(self, *_):
        try:
            if self.process.returncode is None:
                # The unreaped child's PID still identifies the group we created.
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except (PermissionError, ProcessLookupError):
                    self.process.kill()
                self.process.wait()
        finally:
            os.close(self.fd)
            self.pending.clear()
            self.secrets.clear()

    def _error(self, reason):
        return AssertionError(f"reviewer terminal at {self.stage!r}: {reason}")

    def _read(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
            raise self._error("timed out")
        try:
            chunk = os.read(self.fd, 8192)
        except OSError as exc:
            if exc.errno != errno.EIO:  # Linux reports PTY EOF as EIO.
                raise
            chunk = b""
        self.pending.extend(chunk)
        if any(secret in self.pending for secret in self.secrets):
            raise self._error("hidden reply appeared in output")
        if len(self.pending) > 512 * 1024:
            raise self._error("output exceeded limit")
        return bool(chunk)

    def _take(self, end):
        text = self.pending[:end].decode("utf-8", errors="replace")
        del self.pending[:end]
        return text.replace("\r\n", "\n")

    def expect(self, substring: str, timeout=15) -> str:
        self.stage = substring[:100]
        marker = substring.encode("utf-8")
        deadline = time.monotonic() + timeout
        while marker not in self.pending:
            if not self._read(deadline):
                raise self._error("exited before expected prompt")
        return self._take(self.pending.index(marker) + len(marker))

    def reply(self, value: str, hidden=False):
        data = value.encode("utf-8")
        if hidden:
            if termios.tcgetattr(self.fd)[3] & termios.ECHO:
                raise self._error("terminal echo enabled at hidden prompt")
            if data:
                self.secrets.add(data)
        os.write(self.fd, data + b"\n")

    def finish(self, timeout=15) -> str:
        deadline = time.monotonic() + timeout
        while self._read(deadline):
            pass
        try:
            status = self.process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise self._error("timed out waiting for exit") from None
        if status:
            raise self._error(f"exit status {status}")
        return self._take(len(self.pending))


if __name__ == "__main__":
    # Popen created a new session. Claim its slave as /dev/tty for getpass,
    # then replace this single-threaded interpreter with the requested launcher.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.execvp(sys.argv[1], sys.argv[1:])
