# -*- coding: utf-8 -*-
"""Run the 2021 Selenium-3 course-selection script on a modern Selenium.

The original script expects Selenium 3:
  * webdriver.Chrome(executable_path=..., chrome_options=...) -> TypeError on Selenium 4
  * driver.find_element_by_xpath(...) / find_elements_by_*    -> AttributeError on Selenium 4
The site also moved to https while the script still checks for an "http://" URL.

This wrapper leaves the original script untouched: it restores the old helpers,
runs the original script in this interpreter, then reports what happened.

Usage, from the repository root:
    python3 compat_run.py
"""

import os
import runpy
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

TARGET = "东南大学选课助手.py"
HOST = "newxk.urp.seu.edu.cn"


def log(message):
    print("[compat] " + str(message), file=sys.stderr, flush=True)


# --- 1. bring back the Selenium 3 find_element_by_* helpers -------------

_LOCATORS = {
    "id": By.ID,
    "name": By.NAME,
    "xpath": By.XPATH,
    "link_text": By.LINK_TEXT,
    "partial_link_text": By.PARTIAL_LINK_TEXT,
    "tag_name": By.TAG_NAME,
    "class_name": By.CLASS_NAME,
    "css_selector": By.CSS_SELECTOR,
}


def _make_one(locator):
    def find_one(self, value):
        return self.find_element(locator, value)

    return find_one


def _make_many(locator):
    def find_many(self, value):
        return self.find_elements(locator, value)

    return find_many


for _suffix, _locator in _LOCATORS.items():
    setattr(WebDriver, "find_element_by_" + _suffix, _make_one(_locator))
    setattr(WebDriver, "find_elements_by_" + _suffix, _make_many(_locator))


# --- 2. accept the old webdriver.Chrome keyword arguments --------------

_last_driver = None
_real_chrome = webdriver.Chrome


def _chrome(*args, **kwargs):
    global _last_driver
    kwargs.pop("executable_path", None)  # Selenium 3 spelling
    legacy_options = kwargs.pop("chrome_options", None)
    if legacy_options is not None and "options" not in kwargs:
        kwargs["options"] = legacy_options
    try:
        driver = _real_chrome(*args, **kwargs)
    except Exception as exc:
        log("FAILED to start Chrome: %r" % (exc,))
        raise
    _last_driver = driver
    log("Chrome started")
    return driver


webdriver.Chrome = _chrome


# --- 3. log every page the script opens --------------------------------

_real_get = WebDriver.get


def _get(self, url):
    log("opening " + str(url))
    _real_get(self, url)
    try:
        log("page title: " + str(self.title))
    except Exception:
        pass


WebDriver.get = _get


# --- 4. let the legacy "http://" URL check pass on today's https site --

_real_current_url = WebDriver.current_url
_https_notice_shown = False


def _rewrite_https(url):
    """Return the http:// form of a newxk.urp.seu.edu.cn https URL."""
    if url.startswith("https://" + HOST):
        return "http://" + url[len("https://"):]
    return url


def _current_url(self):
    global _https_notice_shown
    url = _real_current_url.fget(self)
    rewritten = _rewrite_https(url)
    if rewritten != url and not _https_notice_shown:
        _https_notice_shown = True
        log("note: site redirects to https; reporting the http form to the legacy script")
    return rewritten


WebDriver.current_url = property(_current_url)


# --- 5. run the original script ----------------------------------------

class _Tee(object):
    """Copy of stdout that also keeps the text, so we can inspect it."""

    def __init__(self, stream):
        self._stream = stream
        self._chunks = []

    def write(self, data):
        self._chunks.append(data)
        self._stream.write(data)
        self._stream.flush()
        return len(data)

    def flush(self):
        self._stream.flush()

    def text(self):
        return "".join(self._chunks)


def main():
    missing = [name for name in ("NAME", "PASSWORD", "CLASS") if not os.environ.get(name)]
    if missing:
        log("missing environment variable(s): " + ", ".join(missing)
            + " - check the repository secrets")
        return 2

    if not os.path.exists(TARGET):
        log("the course-helper script was not found in the repository root")
        return 2

    log("class setting: %r" % os.environ.get("CLASS", ""))
    log("turn setting: %r" % os.environ.get("TURN", ""))
    log("compatibility layer active, starting the course-helper script")

    tee = _Tee(sys.__stdout__)
    original_stdout = sys.stdout
    sys.stdout = tee
    try:
        runpy.run_path(TARGET, run_name="__main__")
    finally:
        sys.stdout = original_stdout

    text = tee.text()
    url = ""
    title = ""
    if _last_driver is not None:
        try:
            url = _real_current_url.fget(_last_driver)
        except Exception as exc:
            url = "<unavailable: %r>" % (exc,)
        try:
            title = _last_driver.title
        except Exception:
            title = ""
        if url.startswith("http"):
            log("last page: " + url)
        if title:
            log("last page title: " + title)

    if "login successfully" in text:
        log("result: the login stage passed, the script is now hunting for the course")
        return 0
    if "/xsxk/elective/" in url:
        log("result: the login itself worked, but the script did not get past the "
            "round selection - that is what happens while the round is not open yet")
        return 1
    log("result: the login stage did not succeed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
