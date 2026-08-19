# UI Automation MVP (Playwright + Pytest)

Minimal UI automation framework with a local demo page as the test target.

## Structure
- `web/demo.html` — local static demo page (to-do list, checkbox, counter)
- `pages/demo_page.py` — Page Object for the demo page
- `tests/` — pytest tests using `pytest-playwright` fixtures

## Setup
```bash
cd /Users/shafelix/mywork2/UI_auto_1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run tests
```bash
pytest
```

Run headed (visible browser) to watch the interactions:
```bash
pytest --headed
```
