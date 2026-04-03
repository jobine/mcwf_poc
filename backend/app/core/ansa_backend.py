"""ANSA backend — manages ANSA process in listener mode via IAP protocol.

This module launches ANSA in batch/listener mode and communicates with it
using the Inter-ANSA Protocol (IAP) over TCP sockets. Python scripts are
sent for execution and results are returned.
"""

import os
from pathlib import Path
import platform
import shutil
import socket
import struct
import subprocess
import threading
import time
import textwrap

# ── IAP Protocol constants ──────────────────────────────────────────

class _MessageCode:
    hello = 0x01
    execute_script = 0x02
    goodbye = 0x03

class _MessageType:
    response = 0x00
    request = 0x01

class _Tag:
    result_code = 0x01
    process_id = 0x02
    script_string = 0x03
    entry_method = 0x04
    script_return_type = 0x05
    script_retval_string_dict = 0x06
    script_execution_details = 0x07
    supported_service = 0x08
    post_connection_action = 0x09
    pre_execution_database_action = 0x0a
    script_retval_bytes = 0x0b
    muted_execution = 0x0e

class _ResultCode:
    success = 0x00

class _ScriptReturnType:
    none = 0x00
    string_dict = 0x02
    type_bytes = 0x03

class _ScriptExecutionDetails:
    success = 0x00

class _PostConnectionAction:
    shut_down = 0x00
    keep_listening = 0x01

class _PreExecutionDatabaseAction:
    reset_database = 0x00
    keep_database = 0x01

class _MutedExecution:
    off = 0x00
    on = 0x01


# ── IAP helpers ─────────────────────────────────────────────────────

def _calculate_padding(length):
    mod = length % 4
    return (4 - mod) if mod else 0

def _pack_btext(btext):
    p = struct.pack(f'>{len(btext)}s', btext)
    pad = _calculate_padding(len(btext))
    if pad:
        p += struct.pack(f'>{pad}s', b'\xa5' * pad)
    return p


class _MessageHeader:
    SIZE = 16

    def __init__(self, version, msg_type, service_id, msg_code, txn_id, length):
        self.version = version
        self.flags = msg_type
        self.service_id = service_id
        self.message_code = msg_code
        self.transaction_id = txn_id
        self.length = length

    def pack(self):
        return struct.pack('>BBHLLL', self.version, self.flags,
                           self.service_id, self.message_code,
                           self.transaction_id, self.length)

    @classmethod
    def from_bytes(cls, data):
        return cls(*struct.unpack('>BBHLLL', data))


class _IE:
    """Information Element (TLV)."""

    def __init__(self, tag, value):
        self.tag = tag
        self.value = value

    def pack(self):
        if isinstance(self.value, int):
            return struct.pack('>LLI', self.tag, 12, self.value)
        elif isinstance(self.value, str):
            b = self.value.encode('utf-8')
            return struct.pack('>LL', self.tag, 8 + len(b)) + _pack_btext(b)
        elif isinstance(self.value, bytes):
            return struct.pack('>LL', self.tag, 8 + len(self.value)) + _pack_btext(self.value)
        raise TypeError(f'Unsupported IE value type: {type(self.value)}')


def _decode_tlvs(data, total_len):
    ies = []
    pos = 0
    while pos < total_len:
        tag = struct.unpack('>L', data[pos:pos+4])[0]
        length = struct.unpack('>L', data[pos+4:pos+8])[0]
        value_len = length - 8

        if tag in (_Tag.result_code, _Tag.process_id, _Tag.script_return_type,
                   _Tag.script_execution_details, _Tag.supported_service,
                   _Tag.post_connection_action, _Tag.muted_execution):
            value = struct.unpack('>L', data[pos+8:pos+12])[0]
        elif tag == _Tag.script_retval_string_dict:
            value = data[pos:pos+length]
        elif tag == _Tag.script_retval_bytes:
            value = bytes(data[pos+8:pos+length])
        elif tag in (_Tag.script_string, _Tag.entry_method):
            value = data[pos+8:pos+8+value_len].decode('utf-8')
        else:
            value = data[pos+8:pos+length]

        ies.append(_IE(tag, value))
        pos += length + _calculate_padding(value_len)
    return ies


