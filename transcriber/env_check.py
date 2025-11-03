"""Cross-platform environment readiness checks."""

from __future__ import annotations

import importlib.util
import platform
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REQUIRED_PACKAGES: Dict[str, str] = {
    "aiohttp": "aiohttp",
    "numpy": "numpy",
    "pydantic": "pydantic",
    "python-dotenv": "dotenv",
    "sounddevice": "sounddevice",
    "faster-whisper": "faster_whisper",
    "vosk": "vosk",
    "websockets": "websockets",
    "google-auth": "google.auth",
    "requests": "requests",
}

CRITICAL_FILES = [
    "transcriber/__init__.py",
    "transcriber/cli.py",
    "transcriber/config.py",
    "transcriber/audio.py",
    "transcriber/pipeline.py",
    "transcriber/asr/speechmatics_backend.py",
]

DEFAULT_GOOGLE_CREDENTIAL = "gen-lang-client-0219123936-d6e117f5a590.json"


def _print_section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _check_packages() -> Tuple[List[str], List[str]]:
    missing: List[str] = []
    installed: List[str] = []
    for pretty, module_name in REQUIRED_PACKAGES.items():
        if importlib.util.find_spec(module_name) is None:
            missing.append(pretty)
        else:
            installed.append(pretty)
    return installed, missing


def _read_env_pairs(env_path: Path) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    try:
        with env_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                pairs[key.strip()] = value.strip().strip('"')
    except FileNotFoundError:
        pass
    return pairs


def _section_packages(installed: Iterable[str], missing: Iterable[str]) -> None:
    _print_section("3. パッケージインストール状況 / Package status")
    for name in sorted(installed):
        print(f"  ✓ {name}")
    for name in sorted(missing):
        print(f"  ✗ {name} (missing)")


def _section_files() -> List[str]:
    _print_section("4. 主要ファイル確認 / Required files")
    missing: List[str] = []
    for rel in CRITICAL_FILES:
        path = Path(rel)
        if path.exists():
            print(f"  ✓ {rel}")
        else:
            print(f"  ✗ {rel}")
            missing.append(rel)
    return missing


def _section_logs_and_env(env_pairs: Dict[str, str]) -> Tuple[bool, List[str], List[str]]:
    issues: List[str] = []
    warnings: List[str] = []
    _print_section("5. ログ/設定ファイル確認 / Logs & .env")

    logs_dir = Path("logs")
    if logs_dir.exists():
        print(f"  ✓ logs directory: {logs_dir}")
    else:
        print("  ✗ logs directory missing")
        issues.append("Create the logs/ directory")

    env_path = Path(".env")
    if env_path.exists():
        print(f"  ✓ .env present ({env_path})")
    else:
        print("  ✗ .env not found")
        issues.append("Copy .env.example to .env and populate secrets")
        return False, issues, warnings

    critical_keys = [
        ("SPEECHMATICS_API_KEY", True),
        ("AUDIO_DEVICE_INDEX", False),
        ("GOOGLE_TRANSLATE_CREDENTIALS_PATH", True),
    ]

    print("\n  Key settings:")
    for key, required in critical_keys:
        if key in env_pairs:
            value = env_pairs[key]
            if key == "SPEECHMATICS_API_KEY":
                status = "*** set ***" if value and value != "***" else "not configured"
                print(f"    {key} = {status}")
                if not value or value == "***":
                    issues.append("SPEECHMATICS_API_KEY not set in .env")
            elif key == "AUDIO_DEVICE_INDEX":
                if value:
                    print(f"    {key} = {value}")
                else:
                    print(f"    {key} = (auto: system default input)")
                    warnings.append("AUDIO_DEVICE_INDEX left empty; using system default input.")
            else:  # GOOGLE_TRANSLATE_CREDENTIALS_PATH
                status = value or "not configured"
                print(f"    {key} = {status}")
                if not value:
                    issues.append("GOOGLE_TRANSLATE_CREDENTIALS_PATH not set in .env")
        else:
            if required:
                print(f"    {key} = (missing)")
                issues.append(f"{key} not set in .env")
            else:
                print(f"    {key} = (auto: system default input)")
                warnings.append("AUDIO_DEVICE_INDEX not set; using system default input.")

    return True, issues, warnings


def _section_credentials(env_pairs: Dict[str, str]) -> None:
    _print_section("6. Google 認証ファイル / Google credentials")
    credential_path = env_pairs.get(
        "GOOGLE_TRANSLATE_CREDENTIALS_PATH", DEFAULT_GOOGLE_CREDENTIAL
    )
    path = Path(credential_path).expanduser()
    if path.exists():
        print(f"  ✓ {path} found")
    else:
        print(f"  ✗ Credential file missing: {path}")


def _print_os_guidance() -> None:
    _print_section("7. OS別ガイダンス / OS guidance")
    system = platform.system().lower()
    if system == "windows":
        print("  - Run scripts/check_environment.py from PowerShell to validate packages.")
        print("  - Use scripts/setup_audio_loopback_windows.ps1 to inspect Stereo Mix / VB-Audio.")
        print("  - VoiceMeeter / CABLE Input are recommended for loopback.")
    elif system == "darwin":
        print("  - Install BlackHole via Homebrew and create a Multi-Output Device.")
        print("  - Run scripts/setup_audio_loopback_macos.sh for status hints.")
    elif system == "linux":
        print("  - Ensure PipeWire/PulseAudio has a monitor source. scripts/setup_audio_loopback_linux.sh can auto-configure.")
        print("  - After setup, python -m transcriber.cli --diagnose-audio should list monitor candidates.")
    else:
        print(f"  - Unrecognised OS '{system}'. Verify loopback routing manually.")


def run_environment_check() -> bool:
    """Run environment diagnostics; returns True when ready to run."""

    _print_section("Environment readiness check")
    print(f"Platform : {platform.platform()}")
    print(f"Python   : {sys.version}")
    print(f"Executable: {sys.executable}")

    _print_section("2. requirements.txt preview")
    req_path = Path("requirements.txt")
    if req_path.exists():
        for line in req_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                print(f"  - {stripped}")
    else:
        print("  requirements.txt not found")

    installed, missing = _check_packages()
    _section_packages(installed, missing)

    missing_files = _section_files()

    env_pairs = _read_env_pairs(Path(".env"))
    env_ok, env_issues, env_warnings = _section_logs_and_env(env_pairs)
    _section_credentials(env_pairs)
    _print_os_guidance()

    _print_section("8. 総合結果 / Summary")
    issues: List[str] = []
    warnings: List[str] = env_warnings.copy()
    if missing:
        issues.append(f"Missing packages: {', '.join(missing)}")
    if missing_files:
        issues.append(f"Missing files: {', '.join(missing_files)}")
    issues.extend(env_issues)

    if issues:
        print("  ✗ Not ready yet. Address the following:")
        for idx, issue in enumerate(issues, 1):
            print(f"    {idx}. {issue}")
        print("\n  → Re-run scripts/check_environment.py after completing the steps.")
        ready = False
    else:
        if warnings:
            print("  ✓ Base system ready. Optional settings were left in auto mode:")
            for warn in warnings:
                print(f"    - {warn}")
        else:
            print("  ✓ All checks passed. You can launch the pipeline.")
        ready = env_ok

    print("\n" + "=" * 60)
    print("  Check complete")
    print("=" * 60)
    return ready
