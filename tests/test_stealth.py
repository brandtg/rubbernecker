# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from avrokit import avro_reader, parse_url

from rubbernecker.crawl import chromedriver_patch
from rubbernecker.crawl.chromedriver_patch import (
    BARE_CDC_REPLACEMENT,
    get_patched_chromedriver,
    patch_cdc_identifiers,
    random_identifier,
)
from rubbernecker.crawl.driver import CrawlDriver, DriverKind, SeleniumDriver
from rubbernecker.crawl.stealth import StealthDriver, load_evasion_script
from rubbernecker.crawl.tool import CrawlTool, InputFormat, create_driver

# Mimics the JavaScript chromedriver injects, with its fixed cdc_ identifiers
# (observed in chromedriver 157), plus a $-prefixed document property and a
# bare cdc_ reference.
FIXTURE_BINARY = (
    b"(function () {window.cdc_adoQpoasnfa76pfcZLmcfl_Array = window.Array;"
    b"window.cdc_adoQpoasnfa76pfcZLmcfl_Promise = window.Promise;}) ();"
    b"const Array = window.cdc_adoQpoasnfa76pfcZLmcfl_Array || window.Array;"
    b"const Promise = window.cdc_adoQpoasnfa76pfcZLmcfl_Promise || window.Promise;"
    b"var $cdc_asdjflasutopfhvcZLmcfl_ = document.$cdc_asdjflasutopfhvcZLmcfl_;"
    b"console.log('cdc_ bare reference');"
)


def _mock_chrome(monkeypatch) -> list:
    """
    Patch webdriver.Chrome to record (options, service, mock driver) triples.
    """
    created = []

    def fake_chrome(options=None, service=None):
        mock_driver = MagicMock()
        created.append((options, service, mock_driver))
        return mock_driver

    monkeypatch.setattr("rubbernecker.crawl.driver.webdriver.Chrome", fake_chrome)
    return created


def _mock_patched_chromedriver(monkeypatch, path: str = "/tmp/fake-chromedriver"):
    monkeypatch.setattr(
        "rubbernecker.crawl.stealth.get_patched_chromedriver", lambda: path
    )


class TestRandomIdentifier:
    def test_length_and_charset(self):
        identifier = random_identifier(28)
        assert len(identifier) == 28
        assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier)

    def test_random(self):
        assert random_identifier(28) != random_identifier(28)

    def test_rejects_nonpositive_length(self):
        with pytest.raises(ValueError):
            random_identifier(0)


class TestPatchCdcIdentifiers:
    def test_no_cdc_remains(self):
        patched, count = patch_cdc_identifiers(FIXTURE_BINARY)
        assert b"cdc_" not in patched
        assert count > 0

    def test_length_preserved(self):
        patched, _ = patch_cdc_identifiers(FIXTURE_BINARY)
        assert len(patched) == len(FIXTURE_BINARY)

    def test_same_identifier_replaced_consistently(self):
        # Both references to the Array identifier must share one replacement,
        # or chromedriver's injected JavaScript would break.
        data = (
            b"window.cdc_adoQpoasnfa76pfcZLmcfl_Array = window.Array; "
            b"const A = window.cdc_adoQpoasnfa76pfcZLmcfl_Array || window.Array;"
        )
        patched, _ = patch_cdc_identifiers(data)
        tokens = re.findall(rb"window\.([A-Za-z0-9_]+)", patched)
        assert len(tokens) == 4  # 2 assignments + 2 fallbacks
        assert tokens[0] == tokens[2]
        assert tokens[1] == tokens[3]
        assert tokens[0] != tokens[1]

    def test_dollar_prefix_preserved(self):
        patched, _ = patch_cdc_identifiers(b"$cdc_asdjflasutopfhvcZLmcfl_")
        assert patched.startswith(b"$")
        assert len(patched) == len(b"$cdc_asdjflasutopfhvcZLmcfl_")
        assert b"cdc_" not in patched

    def test_non_cdc_bytes_untouched(self):
        data = b"keep me 100% intact cdc_adoQpoasnfa76pfcZLmcfl_Array"
        patched, _ = patch_cdc_identifiers(data)
        assert patched.startswith(b"keep me 100% intact ")

    def test_bare_cdc_replaced_with_fixed_token(self):
        patched, count = patch_cdc_identifiers(b"x cdc_ y")
        assert patched == b"x " + BARE_CDC_REPLACEMENT + b" y"
        assert count == 1

    def test_patch_is_idempotent(self):
        patched, _ = patch_cdc_identifiers(FIXTURE_BINARY)
        repatched, count = patch_cdc_identifiers(patched)
        assert repatched == patched
        assert count == 0


