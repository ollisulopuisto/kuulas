"""Credential transport checks use dummy data, never a real Apple account."""

import importlib.util
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

SPEC = importlib.util.spec_from_file_location(
    "macos_ci_credentials", Path(__file__).resolve().parents[1]
    / "scripts/macos_ci_credentials.py",
)
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


def test_security_credentials_are_only_in_stdin(tmp_path):
    value = 'dummy "quote" \\ backslash $value'
    with patch.dict(os.environ, {"KEYCHAIN_PASSWORD": value}), patch.object(
        HELPER.subprocess, "run", return_value=subprocess.CompletedProcess([], 0),
    ) as run:
        HELPER.security("create-keychain", "-p", value, str(tmp_path / "test.keychain"))
    args, kwargs = run.call_args
    assert args[0] == ["/usr/bin/security", "-i"]
    assert value not in str(args)
    assert "KEYCHAIN_PASSWORD" not in kwargs["env"]
    assert '\\"quote\\"' in kwargs["input"]
    assert "\\\\ backslash" in kwargs["input"]


@pytest.mark.parametrize("value", ["a\nb", "a\rb", "a\0b"])
def test_security_line_protocol_rejects_command_separators(value):
    with pytest.raises(ValueError, match="line separator"):
        HELPER.quote(value)


def test_security_failure_does_not_echo_secret(tmp_path):
    with patch.object(
        HELPER.subprocess, "run",
        return_value=subprocess.CompletedProcess([], 1, "secret", "secret"),
    ), pytest.raises(RuntimeError, match="output withheld") as error:
        HELPER.security("create-keychain", "-p", "secret", str(tmp_path / "keychain"))
    assert "secret" not in str(error.value)


def test_import_keeps_all_passwords_off_argv(tmp_path):
    env = {"KEYCHAIN_PATH": str(tmp_path / "keychain"),
           "CERTIFICATE_PATH": str(tmp_path / "cert.p12"),
           "KEYCHAIN_PASSWORD": "dummy-keychain", "P12_PASSWORD": "dummy-p12"}
    with patch.dict(os.environ, env), patch.object(
        HELPER.subprocess, "run", return_value=subprocess.CompletedProcess([], 0),
    ) as run:
        HELPER.import_certificate()
    assert len(run.call_args_list) == 8
    for call in run.call_args_list:
        assert call.args[0] == ["/usr/bin/security", "-i"]
        assert "dummy-keychain" not in str(call.args)
        assert "dummy-p12" not in str(call.args)
        assert "P12_PASSWORD" not in call.kwargs["env"]


def test_notary_password_uses_private_tty_not_argv_or_environment(tmp_path):
    executable = tmp_path / "xcrun"
    marker = tmp_path / "passed"
    executable.write_text(
        '#!/usr/bin/env python3\n'
        'import getpass, os, pathlib, sys\n'
        'if "--password" in sys.argv or "APPLE_APP_PASSWORD" in os.environ:\n'
        '    raise SystemExit(4)\n'
        'value = getpass.getpass("App-specific password: ")\n'
        'if value != "dummy-apple": raise SystemExit(5)\n'
        'pathlib.Path(os.environ["TEST_MARKER"]).write_text("passed")\n'
    )
    executable.chmod(0o700)
    env = {"PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
           "APPLE_APP_PASSWORD": "dummy-apple", "APPLE_ID": "test@example.invalid",
           "APPLE_TEAM_ID": "DUMMYTEAM", "KEYCHAIN_PATH": str(tmp_path / "keychain"),
           "TEST_MARKER": str(marker)}
    with patch.dict(os.environ, env):
        HELPER.store_notary_credentials()
    assert marker.read_text() == "passed"


def test_security_stderr_command_failure_with_zero_process_exit():
    with patch.object(HELPER.subprocess, "run", return_value=(
        subprocess.CompletedProcess([], 0, "", "unlock-keychain: returned -25293\n")
    )), pytest.raises(RuntimeError, match="output withheld"):
        HELPER.security("unlock-keychain", "-p", "dummy", "/dummy/keychain")


def test_import_preserves_original_and_new_search_paths():
    env = {"KEYCHAIN_PATH": "/dummy/new", "CERTIFICATE_PATH": "/dummy/cert",
           "KEYCHAIN_PASSWORD": "dummy", "P12_PASSWORD": "dummy"}
    with patch.dict(os.environ, env), patch.object(HELPER, "security", side_effect=[
        '"/original with spaces"\n', "", "", "", "", "",
        '"/concurrent"\n', "",
    ]) as run:
        HELPER.import_certificate()
    assert run.call_args.args == ("list-keychains", "-d", "user", "-s",
                                  "/original with spaces", "/concurrent", "/dummy/new")


def test_search_list_preserves_literal_quotes_and_backslashes():
    value = '/dummy/work "2026" \\ keychain.keychain-db'
    assert HELPER.keychain_paths('    "' + value + '"\n') == [value]
    with pytest.raises(RuntimeError, match="Unexpected keychain"):
        HELPER.keychain_paths('security> "/dummy/path"\n')
