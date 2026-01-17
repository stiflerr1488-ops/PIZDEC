from __future__ import annotations

import datetime as dt
import json
import locale
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from app_context import BASE_DIR
from logger import get_logger, log, log_exception
from settings_model import Settings
from utils import ensure_dir, now_stamp

_logger = get_logger()

_SENSITIVE_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASS",
    "PWD",
    "KEY",
    "AUTH",
    "COOKIE",
    "BEARER",
    "SESSION",
)

_KEY_LIBS = [
    "selenium",
    "playwright",
    "requests",
    "httpx",
    "customtkinter",
    "pandas",
    "openpyxl",
    "Pillow",
    "playwright-stealth",
]

_DEFAULT_DOMAINS = [
    "google.com",
    "yandex.ru",
    "yandex.com",
    "yandex.net",
    "ya.ru",
]

_EXPECTED_LOGS = [
    "application.log",
    "error.log",
    "network.log",
    "browser.log",
    "webdriver.log",
    "playwright.log",
    "app.log",
]


def _log_step(message: str, level: str = "info") -> None:
    if level == "warn":
        _logger.warning(message)
    elif level == "error":
        _logger.error(message)
    else:
        _logger.info(message)


def _mask_value(value: str) -> str:
    if not value:
        return ""
    value = str(value)
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _mask_env(env: Iterable[Tuple[str, str]]) -> Dict[str, str]:
    masked: Dict[str, str] = {}
    for key, value in env:
        if any(marker in key.upper() for marker in _SENSITIVE_ENV_MARKERS):
            masked[key] = _mask_value(value)
        else:
            masked[key] = str(value)
    return masked


