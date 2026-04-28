# 🗳️ EzeeVote Selenium Website Tester

An automated Selenium testing project for checking the quality, stability, accessibility, and responsiveness of the **EzeeVote** website.

After every test run, it generates a clean and visual HTML report so results are easy to understand.

---

## 🌐 Default Website

```text
https://online-voting-system-henna.vercel.app/
```

You can also test any other website by passing a custom URL.

---

## ✅ What This Project Tests

The test suite checks many important parts of a website:

| Category | What It Checks |
|---|---|
| 🚀 Smoke Test | Page loads correctly with a valid title and URL |
| 🧾 Content | Visible text appears after the JavaScript app finishes loading |
| 🧠 Console | No serious browser console errors |
| 🔎 SEO | Title, description, language, and viewport tags |
| ♿ Accessibility | Landmarks, headings, labels, and keyboard focus |
| 🔗 Links | Broken links and invalid navigation |
| 🖼️ Media | Images load properly and have alt text |
| 📝 Forms | Inputs are labeled and text fields can be typed into |
| 📱 Responsive UI | Desktop, tablet, and mobile layout checks |
| ⚡ Performance | Basic page load speed budget |
| 🔐 Security | HTTPS and healthy HTTP response |
| 📦 Assets | CSS, JS, images, and other resources load correctly |

---

## 🛠️ Requirements

Make sure these are installed:

- Python 3.10+
- Google Chrome
- Selenium

Install Selenium:

```powershell
pip install selenium
```

Selenium Manager usually downloads and manages ChromeDriver automatically.

---

## ▶️ How To Run

Run tests on the default website:

```powershell
python ezeevote.py
```

Run tests on another website:

```powershell
python ezeevote.py --url "https://your-site-url.com"
```

Run with Chrome visible:

```powershell
$env:HEADLESS="0"
python ezeevote.py
```

Run again in headless mode:

```powershell
$env:HEADLESS="1"
python ezeevote.py
```

---

## 📊 Selenium HTML Reports

Every run creates a new report inside:

```text
test_reports/
```

Report filenames include the date and time:

```text
selenium_report_YYYYMMDD_HHMMSS.html
```

Example:

```text
selenium_report_20260428_161235.html
```

✅ **The latest timestamp is the real/current report.**

---

## 🎨 Report Features

The report UI includes:

- 📈 Pass-rate circle
- 🧮 Total, pass, fail, error, and skipped cards
- 🗂️ Category-wise result cards
- 🔍 Result filter buttons
- ⏱️ Test duration
- 🧾 Clean failure summary
- 📜 Expandable full traceback
- 📸 Screenshot for failed tests
- 📱 Responsive report layout

---

## ⚠️ Current Known Issues Found

The current website may fail some accessibility checks.

Examples:

- Missing semantic landmarks like `main`, `nav`, `header`, or `footer`
- Some visible inputs do not have accessible names or labels

These are real frontend issues detected by Selenium. To make those tests pass, the website code needs accessibility improvements.

---

## ⚙️ Useful Environment Variables

You can customize the test run:

```powershell
$env:TEST_URL="https://your-site-url.com"
$env:HEADLESS="0"
$env:PAGE_READY_TIMEOUT="20"
$env:MAX_LINKS_TO_CHECK="60"
$env:MAX_NAV_LINKS_TO_CLICK="20"
$env:SLOW_PAGE_SECONDS="10"
python ezeevote.py
```

| Variable | Purpose |
|---|---|
| `TEST_URL` | Default URL if `--url` is not passed |
| `HEADLESS` | Use `1` for hidden browser, `0` for visible browser |
| `PAGE_READY_TIMEOUT` | Seconds to wait for app content |
| `MAX_LINKS_TO_CHECK` | Maximum links checked for broken URLs |
| `MAX_NAV_LINKS_TO_CLICK` | Maximum internal links opened in browser |
| `SLOW_PAGE_SECONDS` | Performance budget in seconds |

---

## 📁 Project Structure

```text
Tapas CODES/
├── ezeevote.py
├── README.md
├── .gitignore
└── test_reports/
    └── selenium_report_*.html
```

### File Details

| File/Folder | Description |
|---|---|
| `ezeevote.py` | Main Selenium test runner and HTML report generator |
| `test_reports/` | Generated Selenium HTML reports |
| `.gitignore` | Ignores generated, cache, env, and local files |
| `README.md` | Project documentation |

---

## 🧪 Test Result Meaning

| Status | Meaning |
|---|---|
| ✅ PASS | Test completed successfully |
| ❌ FAIL | Website behavior did not meet the expected condition |
| 🛑 ERROR | Test crashed because of an unexpected issue |
| ⏭️ SKIPPED | Test was skipped intentionally |

---

## 🚀 Quick Start

```powershell
pip install selenium
python ezeevote.py
```

Then open the newest file inside:

```text
test_reports/
```

That is your latest Selenium report.