def _pack_ies(ies):
    return b''.join(ie.pack() for ie in ies)


def _bytes_to_string_dict(octets):
    result = {}
    idx = 8
    dict_len = struct.unpack('>L', octets[idx:idx+4])[0]
    idx += 4
    for _ in range(dict_len):
        key_len = struct.unpack('>L', octets[idx:idx+4])[0]
        idx += 4
        key = octets[idx:idx+key_len].decode('utf-8')
        idx += key_len
        data_len = struct.unpack('>L', octets[idx:idx+4])[0]
        idx += 4
        val = octets[idx:idx+data_len].decode('utf-8')
        idx += data_len
        result[key] = val
    return result


# ── ANSA Process & Connection ───────────────────────────────────────

def find_ansa():
    """Find the ANSA executable.

    Checks ANSA_HOME env var first, then PATH.
    Returns the path to ansa64.bat (Windows) or ansa.sh (Linux/Mac).
    """
    ansa_home = os.environ.get('ANSA_HOME', '')
    if ansa_home:
        if platform.system() == 'Windows':
            bat = os.path.join(ansa_home, 'ansa64.bat')
            if not os.path.isfile(bat):
                # ANSA_HOME might point to config/ subdir
                parent = os.path.dirname(ansa_home.rstrip(os.sep))
                bat = os.path.join(parent, 'ansa64.bat')
            if os.path.isfile(bat):
                return bat
        else:
            sh = os.path.join(ansa_home, 'ansa.sh')
            if os.path.isfile(sh):
                return sh

    # Try PATH
    which = shutil.which('ansa64') or shutil.which('ansa')
    if which:
        return which

    raise RuntimeError(
        "ANSA is not installed or not found.\n"
        "Set the ANSA_HOME environment variable to the ANSA installation directory.\n"
        "  Windows: set ANSA_HOME=C:\\Program Files\\BETA_CAE_Systems\\ansa_v25.1.0\n"
        "  Linux:   export ANSA_HOME=/opt/BETA_CAE_Systems/ansa_v25.1.0"
    )