def _safe_stat(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "size": stat.st_size,
            "mode": oct(stat.st_mode),
            "mtime": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _run_command(cmd: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except Exception as exc:
        return 1, "", str(exc)


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", errors="ignore")


def _build_tree(root: Path, max_depth: int = 4) -> str:
    lines: List[str] = []
    root = root.resolve()
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        try:
            rel = current_path.relative_to(root)
        except ValueError:
            rel = current_path
        depth = len(rel.parts)
        if depth > max_depth:
            dirs[:] = []
            continue
        indent = "  " * depth
        name = "." if not rel.parts else rel.name
        lines.append(f"{indent}{name}/")
        for fname in sorted(files):
            fpath = current_path / fname
            info = _safe_stat(fpath)
            size = info.get("size", "?")
            mode = info.get("mode", "?")
            lines.append(f"{indent}  {fname} (size={size}, mode={mode})")
    return "\n".join(lines)


def _collect_system_info() -> Dict[str, Any]:
    now_local = dt.datetime.now()
    now_utc = dt.datetime.utcnow()
    tz_name = time.tzname
    locale_info = {
        "locale": locale.getlocale(),
        "preferred_encoding": locale.getpreferredencoding(False),
        "filesystem_encoding": sys.getfilesystemencoding(),
    }
    return {
        "os": platform.platform(),
        "os_name": os.name,
        "architecture": platform.machine(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "sys_path": sys.path,
        "timezone": tz_name,
        "time_local": now_local.isoformat(),
        "time_utc": now_utc.isoformat() + "Z",
        "locale": locale_info,
        "environment": _mask_env(os.environ.items()),
    }


def _collect_python_env(project_dir: Path) -> Dict[str, Any]:
    code, out, err = _run_command([sys.executable, "-m", "pip", "freeze"], timeout=60)
    requirements = project_dir / "requirements.txt"
    req_content = requirements.read_text(encoding="utf-8", errors="ignore") if requirements.exists() else ""
    versions: Dict[str, str] = {}
    for name in _KEY_LIBS:
        try:
            versions[name] = metadata.version(name)
        except Exception:
            versions[name] = "not installed"
    is_venv = bool(getattr(sys, "base_prefix", sys.prefix) != sys.prefix)
    return {
        "pip_freeze": out.strip() if code == 0 else "",
        "pip_freeze_error": err.strip() if code != 0 else "",
        "key_lib_versions": versions,
        "is_venv": is_venv,
        "venv_path": os.environ.get("VIRTUAL_ENV", ""),
        "requirements_txt": req_content,
    }


def _dns_lookup(host: str) -> Dict[str, Any]:
    try:
        infos = socket.getaddrinfo(host, None)
        addrs = sorted({info[4][0] for info in infos})
        return {"status": "ok", "addresses": addrs}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _tcp_check(host: str, port: int = 443, timeout: float = 3.0) -> Dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"status": "ok", "port": port}
    except Exception as exc:
        return {"status": "error", "port": port, "error": str(exc)}


def _http_check(url: str, user_agent: str) -> Dict[str, Any]:
    headers = {"User-Agent": user_agent}
    request = urllib.request.Request(url, headers=headers, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            return {
                "status": resp.status,
                "final_url": resp.geturl(),
                "headers": dict(resp.headers),
                "method": "HEAD",
            }
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "error": str(exc), "method": "HEAD"}
    except Exception:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return {
                    "status": resp.status,
                    "final_url": resp.geturl(),
                    "headers": dict(resp.headers),
                    "method": "GET",
                }
        except Exception as exc:
            return {"status": "error", "error": str(exc), "method": "GET"}


def _collect_network(settings: Settings) -> Dict[str, Any]:
    domains = list(_DEFAULT_DOMAINS)
    user_agent = getattr(settings, "browser_user_agent", "") or "PythonDiagnostics/1.0"
    proxy_env = {
        "HTTP_PROXY": os.environ.get("HTTP_PROXY", ""),
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY", ""),
        "NO_PROXY": os.environ.get("NO_PROXY", ""),
    }
    checks: Dict[str, Any] = {}
    for domain in domains:
        host = domain
        checks[domain] = {
            "dns": _dns_lookup(host),
            "tcp_443": _tcp_check(host, 443),
            "https": _http_check(f"https://{domain}", user_agent),
        }
    return {
        "domains": domains,
        "proxy": proxy_env,
        "user_agent": user_agent,
        "stealth": "enabled" if bool(getattr(settings, "stealth_enabled", True)) else "disabled",
        "checks": checks,
    }


def _collect_browser(settings: Settings) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "headless": bool(getattr(settings, "headless", False)),
        "persistent_profile": False,
        "user_agent": getattr(settings, "browser_user_agent", ""),
        "launch_args": ["--no-first-run", "--no-default-browser-check"],
        "yandex_executable": getattr(settings, "yandex_executable_path", ""),
    }

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        info["playwright_available"] = False
        info["playwright_error"] = str(exc)
        return info

    info["playwright_available"] = True
    try:
        with sync_playwright() as p:
            info["chromium_executable"] = p.chromium.executable_path
            info["firefox_executable"] = p.firefox.executable_path
            info["webkit_executable"] = p.webkit.executable_path
            try:
                browser = p.chromium.launch(headless=True)
                info["chromium_version"] = browser.version
                browser.close()
                info["launch_test"] = "ok"
            except Exception as exc:
                info["launch_test"] = f"error: {exc}"
    except Exception as exc:
        info["playwright_init_error"] = str(exc)
    return info


def _collect_files(project_dir: Path) -> Dict[str, Any]:
    disk_usage = shutil.disk_usage(project_dir)
    return {
        "project_tree": _build_tree(project_dir, max_depth=4),
        "disk_usage": {
            "total": disk_usage.total,
            "used": disk_usage.used,
            "free": disk_usage.free,
        },
        "temp_dir": tempfile.gettempdir(),
    }


def _collect_self_checks(project_dir: Path) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    code, out, err = _run_command([sys.executable, "-m", "compileall", str(project_dir)], timeout=120)
    results["compileall"] = {
        "status": "ok" if code == 0 else "error",
        "stdout": out.strip(),
        "stderr": err.strip(),
    }
    imports: Dict[str, str] = {}
    for mod in ["customtkinter", "pandas", "playwright", "playwright_stealth", "requests", "httpx"]:
        try:
            __import__(mod)
            imports[mod] = "ok"
        except Exception as exc:
            imports[mod] = f"error: {exc}"
    results["imports"] = imports
    try:
        from parser_core_serp import build_serp_url
        build_serp_url("test", "moscow")
        results["project_start_without_browser"] = "ok"
    except Exception as exc:
        results["project_start_without_browser"] = f"error: {exc}"
    return results


def _collect_logs(project_dir: Path, diag_dir: Path) -> Dict[str, Any]:
    logs_dir = project_dir / "logs"
    found: List[str] = []
    missing: List[str] = []
    copied: List[str] = []
    target = diag_dir / "logs"
    ensure_dir(target)
    if logs_dir.exists():
        for path in sorted(logs_dir.glob("*.log")):
            try:
                shutil.copy2(path, target / path.name)
                copied.append(path.name)
            except Exception as exc:
                _logger.debug("Failed to copy log", exc_info=exc)
    found = copied
    for name in _EXPECTED_LOGS:
        if name not in found:
            missing.append(name)
    return {
        "logs_dir": str(logs_dir),
        "copied": copied,
        "missing": missing,
    }


def _collect_captcha_artifacts(project_dir: Path) -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {"screenshots": [], "html_snapshots": []}
    for pattern in ("*captcha*.png", "*captcha*.jpg", "*captcha*.html"):
        for path in project_dir.rglob(pattern):
            if path.is_file():
                entry = {"path": str(path), "stat": _safe_stat(path)}
                if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    artifacts["screenshots"].append(entry)
                else:
                    artifacts["html_snapshots"].append(entry)
    return artifacts


def _format_report(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_diagnostic_package(
    project_dir: Path,
    output_dir: Path,
    settings: Settings,
    last_output: Optional[Path] = None,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> Path:
    stamp = now_stamp()
    diag_dir = output_dir / f"diagnostics_{stamp}"
    ensure_dir(diag_dir)

    def emit(message: str, level: str = "info") -> None:
        _log_step(message, level=level)
        if log_callback:
            try:
                log_callback(message, level)
            except Exception:
                _logger.debug("Diagnostics log callback failed", exc_info=True)
        else:
            log(message, level)

    emit("🧰 Диагностика: собираю системную информацию…")
    data: Dict[str, Any] = {
        "system": _collect_system_info(),
    }
    data["settings"] = settings.__dict__.copy()

    emit("📦 Диагностика: собираю Python-окружение…")
    data["python_env"] = _collect_python_env(project_dir)

    emit("🌐 Диагностика: проверяю сеть и доступность…")
    data["network"] = _collect_network(settings)

    emit("🧭 Диагностика: проверяю браузер и драйверы…")
    data["browser"] = _collect_browser(settings)

    emit("🤖 Диагностика: собираю данные по капче…")
    data["captcha"] = _collect_captcha_artifacts(project_dir)

    emit("📂 Диагностика: собираю файловую структуру…")
    data["files"] = _collect_files(project_dir)

    emit("🧪 Диагностика: выполняю self-check…")
    data["self_check"] = _collect_self_checks(project_dir)

    emit("🪵 Диагностика: собираю логи…")
    data["logs"] = _collect_logs(project_dir, diag_dir)

    if last_output and last_output.exists():
        try:
            shutil.copy2(last_output, diag_dir / last_output.name)
            data["last_output"] = str(last_output)
        except Exception as exc:
            data["last_output_error"] = str(exc)

    links_path = output_dir / "links.txt"
    if links_path.exists():
        try:
            shutil.copy2(links_path, diag_dir / "links.txt")
        except Exception as exc:
            data["links_copy_error"] = str(exc)

    settings_path = project_dir / "settings.json"
    if settings_path.exists():
        try:
            shutil.copy2(settings_path, diag_dir / "settings.json")
        except Exception as exc:
            data["settings_copy_error"] = str(exc)

    requirements_path = project_dir / "requirements.txt"
    if requirements_path.exists():
        try:
            shutil.copy2(requirements_path, diag_dir / "requirements.txt")
        except Exception as exc:
            data["requirements_copy_error"] = str(exc)

    report_path = diag_dir / "diagnostics_report.json"
    report_path.write_text(_format_report(data), encoding="utf-8")

    tree_path = diag_dir / "project_tree.txt"
    _write_text(tree_path, data["files"]["project_tree"])

    stdout_info = {
        "stdout": getattr(sys.stdout, "name", repr(sys.stdout)),
        "stderr": getattr(sys.stderr, "name", repr(sys.stderr)),
        "note": "История stdout/stderr недоступна (сессия GUI).",
    }
    (diag_dir / "stdout_stderr.json").write_text(
        json.dumps(stdout_info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    zip_path = output_dir / f"diagnostics_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in diag_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(diag_dir))

    try:
        shutil.rmtree(diag_dir)
    except Exception:
        _logger.debug("Failed to clean diagnostics temp dir", exc_info=True)

    emit(f"📦 Диагностика: пакет готов ({zip_path.name})")
    return zip_path
