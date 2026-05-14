"""
Claude tool definitions and their implementations.

Nova has these tools:
  execute_shell    – run any shell command (full Termux access)
  read_file        – read file contents
  write_file       – write/overwrite a file
  list_directory   – ls a path
  http_request     – make HTTP GET / POST (for API calls, webhooks, etc.)
  ssh_command      – run a command on the configured VPS over SSH
  device_info      – dump Android/Termux device info

All commands run with the same UID as the Termux process. Dangerous commands
(rm -rf /, dd, mkfs) are warned about but not blocked — Nova trusts you.
"""

import json
import os
import shlex
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Optional


# ── SAFE_MODE guard ───────────────────────────────────────────────────────────

_DANGEROUS_PATTERNS = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    "> /dev/sd",
    ":(){ :|: & };:",   # fork bomb
    "chmod -R 000 /",
]


def _warn_if_dangerous(cmd: str) -> Optional[str]:
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in cmd:
            return f"[WARNING] Command contains potentially destructive pattern: '{pattern}'"
    return None


# ── Tool implementations ──────────────────────────────────────────────────────

def execute_shell(command: str, timeout: int = 120, workdir: str = "") -> str:
    """Run a shell command and return combined stdout+stderr."""
    warn = _warn_if_dangerous(command)
    prefix = f"{warn}\n\n" if warn else ""

    kwargs: dict[str, Any] = {
        "shell": True,
        "executable": "/bin/bash",
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "env": {**os.environ},
    }
    if workdir:
        kwargs["cwd"] = workdir

    try:
        r = subprocess.run(command, **kwargs)
        out = r.stdout or ""
        err = r.stderr or ""
        combined = (out + err).rstrip()
        if not combined:
            combined = f"[exit {r.returncode}]"
        return f"{prefix}{combined}"
    except subprocess.TimeoutExpired:
        return f"{prefix}[ERROR] Command timed out after {timeout}s"
    except Exception as e:
        return f"{prefix}[ERROR] {e}"


def read_file(path: str, max_bytes: int = 200_000) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"[ERROR] File not found: {path}"
    if not p.is_file():
        return f"[ERROR] Not a file: {path}"
    try:
        raw = p.read_bytes()[:max_bytes]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return f"[binary file, {len(raw)} bytes shown as hex]\n{raw[:512].hex()}"
    except PermissionError:
        return f"[ERROR] Permission denied: {path}"


def write_file(path: str, content: str, append: bool = False) -> str:
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with p.open(mode, encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} chars to {p}"
    except Exception as e:
        return f"[ERROR] {e}"


def list_directory(path: str = ".", show_hidden: bool = True) -> str:
    try:
        r = subprocess.run(
            ["ls", "-lah" if show_hidden else "-lh", path],
            capture_output=True, text=True, timeout=10,
        )
        return (r.stdout + r.stderr).rstrip() or "[empty]"
    except Exception as e:
        return f"[ERROR] {e}"


def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[dict] = None,
    body: str = "",
    timeout: int = 30,
) -> str:
    import urllib.request
    import urllib.error

    method = method.upper()
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    data = body.encode() if body else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            raw = resp.read(50_000)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw[:256].hex()
            return f"HTTP {resp.status}\n{dict(resp.headers)}\n\n{text}"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason}\n{e.read(4096).decode(errors='replace')}"
    except Exception as e:
        return f"[ERROR] {e}"


def ssh_command(command: str, host: str = "", user: str = "", key_path: str = "") -> str:
    """Run a command on the VPS via SSH. Falls back to cfg values if not supplied."""
    from config import cfg

    host = host or cfg.VPS_HOST
    user = user or cfg.VPS_USER
    key_path = key_path or cfg.VPS_SSH_KEY

    if not host:
        return "[ERROR] VPS_HOST not configured. Set it in .env or pass host= argument."

    ssh_cmd = [
        "ssh",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        f"{user}@{host}",
        command,
    ]
    try:
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=60)
        return (r.stdout + r.stderr).rstrip() or f"[exit {r.returncode}]"
    except subprocess.TimeoutExpired:
        return "[ERROR] SSH command timed out"
    except Exception as e:
        return f"[ERROR] {e}"


def device_info() -> str:
    snippets: list[str] = []
    for cmd in [
        "uname -a",
        "id",
        "pwd",
        "df -h /",
        "free -m 2>/dev/null || cat /proc/meminfo | head -5",
        "ip addr show 2>/dev/null | grep -E 'inet |ether' | head -20",
        "getprop ro.product.model 2>/dev/null || echo 'not android'",
        "termux-info 2>/dev/null | head -20 || echo 'termux-api not installed'",
    ]:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        snippets.append(f"$ {cmd}\n{(r.stdout+r.stderr).strip()}")
    return "\n\n".join(snippets)


# ── Claude tool schemas ────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "execute_shell",
        "description": (
            "Execute any shell command in Termux (full Bash shell). "
            "Use this for terminal operations: nmap, adb, ssh, git, curl, python, "
            "file manipulation, process management, network tools, package installs, etc. "
            "stdout and stderr are combined and returned. "
            "Commands run as the Termux user with its full environment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command or pipeline to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to wait (default 120).",
                    "default": 120,
                },
                "workdir": {
                    "type": "string",
                    "description": "Working directory (default: current dir).",
                    "default": "",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file. Returns text or hex for binary files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or ~ path to the file."},
                "max_bytes": {
                    "type": "integer",
                    "description": "Max bytes to read (default 200000).",
                    "default": 200000,
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write or append text content to a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write."},
                "content": {"type": "string", "description": "Text content to write."},
                "append": {
                    "type": "boolean",
                    "description": "If true, append instead of overwrite.",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and directories at a path (like ls -lah).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path.", "default": "."},
                "show_hidden": {
                    "type": "boolean",
                    "description": "Include dotfiles.",
                    "default": True,
                },
            },
            "required": [],
        },
    },
    {
        "name": "http_request",
        "description": (
            "Make an HTTP request (GET, POST, PUT, DELETE, etc.). "
            "Useful for API calls, webhooks, checking services."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "default": "GET"},
                "headers": {
                    "type": "object",
                    "description": "Optional headers dict.",
                    "default": {},
                },
                "body": {"type": "string", "description": "Request body string.", "default": ""},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["url"],
        },
    },
    {
        "name": "ssh_command",
        "description": (
            "Run a command on the configured VPS via SSH. "
            "Uses VPS_HOST / VPS_USER / VPS_SSH_KEY from .env by default. "
            "Use for VPS management, WireGuard, Tailscale, Hak5 device control."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run on VPS."},
                "host": {"type": "string", "description": "Override VPS host.", "default": ""},
                "user": {"type": "string", "description": "Override SSH user.", "default": ""},
                "key_path": {
                    "type": "string",
                    "description": "Override SSH key path.",
                    "default": "",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "device_info",
        "description": "Return device/environment info: OS, IP addresses, memory, disk, etc.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# ── Dispatcher ─────────────────────────────────────────────────────────────────

_HANDLERS = {
    "execute_shell": execute_shell,
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
    "http_request": http_request,
    "ssh_command": ssh_command,
    "device_info": lambda **_: device_info(),
}


def dispatch(tool_name: str, tool_input: dict) -> str:
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return f"[ERROR] Unknown tool: {tool_name}"
    try:
        return str(handler(**tool_input))
    except Exception as e:
        return f"[ERROR] Tool '{tool_name}' raised: {e}"