def _free_port():
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class AnsaConnection:
    """IAP connection to a running ANSA listener process."""

    def __init__(self, port, timeout=120):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._txn_id = 0
        self._connect(port, timeout)

    def _connect(self, port, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._sock.connect(('localhost', port))
                return
            except socket.error:
                time.sleep(1)
        raise RuntimeError(f"Could not connect to ANSA on port {port} within {timeout}s")

    def _next_txn(self):
        tid = self._txn_id
        self._txn_id += 1
        return tid

    def _recv(self):
        header_data = b''
        while len(header_data) < 16:
            header_data += self._sock.recv(16 - len(header_data))
        length = struct.unpack('>L', header_data[12:16])[0]
        payload_len = length - 16
        payload = b''
        while len(payload) < payload_len:
            payload += self._sock.recv(payload_len - len(payload))
        return header_data + payload

    def hello(self):
        """Perform IAP handshake."""
        ies = [
            _IE(_Tag.process_id, os.getpid()),
            _IE(_Tag.supported_service, 0x00010002),
        ]
        packed = _pack_ies(ies)
        header = _MessageHeader(1, _MessageType.request, 0,
                                _MessageCode.hello, self._next_txn(),
                                16 + len(packed))
        self._sock.sendall(header.pack() + packed)

        resp = self._recv()
        resp_ies = _decode_tlvs(resp[16:], len(resp) - 16)
        for ie in resp_ies:
            if ie.tag == _Tag.result_code and ie.value != _ResultCode.success:
                raise RuntimeError("ANSA handshake failed")
        return True

    def run_script(self, script_text, function_name=None,
                   keep_database=True, muted=False):
        """Execute a Python script on the remote ANSA process.

        Args:
            script_text: Python source code to execute.
            function_name: Optional entry function to call.
            keep_database: If True, keep database between executions.
            muted: If True, suppress ANSA console output.

        Returns:
            dict with keys: success (bool), details (int),
            return_type (int), result (dict|bytes|None)
        """
        db_action = (_PreExecutionDatabaseAction.keep_database if keep_database
                     else _PreExecutionDatabaseAction.reset_database)

        ies = [_IE(_Tag.script_string, script_text)]
        if function_name:
            ies.append(_IE(_Tag.entry_method, function_name))
        ies.append(_IE(_Tag.pre_execution_database_action, db_action))
        if muted:
            ies.append(_IE(_Tag.muted_execution, _MutedExecution.on))

        packed = _pack_ies(ies)
        header = _MessageHeader(1, _MessageType.request, 1,
                                _MessageCode.execute_script, self._next_txn(),
                                16 + len(packed))
        self._sock.sendall(header.pack() + packed)

        resp = self._recv()
        resp_ies = _decode_tlvs(resp[16:], len(resp) - 16)

        result = {
            'success': False,
            'details': None,
            'return_type': None,
            'result': None,
        }

        for ie in resp_ies:
            if ie.tag == _Tag.result_code:
                result['success'] = (ie.value == _ResultCode.success)
            elif ie.tag == _Tag.script_execution_details:
                result['details'] = ie.value
            elif ie.tag == _Tag.script_return_type:
                result['return_type'] = ie.value
            elif ie.tag == _Tag.script_retval_string_dict:
                result['result'] = _bytes_to_string_dict(ie.value)
            elif ie.tag == _Tag.script_retval_bytes:
                result['result'] = ie.value

        return result

    def goodbye(self, shutdown=False):
        """Send goodbye and optionally shut down the ANSA process."""
        action = (_PostConnectionAction.shut_down if shutdown
                  else _PostConnectionAction.keep_listening)
        ie = _IE(_Tag.post_connection_action, action)
        packed = ie.pack()
        header = _MessageHeader(1, _MessageType.request, 0,
                                _MessageCode.goodbye, self._next_txn(),
                                16 + len(packed))
        self._sock.sendall(header.pack() + packed)
        self._recv()
        return True

    def close(self):
        """Close the socket connection."""
        self._sock.close()


class AnsaProcess:
    """Manages an ANSA process running in listener/batch mode."""

    def __init__(self, ansa_command=None, batch=True, port=None, extra_args=['--skip-release-highlights'], timeout=120):
        if ansa_command is None:
            ansa_command = find_ansa()

        self.port = port or _free_port()
        self._timeout = timeout

        cmd = [ansa_command, '-nolauncher', '-listenport', str(self.port), '-foregr']
        if batch:
            cmd.append('-b')
        if extra_args:
            cmd.extend(extra_args)

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        self._process = subprocess.Popen(cmd, shell=False,
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         env=env)
        self._connection = None
        self._stdout_thread = None
        self._stdout_stop = threading.Event()
        self._stderr_thread = None
        self._stderr_stop = threading.Event()
        self._last_output_line_time = 0.0
        self._output_line_count = 0
        self._output_time_lock = threading.Lock()

    def connect(self):
        """Establish IAP connection and perform handshake."""
        conn = AnsaConnection(self.port, self._timeout)
        conn.hello()
        self._connection = conn
        return conn

    @property
    def connection(self):
        if self._connection is None:
            self.connect()
        return self._connection

    def _start_pipe_reader(self, pipe, stop_event, callback):
        """Start a thread that reads a pipe line-by-line in real time.

        Returns the started thread, or None if the pipe is unavailable.
        """
        if pipe is None:
            return None

        def _reader():
            try:
                while not stop_event.is_set():
                    raw = pipe.readline()
                    if not raw:
                        break
                    try:
                        line = raw.decode('utf-8').rstrip('\r\n')
                    except UnicodeDecodeError:
                        line = raw.decode('cp1252', errors='replace').rstrip('\r\n')
                    with self._output_time_lock:
                        self._last_output_line_time = time.monotonic()
                        self._output_line_count += 1
                    try:
                        callback(line)
                    except Exception:
                        # Never let callback errors kill the reader thread.
                        pass
            except (AttributeError, OSError, ValueError):
                pass

        t = threading.Thread(target=_reader, daemon=False)
        t.start()
        return t

    def start_output_reader(self, on_stdout=None, on_stderr=None):
        """Start threads that read ANSA stdout and stderr line-by-line.

        Args:
            on_stdout: Called with each stdout line (str). Defaults to print.
            on_stderr: Called with each stderr line (str). Defaults to print.
                       The lines have trailing newline characters stripped.
        """
        if self._stdout_thread is None or not self._stdout_thread.is_alive():
            if on_stdout is None:
                on_stdout = print
            self._stdout_stop.clear()
            self._stdout_thread = self._start_pipe_reader(
                self._process.stdout, self._stdout_stop, on_stdout,
            )

        if self._stderr_thread is None or not self._stderr_thread.is_alive():
            if on_stderr is None:
                on_stderr = print
            self._stderr_stop.clear()
            self._stderr_thread = self._start_pipe_reader(
                self._process.stderr, self._stderr_stop, on_stderr,
            )

    def stop_output_reader(self, timeout=2.0):
        """Stop both reader threads and wait for them to exit."""
        self._stdout_stop.set()
        self._stderr_stop.set()

        if self._process:
            for pipe in (self._process.stdout, self._process.stderr):
                if pipe:
                    try:
                        pipe.close()
                    except Exception:
                        pass

        for thread in (self._stdout_thread, self._stderr_thread):
            if thread and thread.is_alive():
                thread.join(timeout=timeout)

        self._stdout_thread = None
        self._stderr_thread = None

    def _wait_for_quiet_output(self, quiet_period_ms=200, max_wait_ms=1200, poll_ms=20):
        """Wait until both stdout and stderr have been quiet, or timeout.

        This is best-effort and only applies when reader threads are active.
        """
        if quiet_period_ms <= 0:
            return
        stdout_alive = self._stdout_thread is not None and self._stdout_thread.is_alive()
        stderr_alive = self._stderr_thread is not None and self._stderr_thread.is_alive()
        if not stdout_alive and not stderr_alive:
            return

        start = time.monotonic()
        quiet_s = quiet_period_ms / 1000.0
        max_wait_s = max_wait_ms / 1000.0
        poll_s = max(poll_ms, 1) / 1000.0
        quiet_deadline = start + quiet_s
        max_deadline = start + max_wait_s

        with self._output_time_lock:
            seen_count = self._output_line_count

        while True:
            now = time.monotonic()
            if now >= quiet_deadline:
                break

            if now >= max_deadline:
                break

            with self._output_time_lock:
                current_count = self._output_line_count

            if current_count != seen_count:
                seen_count = current_count
                quiet_deadline = time.monotonic() + quiet_s

            time.sleep(poll_s)

    def run_script(self, script_text, function_name=None, keep_database=True,
                   quiet_period_ms=0, quiet_max_wait_ms=1200, **kwargs):
        """Execute a script on the ANSA process.

        Args:
            script_text: Python source code to execute.
            function_name: Optional entry function to call.
            keep_database: If True, keep database between executions.
            quiet_period_ms: Optional stdout quiet window before returning.
                             Set 0 to disable (default).
            quiet_max_wait_ms: Max wait time for quiet window.
        """
        script_text = _inject_script(script_text, function_name or "main", **kwargs)
        result = self.connection.run_script(script_text, function_name, keep_database)
        if quiet_period_ms > 0:
            self._wait_for_quiet_output(
                quiet_period_ms=quiet_period_ms,
                max_wait_ms=quiet_max_wait_ms,
            )
        return result

    def shutdown(self):
        """Gracefully shut down the ANSA process."""
        if self._connection:
            try:
                self._connection.goodbye(shutdown=True)
                self._connection.close()
            except Exception:
                pass
            self._connection = None
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=10)
            except Exception:
                self._process.kill()
            self.stop_output_reader()
            self._process = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.shutdown()