class TestGetPatchedChromedriver:
    def _setup(self, monkeypatch, tmp_path, data: bytes = FIXTURE_BINARY):
        source = tmp_path / "chromedriver"
        source.write_bytes(data)
        cache_dir = tmp_path / "cache"
        monkeypatch.setattr(
            "rubbernecker.crawl.chromedriver_patch._resolve_chromedriver_path",
            lambda: source,
        )
        monkeypatch.setattr(
            "rubbernecker.crawl.chromedriver_patch._cache_dir", lambda: cache_dir
        )
        return source, cache_dir

    def test_creates_cached_patched_copy(self, monkeypatch, tmp_path):
        source, cache_dir = self._setup(monkeypatch, tmp_path)
        path = get_patched_chromedriver()
        target = Path(path)
        assert target != source
        assert cache_dir in target.parents
        assert target.is_file()
        assert target.read_bytes().count(b"cdc_") == 0
        assert len(target.read_bytes()) == source.stat().st_size
        assert os.access(target, os.X_OK)

    def test_reuses_cached_copy(self, monkeypatch, tmp_path):
        self._setup(monkeypatch, tmp_path)
        calls = []
        original = chromedriver_patch.patch_cdc_identifiers

        def spy(data):
            calls.append(data)
            return original(data)

        monkeypatch.setattr(
            "rubbernecker.crawl.chromedriver_patch.patch_cdc_identifiers", spy
        )
        first = get_patched_chromedriver()
        second = get_patched_chromedriver()
        assert first == second
        assert len(calls) == 1

    def test_falls_back_to_unpatched_on_failure(self, monkeypatch, tmp_path):
        source, _ = self._setup(monkeypatch, tmp_path)

        def boom(data):
            raise RuntimeError("cannot patch")

        monkeypatch.setattr(
            "rubbernecker.crawl.chromedriver_patch.patch_cdc_identifiers", boom
        )
        assert get_patched_chromedriver() == str(source)


class TestLoadEvasionScript:
    def test_placeholders_substituted(self):
        script = load_evasion_script()
        assert "__WEBGL_VENDOR__" not in script
        assert "__WEBGL_RENDERER__" not in script
        assert '"Intel Inc."' in script
        assert '"Intel Iris OpenGL Engine"' in script

    def test_custom_webgl_values(self):
        script = load_evasion_script(
            webgl_vendor='In tel" \\ Linux', webgl_renderer="Mesa \\ renderer"
        )
        assert '"In tel\\" \\\\ Linux"' in script
        assert '"Mesa \\\\ renderer"' in script

    def test_covers_known_fingerprints(self):
        script = load_evasion_script()
        assert '"webdriver"' in script
        assert "window.chrome" in script
        assert "navigator.plugins" in script
        assert "navigator.mimeTypes" in script
        assert "navigator.languages" in script
        assert "navigator.permissions" in script
        assert "0x9245" in script
        assert "0x9246" in script


class TestStealthDriver:
    def test_launches_with_patched_driver_and_flag(self, monkeypatch):
        created = _mock_chrome(monkeypatch)
        _mock_patched_chromedriver(monkeypatch)
        StealthDriver(headless=True)
        options, service, _ = created[0]
        assert "--disable-blink-features=AutomationControlled" in options.arguments
        assert "--headless=new" in options.arguments
        assert service.path == "/tmp/fake-chromedriver"

    def test_injects_evasions_on_new_document(self, monkeypatch):
        created = _mock_chrome(monkeypatch)
        _mock_patched_chromedriver(monkeypatch)
        StealthDriver()
        _, _, mock_driver = created[0]
        cmd, payload = mock_driver.execute_cdp_cmd.call_args[0]
        assert cmd == "Page.addScriptToEvaluateOnNewDocument"
        assert "window.chrome" in payload["source"]

    def test_restart_reinjects_evasions(self, monkeypatch):
        created = _mock_chrome(monkeypatch)
        _mock_patched_chromedriver(monkeypatch)
        driver = StealthDriver()
        driver.restart()
        assert len(created) == 2
        assert created[0][2].execute_cdp_cmd.call_count == 1
        assert created[1][2].execute_cdp_cmd.call_count == 1
        assert driver.driver is created[1][2]

    def test_implements_crawl_driver_protocol(self, monkeypatch):
        _mock_chrome(monkeypatch)
        _mock_patched_chromedriver(monkeypatch)
        driver = StealthDriver()
        assert isinstance(driver, CrawlDriver)
        assert isinstance(driver, SeleniumDriver)


