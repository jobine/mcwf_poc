"""Tests for backend.app.core.ansa — AnsaProcess & AnsaConnection."""

import socket
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from backend.app.core.ansa_backend import (
    _IE,
    _Tag,
    _MessageCode,
    _MessageType,
    _MessageHeader,
    _ResultCode,
    _ScriptExecutionDetails,
    _ScriptReturnType,
    _pack_ies,
    AnsaConnection,
    AnsaProcess,
)


# ── AnsaConnection ──────────────────────────────────────────────────

class TestAnsaConnection:
    @patch('socket.socket')
    def test_connect_success(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect.return_value = None

        conn = AnsaConnection(12345, timeout=5)
        mock_sock.connect.assert_called_once_with(('localhost', 12345))

    @patch('socket.socket')
    def test_connect_timeout(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect.side_effect = socket.error("refused")

        with pytest.raises(RuntimeError, match="Could not connect"):
            AnsaConnection(12345, timeout=2)

    @patch('socket.socket')
    def test_hello(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect.return_value = None

        # Build a valid hello response
        resp_ies = [_IE(_Tag.result_code, _ResultCode.success)]
        resp_payload = _pack_ies(resp_ies)
        resp_hdr = _MessageHeader(1, _MessageType.response, 0,
                                  _MessageCode.hello, 0,
                                  16 + len(resp_payload))
        resp_data = resp_hdr.pack() + resp_payload
        mock_sock.recv.side_effect = [resp_data[:16], resp_data[16:]]

        conn = AnsaConnection(12345, timeout=5)
        assert conn.hello() is True

    @patch('socket.socket')
    def test_hello_failure(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect.return_value = None

        # Build a failed hello response
        resp_ies = [_IE(_Tag.result_code, 0xFF)]
        resp_payload = _pack_ies(resp_ies)
        resp_hdr = _MessageHeader(1, _MessageType.response, 0,
                                  _MessageCode.hello, 0,
                                  16 + len(resp_payload))
        resp_data = resp_hdr.pack() + resp_payload
        mock_sock.recv.side_effect = [resp_data[:16], resp_data[16:]]

        conn = AnsaConnection(12345, timeout=5)
        with pytest.raises(RuntimeError, match="handshake failed"):
            conn.hello()

    @patch('socket.socket')
    def test_run_script(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect.return_value = None

        # Build a successful script response
        resp_ies = [
            _IE(_Tag.result_code, _ResultCode.success),
            _IE(_Tag.script_execution_details, _ScriptExecutionDetails.success),
            _IE(_Tag.script_return_type, _ScriptReturnType.none),
        ]
        resp_payload = _pack_ies(resp_ies)
        resp_hdr = _MessageHeader(1, _MessageType.response, 1,
                                  _MessageCode.execute_script, 0,
                                  16 + len(resp_payload))
        resp_data = resp_hdr.pack() + resp_payload
        mock_sock.recv.side_effect = [resp_data[:16], resp_data[16:]]

        conn = AnsaConnection(12345, timeout=5)
        result = conn.run_script("print('hello')")

        assert result['success'] is True
        assert result['details'] == _ScriptExecutionDetails.success
        assert result['return_type'] == _ScriptReturnType.none
        assert result['result'] is None

    @patch('socket.socket')
    def test_goodbye(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect.return_value = None

        # Build a goodbye response
        resp_ies = [_IE(_Tag.result_code, _ResultCode.success)]
        resp_payload = _pack_ies(resp_ies)
        resp_hdr = _MessageHeader(1, _MessageType.response, 0,
                                  _MessageCode.goodbye, 0,
                                  16 + len(resp_payload))
        resp_data = resp_hdr.pack() + resp_payload
        mock_sock.recv.side_effect = [resp_data[:16], resp_data[16:]]

        conn = AnsaConnection(12345, timeout=5)
        assert conn.goodbye(shutdown=True) is True

    @patch('socket.socket')
    def test_close(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect.return_value = None

        conn = AnsaConnection(12345, timeout=5)
        conn.close()
        mock_sock.close.assert_called_once()

    @patch('socket.socket')
    def test_next_txn_increments(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.connect.return_value = None

        conn = AnsaConnection(12345, timeout=5)
        assert conn._next_txn() == 0
        assert conn._next_txn() == 1
        assert conn._next_txn() == 2


# ── AnsaProcess ─────────────────────────────────────────────────────

class TestAnsaProcess:
    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    def test_init_default(self, _mock_port, _mock_find, mock_popen):
        proc = AnsaProcess()
        assert proc.port == 9999
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert '/usr/bin/ansa' in cmd
        assert '-listenport' in cmd
        assert '9999' in cmd
        assert '-b' in cmd

    @patch('subprocess.Popen')
    @patch('app.core.ansa._free_port', return_value=8888)
    def test_init_custom_command(self, _mock_port, mock_popen):
        proc = AnsaProcess(ansa_command='/opt/ansa', batch=False, port=7777)
        assert proc.port == 7777
        cmd = mock_popen.call_args[0][0]
        assert '/opt/ansa' in cmd
        assert '-b' not in cmd

    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    def test_extra_args(self, _mock_port, _mock_find, mock_popen):
        proc = AnsaProcess(extra_args=['-nologo', '-silent'])
        cmd = mock_popen.call_args[0][0]
        assert '-nologo' in cmd
        assert '-silent' in cmd

    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    @patch('app.core.ansa.AnsaConnection')
    def test_connect(self, mock_conn_cls, _mock_port, _mock_find, _mock_popen):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn

        proc = AnsaProcess()
        result = proc.connect()
        mock_conn_cls.assert_called_once_with(9999, 120)
        mock_conn.hello.assert_called_once()
        assert result is mock_conn

    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    @patch('app.core.ansa.AnsaConnection')
    def test_connection_property_lazy(self, mock_conn_cls, _mock_port, _mock_find, _mock_popen):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn

        proc = AnsaProcess()
        assert proc._connection is None
        _ = proc.connection
        mock_conn_cls.assert_called_once()
        assert proc._connection is mock_conn

    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    @patch('app.core.ansa.AnsaConnection')
    def test_run_script_delegates(self, mock_conn_cls, _mock_port, _mock_find, _mock_popen):
        mock_conn = MagicMock()
        mock_conn.run_script.return_value = {'success': True}
        mock_conn_cls.return_value = mock_conn

        proc = AnsaProcess()
        result = proc.run_script("code", "func", keep_database=False)
        mock_conn.run_script.assert_called_once_with("code", "func", False)
        assert result == {'success': True}

    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    def test_shutdown(self, _mock_port, _mock_find, mock_popen):
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        proc = AnsaProcess()
        mock_conn = MagicMock()
        proc._connection = mock_conn

        proc.shutdown()
        mock_conn.goodbye.assert_called_once_with(shutdown=True)
        mock_conn.close.assert_called_once()
        mock_proc.terminate.assert_called_once()
        assert proc._connection is None
        assert proc._process is None

    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    def test_shutdown_force_kill_on_timeout(self, _mock_port, _mock_find, mock_popen):
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd='ansa', timeout=10)
        mock_popen.return_value = mock_proc

        proc = AnsaProcess()
        proc.shutdown()
        mock_proc.kill.assert_called_once()

    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    @patch('app.core.ansa.AnsaConnection')
    def test_context_manager(self, mock_conn_cls, _mock_port, _mock_find, mock_popen):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        with AnsaProcess() as proc:
            assert proc._connection is mock_conn
        mock_conn.goodbye.assert_called_once_with(shutdown=True)


# ── start_stdout_reader ─────────────────────────────────────────────

class TestStartStdoutReader:
    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    def test_reads_lines_via_callback(self, _mock_port, _mock_find, mock_popen):
        mock_proc = MagicMock()
        # Simulate stdout producing two lines then EOF
        mock_proc.stdout.readline.side_effect = [
            b'hello world\n', b'line two\r\n', b''
        ]
        mock_popen.return_value = mock_proc

        collected = []
        proc = AnsaProcess()
        proc.start_stdout_reader(callback=collected.append)
        proc._stdout_thread.join(timeout=2)

        assert collected == ['hello world', 'line two']

    @patch('subprocess.Popen')
    @patch('app.core.ansa.find_ansa', return_value='/usr/bin/ansa')
    @patch('app.core.ansa._free_port', return_value=9999)
    def test_only_starts_once(self, _mock_port, _mock_find, mock_popen):
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [b'']
        mock_popen.return_value = mock_proc

        proc = AnsaProcess()
        proc.start_stdout_reader(callback=lambda x: None)
        first_thread = proc._stdout_thread
        proc.start_stdout_reader(callback=lambda x: None)
        assert proc._stdout_thread is first_thread

