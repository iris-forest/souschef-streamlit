from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.request import urlopen

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


STREAMLIT_URL = "http://127.0.0.1:8501"


def _wait_for_server(url: str, timeout: float = 20.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Streamlit server did not start within {timeout}s")


@contextmanager
def _run_streamlit() -> None:
    env = os.environ.copy()
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/main.py",
        "--server.headless=true",
        "--server.port=8501",
    ]
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_server(STREAMLIT_URL)
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.skipif(
    os.getenv("STREAMLIT_E2E") != "1",
    reason="Set STREAMLIT_E2E=1 to run Selenium tests.",
)
def test_streamlit_homepage_renders() -> None:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,800")

    with _run_streamlit():
        driver = webdriver.Chrome(options=options)
        try:
            driver.get(STREAMLIT_URL)
            wait = WebDriverWait(driver, 20)
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.TAG_NAME, "body"),
                    "SousChef Recipe Transformer",
                )
            )
            body_text = driver.find_element(By.TAG_NAME, "body").text
            assert "SousChef Recipe Transformer" in body_text
            assert "Transform recipe text" in body_text
        finally:
            driver.quit()
