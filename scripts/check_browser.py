"""Developer smoke test using real local Piper and mocked ChatGPT responses."""
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def main():
    root = Path(__file__).resolve().parents[1]
    output = root.parent / "outputs"
    output.mkdir(exist_ok=True)
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
        "--port", "8000", "--no-access-log"], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            if server.poll() is not None:
                raise RuntimeError("Test server failed to start. Port 8000 must be free.")
            try:
                urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
                break
            except Exception:
                time.sleep(.25)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True,
                args=["--enable-webgl", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1440, "height": 1100})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://127.0.0.1:8000")
            expect(page.locator("#connection")).to_contain_text("anmelden")
            assert page.locator("#send").is_disabled()
            assert page.locator("#test-answer").is_disabled()
            page.locator("#test-voice").click()
            expect(page.locator("body")).to_have_attribute("data-state", "speaking", timeout=20000)
            expect(page.locator("body")).to_have_attribute("data-state", "idle", timeout=30000)
            assert page.locator("#error").is_hidden()
            page.route("**/health", lambda r: r.fulfill(json=dict(configured=True, voice_configured=True,
                active="test", accounts=[dict(id="test", label="Simuliertes Testkonto")], tested_models=[])))
            page.route("**/api/models", lambda r: r.fulfill(json={"models": [dict(slug="gpt-6.1-sol", display_name="GPT-6.1 Sol (Test)")]}))
            page.route("**/api/test", lambda r: r.fulfill(json=dict(reply="Jarvis ist online.", model="gpt-6.1-sol")))
            page.route("**/api/chat", lambda r: r.fulfill(json=dict(reply="Das ist eine simulierte Testantwort.", sources=[])))
            page.reload()
            expect(page.locator("#model")).to_have_value("gpt-6.1-sol")
            assert page.locator("#send").is_disabled()
            page.locator("#speak").uncheck()
            page.locator("#test-answer").click()
            expect(page.locator("#send")).to_be_enabled()
            page.locator("#input").fill("Hallo Jarvis")
            page.locator("#send").click()
            expect(page.locator("#result-text")).to_contain_text("simulierte")
            page.screenshot(path=str(output / "jarvis2-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(output / "jarvis2-mobile.png"), full_page=True)
            page.locator("#reset").click()
            assert page.locator(".message.user").count() == 0
            assert not errors, errors
            browser.close()
        print("PASS: local WAV playback, login gate, model picker, test gate, chat, reset, mobile layout, no JS errors")
    finally:
        server.terminate()
        server.wait(timeout=15)


if __name__ == "__main__":
    main()
