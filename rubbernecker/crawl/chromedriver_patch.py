# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

"""
Chromedriver binary patcher.

chromedriver injects JavaScript into every page that stashes references to
window constructors under fixed cdc_* identifiers (e.g.
cdc_adoQpoasnfa76pfcZLmcfl_Array); bot detectors scan for those names on
window and document. This module makes a cached copy of the
Selenium-Manager-resolved chromedriver binary with every cdc_* identifier
replaced by a same-length random identifier, and returns the path to the
patched binary.

The patch preserves all byte lengths and maps every occurrence of a given
identifier to the same replacement, so the injected JavaScript keeps working.
"""

import hashlib
import logging
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
from pathlib import Path

from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.driver_finder import DriverFinder

logger = logging.getLogger(__name__)

# chromedriver embeds its injected JavaScript with identifiers of the form
# (optionally $-)prefixed cdc_ plus a fixed-length alphanumeric suffix. Match
# the entire identifier so replacements remain valid JavaScript, and bound the
# match so a cdc_ occurrence cannot swallow neighboring strings.
CDC_IDENTIFIER_PATTERN = re.compile(rb"[$]?cdc_[A-Za-z0-9_]{20,40}")

# Fallback for cdc_ byte sequences that are not part of a full identifier
# (length-stable, and consistent across the binary so references keep working).
BARE_CDC_REPLACEMENT = b"qzx_"


def random_identifier(length: int) -> str:
    """
    Generate a random JavaScript identifier of the given length.

    Starts with a letter or underscore so the result is valid even when some
    chromedriver builds prefix the identifier with $.

    :param length: Desired length.
    :return: The identifier.
    """
    if length < 1:
        raise ValueError("Identifier length must be positive")
    alphabet = string.ascii_letters + string.digits + "_"
    first = secrets.choice(string.ascii_letters + "_")
    return first + "".join(secrets.choice(alphabet) for _ in range(length - 1))


def patch_cdc_identifiers(data: bytes) -> tuple[bytes, int]:
    """
    Neutralize every cdc_* identifier in a chromedriver binary image.

    Each distinct identifier is replaced by a single same-length random
    identifier — all occurrences share the replacement so internal references
    stay consistent — and any remaining bare cdc_ byte sequences are replaced
    with a fixed same-length token.

    :param data: The binary image.
    :return: Tuple of (patched image, number of occurrences replaced).
    """
    replacements: dict[bytes, bytes] = {}
    count = 0

    def replace(match: re.Match) -> bytes:
        nonlocal count
        identifier = match.group(0)
        if identifier not in replacements:
            prefix = b"$" if identifier.startswith(b"$") else b""
            body = random_identifier(len(identifier) - len(prefix))
            replacements[identifier] = prefix + body.encode("ascii")
        count += 1
        return replacements[identifier]

    patched = CDC_IDENTIFIER_PATTERN.sub(replace, data)
    count += patched.count(b"cdc_")
    patched = patched.replace(b"cdc_", BARE_CDC_REPLACEMENT)
    return patched, count


def _resign(path: Path) -> None:
    """
    Re-sign a patched binary ad hoc on macOS, where modifying an executable
    invalidates its code signature and Gatekeeper refuses to launch it.

    :param path: Path to the patched binary.
    :return: None
    """
    if sys.platform != "darwin":
        return
    if shutil.which("codesign") is None:
        logger.warning(
            "codesign not found; the patched chromedriver may be rejected by Gatekeeper"
        )
        return
    result = subprocess.run(
        ["codesign", "--force", "--sign", "-", str(path)],
        capture_output=True,
    )
    if result.returncode != 0:
        logger.warning(
            "Ad hoc re-signing of %s failed: %s",
            path,
            result.stderr.decode(errors="replace").strip(),
        )


def _cache_dir() -> Path:
    """
    Return the per-user cache directory for patched chromedriver copies.

    :return: The cache directory.
    """
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return Path(base) / "rubbernecker" / "chromedriver"


def _resolve_chromedriver_path() -> Path:
    """
    Ask Selenium Manager for the chromedriver binary (downloading it if
    necessary), mirroring how SeleniumDriver resolves it.

    :return: Path to the chromedriver binary.
    """
    return Path(DriverFinder(Service(), ChromeOptions()).get_driver_path())


def get_patched_chromedriver() -> str:
    """
    Resolve chromedriver via Selenium Manager and return the path to a cached
    copy with its cdc_* identifiers neutralized.

    The patched copy is keyed by the source binary's SHA-256 digest, so
    Selenium Manager upgrades naturally produce fresh copies. If patching
    fails, the unpatched binary is used and a warning is logged: stealth is
    degraded, but crawling still works.

    :return: Path to the (patched) chromedriver binary.
    """
    source = _resolve_chromedriver_path()
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    target = _cache_dir() / digest[:16] / source.name
    if target.is_file():
        return str(target)
    try:
        patched, count = patch_cdc_identifiers(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(patched)
        os.chmod(target, 0o755)
        _resign(target)
        logger.info("Patched %d cdc_ occurrence(s) in %s -> %s", count, source, target)
    except Exception as e:
        logger.warning(
            "Failed to patch chromedriver (%s); "
            "using the unpatched binary and degrading stealth",
            e,
        )
        return str(source)
    return str(target)