class TestDriverSelection:
    def test_create_selenium_driver(self, monkeypatch):
        created = _mock_chrome(monkeypatch)
        driver = create_driver(DriverKind.SELENIUM)
        assert isinstance(driver, SeleniumDriver)
        assert not isinstance(driver, StealthDriver)
        assert "--disable-blink-features" not in created[0][0].arguments

    def test_create_stealth_driver(self, monkeypatch):
        created = _mock_chrome(monkeypatch)
        _mock_patched_chromedriver(monkeypatch)
        driver = create_driver(DriverKind.STEALTH)
        assert isinstance(driver, StealthDriver)
        assert (
            "--disable-blink-features=AutomationControlled" in created[0][0].arguments
        )

    def test_unknown_kind_raises(self):
        with pytest.raises(KeyError):
            create_driver("bogus")  # ty: ignore[invalid-argument-type]


class TestCliDriverOption:
    def _parse(self, argv: list[str]) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="tool", required=True)
        CrawlTool().configure(subparsers)
        return parser.parse_args(argv)

    def test_default_is_selenium(self):
        args = self._parse(["crawl", "input.txt", "output.avro"])
        assert args.driver == DriverKind.SELENIUM

    def test_explicit_stealth(self):
        args = self._parse(["crawl", "input.txt", "output.avro", "--driver", "stealth"])
        assert args.driver == DriverKind.STEALTH


FINGERPRINT_SCRIPT = """
return {
  webdriver: navigator.webdriver,
  chromeObj: typeof window.chrome,
  chromeApp: !!(window.chrome && window.chrome.app),
  plugins: navigator.plugins.length,
  mimeTypes: navigator.mimeTypes.length,
  languages: navigator.languages,
  permissionsQueryNative: /\\[native code\\]/.test(navigator.permissions.query.toString()),
};
"""

WEBGL_SCRIPT = """
const canvas = document.createElement('canvas');
const gl = canvas.getContext('webgl');
if (!gl) return null;
const ext = gl.getExtension('WEBGL_debug_renderer_info');
return {
  vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
  renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL),
};
"""


@pytest.mark.integration
def test_patched_chromedriver_has_no_cdc_strings():
    path = get_patched_chromedriver()
    assert Path(path).read_bytes().count(b"cdc_") == 0


@pytest.mark.integration
def test_stealth_crawl_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        input_url = parse_url(os.path.join(tmpdir, "requests.txt"))
        output_url = parse_url(os.path.join(tmpdir, "output.avro"))
        with input_url.with_mode("w") as f:
            f.write("https://news.ycombinator.com/\n")
            f.write("https://news.ycombinator.com/news\n")
        tool = CrawlTool()
        stats = tool.crawl(
            input_url,
            output_url,
            headless=True,
            input_format=InputFormat.TEXT,
            driver=DriverKind.STEALTH,
        )
        assert stats.count_input == 2
        assert stats.count_output == 2
        assert stats.count_error == 0
        assert output_url.exists()
        with avro_reader(output_url.with_mode("rb")) as reader:
            records = [record for record in reader if isinstance(record, dict)]
        assert len(records) == 2
        assert all(record["body"] for record in records)


@pytest.mark.integration
def test_stealth_fingerprints_masked():
    driver = StealthDriver(headless=True)
    try:
        driver.activate_cdp_mode(
            "data:text/html,<html><head><title>t</title></head><body>hi</body></html>"
        )
        driver.wait_for_ready_state_complete()
        raw = driver.driver
        assert raw is not None
        raw.set_script_timeout(10)
        fp = raw.execute_script(FINGERPRINT_SCRIPT)
        assert fp["webdriver"] is False
        assert fp["chromeObj"] == "object"
        assert fp["chromeApp"]
        assert fp["plugins"] == 5
        assert fp["mimeTypes"] == 2
        assert fp["languages"] == ["en-US", "en"]
        assert fp["permissionsQueryNative"]
        assert raw.execute_script(WEBGL_SCRIPT) == {
            "vendor": "Intel Inc.",
            "renderer": "Intel Iris OpenGL Engine",
        }
        # The permissions patch must return a state consistent with
        # Notification.permission instead of the mismatched native answer.
        notification_permission = raw.execute_script("return Notification.permission")
        queried = raw.execute_async_script(
            "const [done] = arguments;"
            "navigator.permissions.query({name: 'notifications'})"
            ".then((status) => done(status.state));"
        )
        assert queried == notification_permission
    finally:
        driver.quit()
