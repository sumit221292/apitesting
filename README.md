# ZeepLive API Test Automation Lab

Advanced API testing tool with Web UI for ZeepLive backend APIs.

## Features

- **Manual API Testing** - Postman-like interface, send requests, view responses
- **Auto Test Suite** - Select APIs, run batch tests, pass/fail dashboard
- **Load Testing** - Virtual users, ramp/spike/stress patterns, real-time charts
- **Error Detection** - Auto-detect missing fields, popup to fill & retry
- **Collection Management** - Add/Edit/Delete APIs, Import/Export Postman collections
- **Security** - Login required, credentials in `.env` file (not in code), session management

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run the app (first run will ask to create login credentials)
python zeeplive_test_ui.py

# Open in browser
# http://localhost:5555
```

## Login

First run creates `.env.zeeplive` file with your credentials.
- Default: `admin` / `admin@123` (change after first login)
- Change password from UI: Sidebar > PW button

## Files

| File | Description |
|------|-------------|
| `zeeplive_test_ui.py` | Main app - Web UI with all features |
| `zeeplive_api.py` | CLI version (terminal-based API runner) |
| `test_*.py` | Playwright automated tests |
| `.env.zeeplive` | Credentials (auto-created, NOT committed to git) |

## Playwright Tests

```bash
# Run all tests (headed - visible browser)
python test_auth.py          # Login/security tests
python test_zeeplive_ui.py   # Full UI test (88 checks)
python test_filter.py        # Filter & optimization tests
python test_load.py          # Load testing tests
python test_manage.py        # Add/Delete/Collection tests
```
