#!/usr/bin/python3 -I
"""Admit the listener's job packet before starting the pinned vendor worker.

Protocol: actions/runner ProcessChannel + StreamString, little-endian Int32
message kind and UTF-16LE byte length. No payload/credentials are logged.
"""

import hashlib, json, math, os, select, signal, stat, struct, subprocess, sys, threading, time

MAX = 50_000_000


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def lower(value):
    if not isinstance(value, dict):
        raise ValueError("object")
    result = {}
    for k, v in value.items():
        key = k.lower()
        if key in result:
            raise ValueError("duplicate_case")
        result[key] = v
    return result


def dictionary(value):
    value = lower(value)
    if "t" in value or "d" in value:
        if (
            set(value) != {"t", "d"}
            or value["t"] != 2
            or type(value["t"]) is not int
            or not isinstance(value["d"], list)
        ):
            raise ValueError("context")
        result = {}
        for pair in value["d"]:
            if (
                not isinstance(pair, dict)
                or set(pair) != {"k", "v"}
                or not isinstance(pair["k"], str)
            ):
                raise ValueError("context")
            key = pair["k"].lower()
            if key in result:
                raise ValueError("duplicate_context")
            result[key] = pair["v"]
        return result
    return value


def string(value):
    if isinstance(value, str):
        return value
    if (
        isinstance(value, dict)
        and set(value) <= {"s", "t"}
        and value.get("t", 0) == 0
        and type(value.get("t", 0)) is int
        and isinstance(value.get("s"), str)
    ):
        return value["s"]
    raise ValueError("context_string")


def admit(body, policy):
    msg = lower(json.loads(body.decode("utf-16-le"), object_pairs_hook=pairs))
    if (
        msg.get("jobname") != "postgresql-runtime"
        or msg.get("jobdisplayname") != "PostgreSQL runtime and metadata"
    ):
        raise ValueError("job")
    github = dictionary(dictionary(msg["contextdata"])["github"])
    expected = policy["github"]
    if (
        not isinstance(expected, dict)
        or not expected
        or any(string(github.get(k)) != v for k, v in expected.items())
    ):
        raise ValueError("authority")
    if (
        not {
            "repository",
            "repository_id",
            "event_name",
            "run_id",
            "run_attempt",
            "sha",
            "ref",
            "actor_id",
        }
        <= set(expected)
        or expected.get("repository") != "caglarsubas/auto_ml"
        or expected.get("run_attempt") != "1"
        or expected.get("event_name") not in {"pull_request", "push"}
    ):
        raise ValueError("policy")
    if (
        type(policy["valid_until"]) not in (int, float)
        or not math.isfinite(policy["valid_until"])
        or time.time() > policy["valid_until"]
    ):
        raise ValueError("expired")
    return msg


def exact(fd, count, deadline, stop=None):
    result = bytearray()
    while len(result) < count:
        if stop and stop.is_set():
            raise EOFError()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError()
        if not select.select([fd], [], [], min(0.25, remaining))[0]:
            continue
        chunk = os.read(fd, min(65536, count - len(result)))
        if not chunk:
            raise EOFError()
        result.extend(chunk)
    return bytes(result)


def frame(fd, stop=None):
    header = exact(fd, 8, time.monotonic() + 20, stop)
    kind, size = struct.unpack("<ii", header)
    if size < 0 or size > MAX or size % 2:
        raise ValueError("frame")
    return kind, header + exact(fd, size, time.monotonic() + 20, stop)


def write(fd, data):
    view = memoryview(data)
    while view:
        size = os.write(fd, view)
        if size <= 0:
            raise EOFError()
        view = view[size:]


def execute(argv, policy, vendor):
    if (
        len(argv) != 4
        or argv[1] != "spawnclient"
        or any(not s.isdecimal() or int(s) < 3 for s in argv[2:])
    ):
        raise ValueError("arguments")
    source, target = map(int, argv[2:])
    kind, first = frame(source)
    if kind != 1:
        raise ValueError("first_message")
    admit(first[8:], policy)
    sha = hashlib.sha256()
    with open(vendor, "rb") as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block)
    if sha.hexdigest() != policy["vendor_sha256"]:
        raise ValueError("worker_integrity")
    lease = os.open(
        policy["used_marker"],
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
        0o600,
    )
    os.close(lease)
    child_in, feed = os.pipe()
    drain, child_out = os.pipe()
    stop = threading.Event()
    errors = []
    child = subprocess.Popen(
        [vendor, "spawnclient", str(child_in), str(child_out)],
        pass_fds=(child_in, child_out),
    )
    os.close(child_in)
    os.close(child_out)

    def fail():
        errors.append(True)
        if child.poll() is None:
            child.terminate()

    def input_loop():
        try:
            write(feed, first)
            while not stop.is_set():
                if not select.select([source], [], [], 0.25)[0]:
                    continue
                k, data = frame(source, stop)
                if k not in {2, 3, 4}:
                    raise ValueError("second_job")
                write(feed, data)
        except (OSError, EOFError, ValueError, TimeoutError):
            if not stop.is_set():
                fail()
        finally:
            os.close(feed)

    def output_loop():
        try:
            while True:
                if not select.select([drain], [], [], 0.25)[0]:
                    if stop.is_set():
                        break
                    continue
                data = os.read(drain, 65536)
                if not data:
                    break
                write(target, data)
        except OSError:
            if not stop.is_set():
                fail()
        finally:
            os.close(drain)

    threads = [
        threading.Thread(target=f, daemon=True) for f in [input_loop, output_loop]
    ]
    for t in threads:
        t.start()
    previous = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        previous[sig] = signal.signal(
            sig, lambda s, _: child.send_signal(s) if child.poll() is None else None
        )
    try:
        result = child.wait()
    finally:
        stop.set()
        for t in threads:
            t.join(2)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if errors and result == 0:
        return 78
    return result


def load_policy(path):
    info = os.lstat(path)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_mode & 0o022
        or info.st_size > 16384
    ):
        raise ValueError("policy_file")
    return json.loads(open(path).read(), object_pairs_hook=pairs)


def main():
    try:
        result = execute(
            sys.argv,
            load_policy("/opt/declarai-pilot/admission.json"),
            "/opt/actions-runner/bin/Runner.Worker.vendor",
        )
        if result < 0:
            signal.signal(-result, signal.SIG_DFL)
            os.kill(os.getpid(), -result)
        return result
    except Exception:
        print(
            "Pilot job admission denied before vendor worker startup.", file=sys.stderr
        )
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