# ── Script / result helpers ─────────────────────────────────────────

def _is_backend_result_ok(result):
    """Return True when ANSA IAP call succeeded and payload status is ok (if present)."""
    if not isinstance(result, dict):
        return False
    if not result.get("success"):
        return False

    payload = result.get("result")
    if isinstance(payload, dict) and "status" in payload:
        return payload.get("status") == "ok"
    return True


def _backend_result_error(prefix, result):
    """Build a consistent debug-friendly error string from backend response."""
    if not isinstance(result, dict):
        return f"{prefix}: invalid result type={type(result).__name__}"
    return (
        f"{prefix}: success={result.get('success')}, "
        f"details={result.get('details')}, result={result.get('result')}"
    )


def _inject_script(script: str, function_name: str = "main", **kwargs) -> str:
    """Inject keyword arguments as variable declarations at the top of a function.

    Each kwarg is inserted as a local variable assignment at the beginning of
    the specified function body.  Only built-in types (str, int, float, bool,
    None, list, tuple, dict, set, bytes) are supported.

    Args:
        script: The original script text.
        function_name: Name of the target function to inject into.
        **kwargs: Key-value pairs to declare as variables.
    Returns:
        The modified script text with injected variable declarations.
    """
    if not kwargs:
        return script

    lines = script.splitlines(keepends=True)
    # Locate the "def <function_name>(...):" line
    pattern = f"def {function_name}("
    insert_idx = None
    indent = ""
    for i, line in enumerate(lines):
        if pattern in line:
            # Determine body indent from the next non-empty line
            for j in range(i + 1, len(lines)):
                stripped = lines[j].strip()
                if stripped:
                    indent = lines[j][: len(lines[j]) - len(lines[j].lstrip())]
                    break
            else:
                indent = "    "
            insert_idx = i + 1
            break

    if insert_idx is None:
        raise ValueError(f"Function '{function_name}' not found in script")

    decl_lines = []
    for key, value in kwargs.items():
        decl_lines.append(f"{indent}{key} = {value!r}\n")

    lines[insert_idx:insert_idx] = decl_lines
    return "".join(lines)


