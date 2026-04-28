import argparse
import json
import html
import os
import time
import traceback
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


REPORT_DIR = Path(__file__).parent / "test_reports"
DEFAULT_URL = os.getenv("TEST_URL", "https://online-voting-system-henna.vercel.app/")
PAGE_READY_TIMEOUT = int(os.getenv("PAGE_READY_TIMEOUT", "15"))
MAX_LINKS_TO_CHECK = int(os.getenv("MAX_LINKS_TO_CHECK", "40"))
MAX_NAV_LINKS_TO_CLICK = int(os.getenv("MAX_NAV_LINKS_TO_CLICK", "12"))
SLOW_PAGE_SECONDS = float(os.getenv("SLOW_PAGE_SECONDS", "8"))


@dataclass
class TestResultItem:
    name: str
    status: str
    duration: float
    error: str = ""
    category: str = "General"
    screenshot: str = ""


class ReportResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.report_items = []
        self._started_at = {}

    def startTest(self, test):
        self._started_at[test] = time.perf_counter()
        super().startTest(test)

    def addSuccess(self, test):
        self._add_report_item(test, "PASS")
        super().addSuccess(test)

    def addFailure(self, test, err):
        self._add_report_item(test, "FAIL", self._format_error(err))
        super().addFailure(test, err)

    def addError(self, test, err):
        self._add_report_item(test, "ERROR", self._format_error(err))
        super().addError(test, err)

    def addSkip(self, test, reason):
        self._add_report_item(test, "SKIPPED", reason)
        super().addSkip(test, reason)

    def _add_report_item(self, test, status, error=""):
        started_at = self._started_at.pop(test, time.perf_counter())
        screenshot = ""
        if status in {"FAIL", "ERROR"}:
            screenshot = self._capture_screenshot(test)
        self.report_items.append(
            TestResultItem(
                name=self.getDescription(test),
                status=status,
                duration=time.perf_counter() - started_at,
                error=error,
                category=getattr(test, "category", self._category_from_test(test)),
                screenshot=screenshot,
            )
        )

    @staticmethod
    def _format_error(err):
        return "".join(traceback.format_exception(*err))

    @staticmethod
    def _category_from_test(test):
        method_name = getattr(test, "_testMethodName", "")
        return method_name.split("_")[1].title() if "_" in method_name else "General"

    @staticmethod
    def _capture_screenshot(test):
        driver = getattr(test, "driver", None)
        if not driver:
            return ""
        try:
            return driver.get_screenshot_as_base64()
        except WebDriverException:
            return ""


class ReportRunner(unittest.TextTestRunner):
    resultclass = ReportResult


class SeleniumBaseTest(unittest.TestCase):
    driver = None
    base_url = DEFAULT_URL

    @classmethod
    def setUpClass(cls):
        chrome_options = Options()
        if os.getenv("HEADLESS", "1") != "0":
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-size=1366,768")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.set_capability("goog:loggingPrefs", {"browser": "ALL"})

        try:
            cls.driver = webdriver.Chrome(options=chrome_options)
            cls.driver.implicitly_wait(2)
            cls.wait = WebDriverWait(cls.driver, PAGE_READY_TIMEOUT)
        except WebDriverException as exc:
            raise RuntimeError(
                "Could not start Chrome WebDriver. Install Google Chrome and "
                "Selenium, then make sure ChromeDriver is available."
            ) from exc

    @classmethod
    def tearDownClass(cls):
        if cls.driver:
            cls.driver.quit()

    def open_home_page(self):
        self.driver.get(self.base_url)
        self.wait_for_document_ready()

    def wait_for_document_ready(self):
        self.wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")

    def wait_for_visible_body_text(self):
        ignored_loader_text = {"checking session", "loading", "please wait"}
        end_time = time.time() + PAGE_READY_TIMEOUT
        last_text = ""
        while time.time() < end_time:
            body = self.driver.find_element(By.TAG_NAME, "body")
            last_text = body.text.strip()
            normalized = " ".join(last_text.lower().split())
            if last_text and normalized not in ignored_loader_text:
                return last_text
            time.sleep(0.35)
        self.fail(f"Page body did not show usable content within {PAGE_READY_TIMEOUT}s. Last text: {last_text!r}")

    def get_browser_console_errors(self):
        try:
            logs = self.driver.get_log("browser")
        except (ValueError, WebDriverException):
            return []

        ignored_fragments = (
            "favicon.ico",
            "manifest.json",
            "third-party cookie",
            "downloadable font",
        )
        errors = []
        for entry in logs:
            message = entry.get("message", "")
            level = entry.get("level", "")
            if level not in {"SEVERE", "ERROR"}:
                continue
            if any(fragment.lower() in message.lower() for fragment in ignored_fragments):
                continue
            errors.append(f"{level}: {message}")
        return errors

    def collect_links(self):
        links = []
        for element in self.driver.find_elements(By.CSS_SELECTOR, "a[href]"):
            href = element.get_attribute("href")
            if href and not href.startswith(("javascript:", "mailto:", "tel:")):
                links.append(href)
        return sorted(set(links))

    def absolute_url(self, value):
        return urljoin(self.base_url, value)