def _prepend_path_preamble(script_text: str, script_path: str) -> str:
    """Prepend a preamble that restores the original script path context.

    When ANSA executes a script received via IAP, it saves it to a temp file,
    so ``__file__`` points to the temp directory.  This preamble overrides
    ``__file__`` with the original path and adds the script's directory to
    ``sys.path`` so that relative imports and config-file lookups work.
    """
    script_path = str(script_path).replace("\\", "/")
    script_dir = str(Path(script_path).parent).replace("\\", "/")
    preamble = (
        f"import sys as __sys\n"
        f'__file__ = r"{script_path}"\n'
        f'if r"{script_dir}" not in __sys.path:\n'
        f'    __sys.path.insert(0, r"{script_dir}")\n'
        f"del __sys\n"
    )
    return preamble + script_text


def _resolve_script_content(script):
    """Resolve script input to executable source code.

    Supports:
    - pathlib.Path / os.PathLike: read file content and prepend path preamble
    - str path to an existing file: read file content and prepend path preamble
    - str script body: use as-is (no preamble)
    """
    if isinstance(script, os.PathLike):
        resolved = Path(script).resolve()
        with resolved.open("r", encoding="utf-8") as f:
            content = f.read()
        return _prepend_path_preamble(content, str(resolved))

    if isinstance(script, str):
        try:
            candidate = Path(script).expanduser()
            if candidate.is_file():
                resolved = candidate.resolve()
                with resolved.open("r", encoding="utf-8") as f:
                    content = f.read()
                return _prepend_path_preamble(content, str(resolved))
        except (OSError, ValueError):
            pass
        return script

    return str(script)


# ── Script builder helpers ──────────────────────────────────────────

def build_script(code, imports=None, function_name="main", **kwargs):
    """Build a complete ANSA Python script with imports and entry point.

    Args:
        code: The script body (will be indented inside the function).
        imports: List of import statements (default: ansa basics).
        function_name: Entry function name.
        **kwargs: Additional keyword arguments to pass to the script.
    Returns:
        Tuple of (script_text, function_name).
    """
    if imports is None:
        imports = [
            "import os",
            "import json",
            "import ansa",
            "from ansa import base",
            "from ansa import constants",
            "from ansa import utils",
        ]

    import_block = "\n".join(imports)
    indented = textwrap.indent(code, "    ")

    script = f"""{import_block}

def {function_name}():
{indented}
"""
    script = _inject_script(script, function_name, **kwargs)

    return script, function_name


if __name__ == "__main__":
    # Example usage
    with AnsaProcess() as ansa:
        script = """\
def main():
    print('hello, world!')
"""
        print("Original script:")
        print(script)
        script = _inject_script(script, function_name="main", a='hello', b=True, c=[1, 2, 3], d = {'key': 'value'})
        print("Generated script:")
        print(script)