class WebsiteQualityTests(SeleniumBaseTest):
    def test_load_home_page_successfully(self):
        """Smoke: home page opens with a valid title and URL."""
        self.category = "Smoke"
        self.open_home_page()
        self.assertTrue(self.driver.title.strip(), "Page title should not be empty")
        self.assertTrue(
            self.driver.current_url.startswith("http"),
            f"Browser should stay on a valid web URL, got: {self.driver.current_url}",
        )

    def test_content_visible_after_app_load(self):
        """Content: page shows usable visible text after JavaScript finishes."""
        self.category = "Content"
        self.open_home_page()
        body_text = self.wait_for_visible_body_text()
        self.assertGreaterEqual(len(body_text), 20, "Visible page content is too small to be useful")

    def test_no_uncaught_console_errors(self):
        """Stability: browser console has no severe JavaScript errors."""
        self.category = "Stability"
        self.open_home_page()
        self.wait_for_visible_body_text()
        errors = self.get_browser_console_errors()
        self.assertFalse(errors, "Console errors found:\n" + "\n".join(errors[:10]))

    def test_metadata_and_seo_basics(self):
        """SEO: title, description, language, and viewport metadata exist."""
        self.category = "SEO"
        self.open_home_page()
        title = self.driver.title.strip()
        lang = self.driver.find_element(By.TAG_NAME, "html").get_attribute("lang")
        viewport = self.driver.find_elements(By.CSS_SELECTOR, "meta[name='viewport']")
        descriptions = self.driver.find_elements(By.CSS_SELECTOR, "meta[name='description']")

        self.assertGreaterEqual(len(title), 3, "Title should be descriptive")
        self.assertTrue(lang, "HTML lang attribute is required")
        self.assertTrue(viewport, "Viewport meta tag is required for responsive layout")
        self.assertTrue(
            descriptions and descriptions[0].get_attribute("content").strip(),
            "Meta description should not be empty",
        )

    def test_accessibility_landmarks_and_headings(self):
        """Accessibility: page has landmarks/headings for screen-reader structure."""
        self.category = "Accessibility"
        self.open_home_page()
        self.wait_for_visible_body_text()
        landmarks = self.driver.find_elements(By.CSS_SELECTOR, "main, [role='main'], nav, header, footer")
        headings = self.driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, h6")

        self.assertTrue(landmarks, "Add at least one semantic landmark such as main, nav, header, or footer")
        self.assertTrue(headings, "Add visible headings so users can understand page structure")

    def test_accessibility_interactive_controls_are_named(self):
        """Accessibility: buttons, links, and form controls have accessible names."""
        self.category = "Accessibility"
        self.open_home_page()
        self.wait_for_visible_body_text()
        selectors = "button, a[href], input:not([type='hidden']), select, textarea, [role='button']"
        unnamed = []
        for index, element in enumerate(self.driver.find_elements(By.CSS_SELECTOR, selectors), start=1):
            try:
                label = (
                    element.text
                    or element.get_attribute("aria-label")
                    or element.get_attribute("title")
                    or element.get_attribute("placeholder")
                    or element.get_attribute("name")
                    or element.get_attribute("value")
                )
                if element.is_displayed() and not str(label or "").strip():
                    unnamed.append(f"{element.tag_name} #{index}")
            except StaleElementReferenceException:
                continue
        self.assertFalse(unnamed, "Visible interactive controls need labels: " + ", ".join(unnamed[:20]))

    def test_links_are_not_broken(self):
        """Links: visible page links return successful HTTP responses."""
        self.category = "Links"
        self.open_home_page()
        self.wait_for_visible_body_text()
        links = self.collect_links()[:MAX_LINKS_TO_CHECK]
        broken = []

        for href in links:
            parsed = urlparse(href)
            if parsed.scheme not in {"http", "https"}:
                continue
            try:
                request = Request(href, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(request, timeout=10) as response:
                    status = response.getcode()
            except HTTPError as exc:
                status = exc.code
            except URLError as exc:
                broken.append(f"{href} -> {exc.reason}")
                continue
            except Exception as exc:
                broken.append(f"{href} -> {exc}")
                continue

            if status >= 400:
                broken.append(f"{href} -> HTTP {status}")

        self.assertFalse(broken, "Broken links found:\n" + "\n".join(broken))

    def test_internal_navigation_links_open_valid_pages(self):
        """Navigation: internal links can be clicked without browser error pages."""
        self.category = "Navigation"
        self.open_home_page()
        self.wait_for_visible_body_text()
        base_host = urlparse(self.base_url).netloc
        internal_links = [href for href in self.collect_links() if urlparse(href).netloc == base_host]
        failures = []

        for href in internal_links[:MAX_NAV_LINKS_TO_CLICK]:
            try:
                self.driver.get(href)
                self.wait_for_document_ready()
                self.assertNotIn("chrome-error://", self.driver.current_url)
                self.assertFalse(
                    self.driver.find_elements(By.CSS_SELECTOR, "h1.next-error-h1"),
                    f"Next.js error page displayed for {href}",
                )
            except Exception as exc:
                failures.append(f"{href} -> {exc}")

        self.assertFalse(failures, "Internal navigation failures:\n" + "\n".join(failures))

    def test_images_load_and_have_alt_text(self):
        """Media: visible images load correctly and have alt text."""
        self.category = "Media"
        self.open_home_page()
        self.wait_for_visible_body_text()
        failures = []
        for index, image in enumerate(self.driver.find_elements(By.CSS_SELECTOR, "img"), start=1):
            if not image.is_displayed():
                continue
            loaded = self.driver.execute_script(
                "return arguments[0].complete && arguments[0].naturalWidth > 0",
                image,
            )
            if not loaded:
                failures.append(f"Image #{index} did not load: {image.get_attribute('src')}")
            if image.get_attribute("alt") is None:
                failures.append(f"Image #{index} is missing alt text: {image.get_attribute('src')}")

        self.assertFalse(failures, "Image issues found:\n" + "\n".join(failures))

    def test_forms_are_labeled_and_typeable(self):
        """Forms: inputs are labeled and text fields accept typing."""
        self.category = "Forms"
        self.open_home_page()
        self.wait_for_visible_body_text()
        fields = self.driver.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']), textarea, select")
        failures = []

        for index, field in enumerate(fields, start=1):
            if not field.is_displayed():
                continue
            field_id = field.get_attribute("id")
            label = (
                field.get_attribute("aria-label")
                or field.get_attribute("placeholder")
                or field.get_attribute("name")
                or (self.driver.find_elements(By.CSS_SELECTOR, f"label[for='{field_id}']") if field_id else "")
            )
            if not label:
                failures.append(f"{field.tag_name} #{index} needs a label, placeholder, name, or aria-label")

            field_type = (field.get_attribute("type") or "").lower()
            if field.tag_name in {"input", "textarea"} and field_type in {"", "text", "email", "password", "search", "tel", "url"}:
                try:
                    if field.is_enabled():
                        field.clear()
                        field.send_keys("test")
                        self.assertIn("test", field.get_attribute("value"))
                        field.send_keys(Keys.CONTROL, "a")
                        field.send_keys(Keys.BACKSPACE)
                except Exception as exc:
                    failures.append(f"{field.tag_name} #{index} could not accept typing: {exc}")

        self.assertFalse(failures, "Form issues found:\n" + "\n".join(failures))

    def test_responsive_layout_desktop_tablet_mobile(self):
        """Responsive: layout works on desktop, tablet, and mobile widths."""
        self.category = "Visual"
        failures = []
        viewports = [(1366, 768, "desktop"), (820, 1180, "tablet"), (390, 844, "mobile")]

        for width, height, label in viewports:
            self.driver.set_window_size(width, height)
            self.open_home_page()
            self.wait_for_visible_body_text()
            metrics = self.driver.execute_script(
                """
                return {
                    scrollWidth: document.documentElement.scrollWidth,
                    clientWidth: document.documentElement.clientWidth,
                    bodyText: document.body.innerText.trim().length
                };
                """
            )
            if metrics["scrollWidth"] > metrics["clientWidth"] + 4:
                failures.append(
                    f"{label}: horizontal overflow {metrics['scrollWidth']}px > {metrics['clientWidth']}px"
                )
            if metrics["bodyText"] < 20:
                failures.append(f"{label}: page content looks empty")

        self.assertFalse(failures, "Responsive layout issues:\n" + "\n".join(failures))

    def test_keyboard_tab_focus_is_visible(self):
        """Keyboard: tabbing reaches a visible focused element."""
        self.category = "Accessibility"
        self.open_home_page()
        self.wait_for_visible_body_text()
        body = self.driver.find_element(By.TAG_NAME, "body")
        reached_focus = False
        for _ in range(12):
            body.send_keys(Keys.TAB)
            active = self.driver.switch_to.active_element
            if active and active.tag_name.lower() != "body" and active.is_displayed():
                reached_focus = True
                break
        self.assertTrue(reached_focus, "Keyboard Tab should move focus to a visible interactive element")

    def test_static_assets_loaded_without_http_errors(self):
        """Assets: scripts, styles, images, and fetches do not return HTTP errors."""
        self.category = "Performance"
        self.open_home_page()
        self.wait_for_visible_body_text()
        entries = self.driver.execute_script(
            """
            return performance.getEntriesByType('resource').map((entry) => ({
                name: entry.name,
                type: entry.initiatorType,
                duration: entry.duration,
                transferSize: entry.transferSize
            }));
            """
        )
        failed_assets = []
        for entry in entries:
            name = entry["name"]
            if not name.startswith(("http://", "https://")):
                continue
            try:
                request = Request(name, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(request, timeout=10) as response:
                    status = response.getcode()
            except HTTPError as exc:
                status = exc.code
            except Exception:
                continue
            if status >= 400:
                failed_assets.append(f"{entry['type']}: {name} -> HTTP {status}")

        self.assertFalse(failed_assets, "Failed assets:\n" + "\n".join(failed_assets[:20]))

    def test_basic_performance_budget(self):
        """Performance: page completes browser load within the configured budget."""
        self.category = "Performance"
        self.open_home_page()
        timing = self.driver.execute_script(
            """
            const nav = performance.getEntriesByType('navigation')[0];
            return nav ? nav.loadEventEnd / 1000 : 0;
            """
        )
        self.assertLess(
            timing,
            SLOW_PAGE_SECONDS,
            f"Page load took {timing:.2f}s, budget is {SLOW_PAGE_SECONDS:.2f}s",
        )

    def test_https_and_security_basics(self):
        """Security: production URL uses HTTPS and returns a healthy status."""
        self.category = "Security"
        parsed = urlparse(self.base_url)
        if parsed.hostname in {"localhost", "127.0.0.1"}:
            self.skipTest("HTTPS check skipped for local development URL")
        self.assertEqual(parsed.scheme, "https", "Production test URL should use HTTPS")
        request = Request(self.base_url, method="GET", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=15) as response:
            status = response.getcode()
        self.assertLess(status, 400, f"Home page returned HTTP {status}")


def summarize_error(error_text):
    if not error_text:
        return ""

    lines = [line.strip() for line in error_text.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith(("AssertionError:", "RuntimeError:", "TimeoutException:", "WebDriverException:")):
            return line
    if lines:
        return lines[-1]
    return "Test failed. Open the traceback for details."


def build_html_report(result, test_url, started_at, finished_at):
    total = result.testsRun
    passed = len([item for item in result.report_items if item.status == "PASS"])
    failed = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    duration = (finished_at - started_at).total_seconds()
    pass_rate = round((passed / total) * 100) if total else 0
    status_counts = {
        "PASS": passed,
        "FAIL": failed,
        "ERROR": errors,
        "SKIPPED": skipped,
    }
    categories = sorted({item.category for item in result.report_items})
    category_stats = []
    for category in categories:
        items = [item for item in result.report_items if item.category == category]
        category_passed = len([item for item in items if item.status == "PASS"])
        category_stats.append((category, category_passed, len(items)))

    rows = []
    for item in result.report_items:
        css_class = item.status.lower()
        error_summary = summarize_error(item.error)
        details = (
            f"""
            <div class="issue-summary">{html.escape(error_summary)}</div>
            <details>
                <summary>Full traceback</summary>
                <pre>{html.escape(item.error)}</pre>
            </details>
            """
            if item.error
            else """<div class="ok-detail">No issues found.</div>"""
        )
        screenshot = (
            f"""<button class="screenshot-toggle" type="button" onclick="toggleScreenshot(this)">View screenshot</button>
                <img class="screenshot" alt="Failure screenshot" src="data:image/png;base64,{item.screenshot}">"""
            if item.screenshot
            else ""
        )
        rows.append(
            f"""
            <tr class="{css_class}" data-status="{item.status}" data-category="{html.escape(item.category)}">
                <td>
                    <div class="test-name">{html.escape(item.name)}</div>
                    <div class="category-pill">{html.escape(item.category)}</div>
                </td>
                <td><span class="status">{item.status}</span></td>
                <td><strong>{item.duration:.2f}s</strong></td>
                <td><pre>{details}</pre>{screenshot}</td>
            </tr>
            """
        )

    filter_buttons = "".join(
        f'<button type="button" data-filter="{status}" onclick="filterStatus(\'{status}\')">{status.title()} <strong>{count}</strong></button>'
        for status, count in status_counts.items()
    )
    category_cards = "".join(
        f"""
        <article>
            <span>{html.escape(category)}</span>
            <strong>{category_passed}/{category_total}</strong>
            <div class="bar"><i style="width:{round((category_passed / category_total) * 100) if category_total else 0}%"></i></div>
        </article>
        """
        for category, category_passed, category_total in category_stats
    )
    report_json = json.dumps(
        {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "passRate": pass_rate,
            "duration": duration,
        }
    ).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Selenium Test Report</title>
    <style>
        :root {{
            color-scheme: light;
            --bg: #f6f8fb;
            --panel: #ffffff;
            --ink: #182230;
            --muted: #667085;
            --line: #d9e2ec;
            --pass: #11845b;
            --fail: #c2410c;
            --error: #b42318;
            --skip: #667085;
            --blue: #2563eb;
            --violet: #7c3aed;
        }}
        body {{
            margin: 0;
            color: var(--ink);
            background:
                radial-gradient(circle at 10% 0%, rgba(37, 99, 235, .10), transparent 30%),
                linear-gradient(180deg, #ffffff 0, var(--bg) 360px);
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        main {{
            width: min(1220px, calc(100% - 32px));
            margin: 28px auto 42px;
        }}
        header {{
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 24px;
            align-items: center;
            margin-bottom: 24px;
        }}
        h1 {{
            margin: 0 0 8px;
            font-size: clamp(28px, 4vw, 48px);
            line-height: 1;
            letter-spacing: 0;
        }}
        .subtitle {{
            margin: 0;
            color: var(--muted);
            font-size: 15px;
            line-height: 1.6;
        }}
        .hero-score {{
            width: 158px;
            height: 158px;
            border-radius: 50%;
            display: grid;
            place-items: center;
            background: conic-gradient(var(--pass) {pass_rate}%, #e6edf5 0);
            box-shadow: 0 18px 45px rgba(16, 24, 40, .13);
        }}
        .hero-score div {{
            width: 118px;
            height: 118px;
            border-radius: 50%;
            display: grid;
            place-items: center;
            background: var(--panel);
            text-align: center;
        }}
        .hero-score strong {{
            display: block;
            font-size: 34px;
        }}
        .hero-score span {{
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .08em;
        }}
        .meta-grid, .summary, .category-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 12px;
            margin-bottom: 18px;
        }}
        .meta-grid div, .summary div, .category-grid article {{
            background: rgba(255, 255, 255, .88);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 12px 28px rgba(16, 24, 40, .06);
        }}
        .label, .meta-grid span, .category-grid span {{
            color: var(--muted);
            display: block;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: .08em;
            text-transform: uppercase;
        }}
        .meta-grid strong {{
            display: block;
            margin-top: 8px;
            overflow-wrap: anywhere;
        }}
        .summary strong, .category-grid strong {{
            display: block;
            font-size: 28px;
            margin-top: 6px;
        }}
        .pass-card strong {{ color: var(--pass); }}
        .fail-card strong {{ color: var(--fail); }}
        .error-card strong {{ color: var(--error); }}
        .filters {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 24px 0 12px;
        }}
        .filters button, .screenshot-toggle {{
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--panel);
            color: var(--ink);
            cursor: pointer;
            font: inherit;
            font-size: 13px;
            font-weight: 700;
            padding: 9px 12px;
        }}
        .filters button:hover, .screenshot-toggle:hover {{
            border-color: var(--blue);
        }}
        .report-panel {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 18px 45px rgba(16, 24, 40, .08);
        }}
        table {{
            width: 100%;
            table-layout: fixed;
            border-collapse: collapse;
        }}
        col.test-col {{ width: 48%; }}
        col.status-col {{ width: 10%; }}
        col.time-col {{ width: 8%; }}
        col.details-col {{ width: 34%; }}
        th, td {{
            padding: 14px;
            text-align: left;
            border-bottom: 1px solid #eef2f6;
            vertical-align: top;
        }}
        th {{
            background: #f8fafc;
            color: #475467;
            font-size: 12px;
            letter-spacing: .08em;
            text-transform: uppercase;
        }}
        tr:last-child td {{
            border-bottom: 0;
        }}
        .status {{
            display: inline-block;
            min-width: 72px;
            padding: 5px 9px;
            border-radius: 999px;
            color: #ffffff;
            text-align: center;
            font-weight: 700;
            font-size: 12px;
        }}
        .pass .status {{ background: var(--pass); }}
        .fail .status {{ background: var(--fail); }}
        .error .status {{ background: var(--error); }}
        .skipped .status {{ background: var(--skip); }}
        .test-name {{
            font-weight: 750;
            line-height: 1.35;
            overflow-wrap: anywhere;
        }}
        .category-pill {{
            display: inline-block;
            margin-top: 8px;
            padding: 4px 8px;
            border-radius: 999px;
            background: #eef4ff;
            color: #1849a9;
            font-size: 12px;
            font-weight: 700;
        }}
        pre {{
            max-width: 100%;
            max-height: 260px;
            overflow: auto;
            white-space: pre-wrap;
            word-break: normal;
            overflow-wrap: anywhere;
            margin: 0;
            font-size: 12px;
            line-height: 1.55;
            color: #344054;
            background: #f8fafc;
            border: 1px solid #e4e7ec;
            border-radius: 8px;
            padding: 12px;
        }}
        .issue-summary {{
            border-left: 4px solid var(--fail);
            background: #fff7ed;
            color: #7c2d12;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 700;
            line-height: 1.45;
            margin-bottom: 10px;
            padding: 10px 12px;
            overflow-wrap: anywhere;
        }}
        .ok-detail {{
            color: var(--muted);
            font-size: 13px;
        }}
        details summary {{
            cursor: pointer;
            color: var(--blue);
            font-size: 13px;
            font-weight: 800;
            margin-bottom: 8px;
        }}
        details:not([open]) summary {{
            margin-bottom: 0;
        }}
        .bar {{
            height: 8px;
            margin-top: 12px;
            border-radius: 999px;
            background: #e6edf5;
            overflow: hidden;
        }}
        .bar i {{
            display: block;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, var(--pass), var(--blue));
        }}
        .screenshot-toggle {{
            margin-top: 12px;
        }}
        .screenshot {{
            display: none;
            width: min(620px, 100%);
            margin-top: 12px;
            border: 1px solid var(--line);
            border-radius: 8px;
        }}
        .screenshot.is-visible {{
            display: block;
        }}
        @media (max-width: 760px) {{
            header {{
                grid-template-columns: 1fr;
            }}
            .hero-score {{
                width: 132px;
                height: 132px;
            }}
            table, thead, tbody, tr, th, td {{
                display: block;
            }}
            colgroup {{
                display: none;
            }}
            thead {{
                display: none;
            }}
            tr {{
                border-bottom: 1px solid #eef2f6;
            }}
            td {{
                border-bottom: 0;
                padding: 10px 14px;
            }}
        }}
    </style>
</head>
<body>
    <main>
        <header>
            <div>
                <h1>Selenium Test Report</h1>
                <p class="subtitle">Full website quality check covering smoke, content, navigation, links, forms, accessibility, visual responsiveness, performance, assets, and security basics.</p>
            </div>
            <div class="hero-score"><div><strong>{pass_rate}%</strong><span>Pass rate</span></div></div>
        </header>
        <section class="meta-grid" aria-label="Run details">
            <div><span>URL</span><strong>{html.escape(test_url)}</strong></div>
            <div><span>Started</span><strong>{started_at.strftime("%Y-%m-%d %H:%M:%S")}</strong></div>
            <div><span>Finished</span><strong>{finished_at.strftime("%Y-%m-%d %H:%M:%S")}</strong></div>
            <div><span>Duration</span><strong>{duration:.2f}s</strong></div>
        </section>
        <section class="summary">
            <div><span class="label">Total</span><strong>{total}</strong></div>
            <div class="pass-card"><span class="label">Passed</span><strong>{passed}</strong></div>
            <div class="fail-card"><span class="label">Failed</span><strong>{failed}</strong></div>
            <div class="error-card"><span class="label">Errors</span><strong>{errors}</strong></div>
            <div><span class="label">Skipped</span><strong>{skipped}</strong></div>
        </section>
        <section class="category-grid" aria-label="Category results">
            {category_cards}
        </section>
        <nav class="filters" aria-label="Result filters">
            <button type="button" data-filter="ALL" onclick="filterStatus('ALL')">All <strong>{total}</strong></button>
            {filter_buttons}
        </nav>
        <section class="report-panel">
            <table>
                <colgroup>
                    <col class="test-col">
                    <col class="status-col">
                    <col class="time-col">
                    <col class="details-col">
                </colgroup>
                <thead>
                    <tr>
                        <th>Test</th>
                        <th>Status</th>
                        <th>Time</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </section>
    </main>
    <script type="application/json" id="report-data">{report_json}</script>
    <script>
        function filterStatus(status) {{
            document.querySelectorAll('tbody tr').forEach((row) => {{
                row.style.display = status === 'ALL' || row.dataset.status === status ? '' : 'none';
            }});
        }}
        function toggleScreenshot(button) {{
            const image = button.nextElementSibling;
            image.classList.toggle('is-visible');
            button.textContent = image.classList.contains('is-visible') ? 'Hide screenshot' : 'View screenshot';
        }}
    </script>
</body>
</html>
"""


def save_report(result, test_url, started_at, finished_at):
    REPORT_DIR.mkdir(exist_ok=True)
    report_name = f"selenium_report_{finished_at.strftime('%Y%m%d_%H%M%S')}.html"
    report_path = REPORT_DIR / report_name
    report_path.write_text(
        build_html_report(result, test_url, started_at, finished_at),
        encoding="utf-8",
    )
    return report_path


def parse_args():
    parser = argparse.ArgumentParser(description="Run Selenium tests and create an HTML report.")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Website URL to test. Default: TEST_URL env var or https://example.com",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    SeleniumBaseTest.base_url = args.url

    started_at = datetime.now()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WebsiteQualityTests)
    runner = ReportRunner(verbosity=2)
    result = runner.run(suite)
    finished_at = datetime.now()

    report_path = save_report(result, args.url, started_at, finished_at)
    print(f"\nHTML test report created: {report_path}")

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
