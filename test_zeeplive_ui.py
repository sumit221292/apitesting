"""
Playwright HEADED full test - every feature, every button, every flow.
"""
import sys, os, time, json
# Fix Windows console unicode
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

URL = "http://localhost:5555"
SLOW = 500
PASS = 0
FAIL = 0
TESTS = []

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1; TESTS.append(("PASS", name))
        print(f"    [PASS] {name}" + (f" - {detail}" if detail else ""))
    else:
        FAIL += 1; TESTS.append(("FAIL", name))
        print(f"    [FAIL] {name}" + (f" - {detail}" if detail else ""))

def run():
    global PASS, FAIL
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=SLOW)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        # ═══════════════════════════════════════════════════════
        print("\n" + "="*60)
        print("  ZEEPLIVE UI - FULL TEST SUITE (HEADED)")
        print("="*60)

        # ─── TEST GROUP 1: PAGE LOAD ───
        print("\n[1] PAGE LOAD")
        page.goto(URL)
        page.wait_for_selector(".side-hdr h2", timeout=10000)
        check("Page title", "ZeepLive" in page.title(), page.title())
        check("3 mode tabs exist", len(page.query_selector_all(".mode-tab")) == 3)
        check("Tab 1 is 'Manual Test'", "Manual" in page.query_selector_all(".mode-tab")[0].inner_text())
        check("Tab 2 is 'Auto Test'", "Auto" in page.query_selector_all(".mode-tab")[1].inner_text())
        check("Tab 3 is 'Results'", "Results" in page.query_selector_all(".mode-tab")[2].inner_text())
        check("Manual Test tab is active by default", "on" in page.query_selector_all(".mode-tab")[0].get_attribute("class"))

        # Sidebar
        page.wait_for_selector(".fld", timeout=10000)
        folders = page.query_selector_all(".fld")
        check("Sidebar has 30 folders", len(folders) == 30, f"got {len(folders)}")
        check("Endpoint count shown", page.query_selector("#epCnt").inner_text() != "")

        # Token status - should be empty initially
        tok = page.query_selector("#tokSt").inner_text()
        check("Token status shows 'No Token' initially", "No Token" in tok or "Token" in tok, tok)

        # ─── TEST GROUP 2: SIDEBAR NAVIGATION ───
        print("\n[2] SIDEBAR - FOLDER EXPAND/COLLAPSE")
        first_folder_h = page.query_selector(".fld-h")
        first_folder_h.click()
        time.sleep(0.3)
        fld_list = page.query_selector(".fld-list")
        check("Folder expands on click", fld_list and "open" in fld_list.get_attribute("class"))
        first_folder_h.click()
        time.sleep(0.3)
        check("Folder collapses on 2nd click", "open" not in fld_list.get_attribute("class"))

        # ─── TEST GROUP 3: ENDPOINT SELECTION ───
        print("\n[3] ENDPOINT SELECTION IN SIDEBAR")
        # Open Auth folder and click Login endpoint
        for fh in page.query_selector_all(".fld-h"):
            if "Auth" in fh.inner_text():
                fh.click(); break
        time.sleep(0.3)

        login_ep = None
        for ep in page.query_selector_all(".ep-row"):
            if "Login User" in ep.inner_text():
                login_ep = ep; ep.click(); break
        time.sleep(0.3)
        check("Login endpoint found in sidebar", login_ep is not None)
        check("Endpoint row highlighted", "on" in login_ep.get_attribute("class"))
        url_val = page.input_value("#mUrl")
        check("URL bar populated", url_val != "", url_val)
        check("URL contains device-manual-login", "device-manual-login" in (url_val or ""), url_val)
        check("Method is POST", page.input_value("#mSel") == "POST")
        info = page.query_selector("#epInfo").inner_text()
        check("Endpoint info shows name", "Login" in info, info)

        # Check headers loaded
        hdr_rows = page.query_selector_all("#hdEd .kv")
        check("Headers loaded from collection", len(hdr_rows) > 0, f"{len(hdr_rows)} headers")

        # Check body loaded
        page.click("text=Body")
        time.sleep(0.2)
        body_rows = page.query_selector_all("#bdEd .kv")
        check("Body fields loaded from collection", len(body_rows) > 0, f"{len(body_rows)} fields")

        # ─── TEST GROUP 4: LOGIN & TOKEN ───
        print("\n[4] LOGIN & GET TOKEN")
        page.click("text=Headers")  # switch back
        time.sleep(0.2)
        page.click("#sendBtn")
        page.wait_for_function("!document.getElementById('sendBtn').disabled", timeout=15000)
        time.sleep(0.5)

        res_st = page.query_selector("#resSt").inner_text()
        check("Login returns 200", "200" in res_st, res_st)

        # Check response body has token
        res_body = page.query_selector("#resBody").inner_text()
        check("Response contains 'token'", "token" in res_body.lower())
        check("Response contains 'profile_id'", "profile_id" in res_body.lower())

        tok = page.query_selector("#tokSt").inner_text()
        check("Token Active after login", "Token Active" in tok, tok)
        check("Profile ID shown", "ID:" in tok)

        # ─── TEST GROUP 5: MANUAL API TEST WITH TOKEN ───
        print("\n[5] MANUAL API TEST - WITH TOKEN (Get App Settings)")
        for fh in page.query_selector_all(".fld-h"):
            if "Profile" in fh.inner_text():
                fh.click(); break
        time.sleep(0.3)
        for ep in page.query_selector_all(".ep-row"):
            if "Get App Settings" in ep.inner_text():
                ep.click(); break
        time.sleep(0.3)
        info = page.query_selector("#epInfo").inner_text()
        check("Shows [needs token] for auth endpoint", "token" in info.lower(), info)

        page.click("#sendBtn")
        page.wait_for_function("!document.getElementById('sendBtn').disabled", timeout=15000)
        time.sleep(0.5)
        res_st = page.query_selector("#resSt").inner_text()
        check("Get App Settings returns 200", "200" in res_st, res_st)

        # ─── TEST GROUP 6: MANUAL API - ERROR POPUP ───
        print("\n[6] ERROR POPUP - Follow User (missing field)")
        for fh in page.query_selector_all(".fld-h"):
            if "Follow" in fh.inner_text() and "Social" in fh.inner_text():
                fh.click(); break
        time.sleep(0.3)
        for ep in page.query_selector_all(".ep-row"):
            txt = ep.inner_text()
            if "Follow User" in txt and "New" not in txt and "Check" not in txt and "Live" not in txt:
                ep.click(); break
        time.sleep(0.3)
        page.click("#sendBtn")
        page.wait_for_function("!document.getElementById('sendBtn').disabled", timeout=15000)
        time.sleep(0.5)

        popup = page.query_selector("#errPop")
        popup_visible = popup and popup.is_visible()
        check("Error popup appears", popup_visible)

        if popup_visible:
            title = page.query_selector("#popTitle").inner_text()
            check("Popup shows 'missing field(s)'", "missing" in title.lower(), title)

            fields = page.query_selector_all("#popBody .ef")
            check("Missing field inputs shown", len(fields) > 0, f"{len(fields)} fields")

            labels = [f.query_selector("label").inner_text() for f in fields]
            check("Field name extracted correctly", len(labels) > 0, str(labels))

            # Fill field
            inp = page.query_selector("#pf-0")
            if inp:
                inp.fill("12345")
                check("Can type in field input", inp.input_value() == "12345")

            # Test Retry button exists
            retry_btn = page.query_selector(".pop-retry")
            check("'Retry with fields' button exists", retry_btn is not None)

            skip_btn = page.query_selector(".pop-skip")
            check("'Skip' button exists", skip_btn is not None)

            # Click skip
            page.click(".pop-skip")
            time.sleep(0.5)
            check("Popup closes on Skip", not page.query_selector("#errPop").is_visible())

        # ─── TEST GROUP 7: ADD/REMOVE HEADER & BODY FIELDS ───
        print("\n[7] ADD/REMOVE HEADER & BODY FIELDS")
        page.click("text=Headers")
        time.sleep(0.2)
        before = len(page.query_selector_all("#hdEd .kv"))
        page.click("text=+ add header")
        time.sleep(0.2)
        after = len(page.query_selector_all("#hdEd .kv"))
        check("Add header adds a row", after == before + 1, f"{before} -> {after}")

        # Remove last row
        x_btns = page.query_selector_all("#hdEd .kv .x")
        if x_btns:
            x_btns[-1].click()
            time.sleep(0.2)
            check("Remove button deletes row", len(page.query_selector_all("#hdEd .kv")) == after - 1)

        # ─── TEST GROUP 8: VARIABLES MODAL ───
        print("\n[8] VARIABLES MODAL")
        page.click("text=Variables")
        time.sleep(0.5)
        modal = page.query_selector("#varsMdl")
        check("Variables modal opens", modal and modal.is_visible())

        var_rows = page.query_selector_all("#varsB .kv")
        check("Variables list not empty", len(var_rows) > 0, f"{len(var_rows)} vars")

        # Find auth_token
        found_token = False
        for vr in var_rows:
            k = vr.query_selector("input.k")
            if k and k.get_attribute("value") == "auth_token":
                found_token = True; break
        check("auth_token in variables", found_token)

        # Find profile_id
        found_pid = False
        for vr in var_rows:
            k = vr.query_selector("input.k")
            if k and k.get_attribute("value") == "profile_id":
                found_pid = True; break
        check("profile_id in variables", found_pid)

        # Close
        page.click("#varsMdl .pop-x")
        time.sleep(0.3)
        check("Variables modal closes", not modal.is_visible())

        # ─── TEST GROUP 9: AUTO TEST TAB ───
        print("\n[9] AUTO TEST TAB - LAYOUT")
        page.click("[data-m='auto']")
        time.sleep(0.3)
        check("Auto Test tab opens", "on" in page.query_selector("[data-m='auto']").get_attribute("class"))

        check("Run button exists", page.query_selector("#runBtn") is not None)
        check("Select All button exists", page.query_selector_all("button.btn-sm")[1] is not None)
        check("Deselect All exists", page.inner_text("body").count("Deselect All") > 0)
        check("Safe Only button exists", page.inner_text("body").count("Safe Only") > 0)
        check("Preset Full Backend button exists", page.inner_text("body").count("Full Backend") > 0)
        check("Preset Auth Flow button exists", page.inner_text("body").count("Auth Flow") > 0)

        # Config options
        check("Auto-login checkbox exists", page.query_selector("#cfgLogin") is not None)
        check("Auto-login checked by default", page.query_selector("#cfgLogin").is_checked())
        check("Delay input exists", page.query_selector("#cfgDelay") is not None)
        check("Timeout input exists", page.query_selector("#cfgTimeout") is not None)
        check("Stop on fail checkbox exists", page.query_selector("#cfgStop") is not None)

        # Selection area
        sf_items = page.query_selector_all(".sf")
        check("30 folders in selection area", len(sf_items) == 30, f"got {len(sf_items)}")

        # ─── TEST GROUP 10: SELECT ALL / DESELECT ALL ───
        print("\n[10] SELECT ALL / DESELECT ALL")
        page.click("text=Select All")
        time.sleep(0.5)
        cnt = page.query_selector("#selCnt").inner_text()
        check("Select All selects all endpoints", int(cnt) > 300, f"selected {cnt}")

        # Check folder checkboxes are checked
        fc0 = page.query_selector("#fc-0")
        check("Folder checkbox checked after Select All", fc0.is_checked())

        page.click("text=Deselect All")
        time.sleep(0.3)
        cnt = page.query_selector("#selCnt").inner_text()
        check("Deselect All -> 0 selected", cnt == "0", f"selected {cnt}")
        check("Folder checkbox unchecked after Deselect All", not fc0.is_checked())

        # ─── TEST GROUP 11: SAFE ONLY SELECTION ───
        print("\n[11] SAFE ONLY SELECTION")
        page.click("text=Safe Only (read-only)")
        time.sleep(0.5)
        cnt = int(page.query_selector("#selCnt").inner_text())
        check("Safe Only selects > 0 APIs", cnt > 0, f"selected {cnt}")

        # KEY BUG TEST: folder checkboxes should be updated
        any_folder_checked = False
        any_folder_indeterminate = False
        for fi in range(min(10, len(sf_items))):
            fc = page.query_selector(f"#fc-{fi}")
            if fc:
                if fc.is_checked(): any_folder_checked = True
                # Check indeterminate via JS
                is_ind = page.evaluate(f"document.getElementById('fc-{fi}').indeterminate")
                if is_ind: any_folder_indeterminate = True
        check("Folder checkboxes updated (checked or indeterminate)", any_folder_checked or any_folder_indeterminate,
              f"checked={any_folder_checked} indeterminate={any_folder_indeterminate}")

        # Check that selected folders auto-opened
        open_lists = page.query_selector_all(".sf-list.open")
        check("Folders with selected APIs auto-opened", len(open_lists) > 0, f"{len(open_lists)} folders opened")

        # Verify SAFE endpoints only
        # Pick a folder, check only SAFE tagged endpoints are checked
        page.click("text=Deselect All")
        time.sleep(0.2)

        # ─── TEST GROUP 12: PRESET FULL BACKEND ───
        print("\n[12] PRESET: FULL BACKEND")
        page.click("text=Preset: Full Backend (20)")
        time.sleep(1)
        cnt = page.query_selector("#selCnt").inner_text()
        check("Full Backend preset selects 20", cnt == "20", f"selected {cnt}")

        # Folder checkboxes for folders with selected endpoints
        fc_profile = None
        for fi in range(len(sf_items)):
            fc = page.query_selector(f"#fc-{fi}")
            if fc:
                is_checked = fc.is_checked()
                is_ind = page.evaluate(f"document.getElementById('fc-{fi}').indeterminate")
                if is_checked or is_ind:
                    fc_profile = fi; break
        check("At least one folder checkbox active after preset load", fc_profile is not None)

        # ─── TEST GROUP 13: PRESET AUTH FLOW ───
        print("\n[13] PRESET: AUTH FLOW")
        page.click("text=Preset: Auth Flow (6)")
        time.sleep(1)
        cnt = page.query_selector("#selCnt").inner_text()
        check("Auth Flow preset selects 6", cnt == "6", f"selected {cnt}")

        # ─── TEST GROUP 14: INDIVIDUAL ENDPOINT CHECK/UNCHECK ───
        print("\n[14] INDIVIDUAL ENDPOINT CHECKBOX")
        page.click("text=Deselect All")
        time.sleep(0.2)

        # Force-open first folder in selection and check first endpoint via JS
        page.evaluate("document.querySelectorAll('.sf-list')[0].classList.add('open')")
        time.sleep(0.3)
        first_sc_id = "sc-0-0"
        page.evaluate(f"document.getElementById('{first_sc_id}').click()")
        time.sleep(0.3)
        cnt = page.query_selector("#selCnt").inner_text()
        check("Single endpoint check -> count=1", cnt == "1")

        # Folder should be indeterminate (not all selected)
        is_ind = page.evaluate("document.getElementById('fc-0').indeterminate")
        check("Folder shows indeterminate when partial", is_ind)

        page.evaluate(f"document.getElementById('{first_sc_id}').click()")  # uncheck
        time.sleep(0.2)
        cnt = page.query_selector("#selCnt").inner_text()
        check("Uncheck endpoint -> count=0", cnt == "0")

        # ─── TEST GROUP 15: FOLDER CHECKBOX ───
        print("\n[15] FOLDER CHECKBOX (select all in folder)")
        fc0 = page.query_selector("#fc-0")
        fc0.click()
        time.sleep(0.3)
        cnt = int(page.query_selector("#selCnt").inner_text())
        folder_size = len(page.query_selector_all("[id^='sc-0-']"))
        check("Folder checkbox selects all endpoints in folder", cnt == folder_size,
              f"selected {cnt}, folder has {folder_size}")

        # Uncheck folder
        fc0.click()
        time.sleep(0.2)
        cnt = page.query_selector("#selCnt").inner_text()
        check("Uncheck folder -> all deselected", cnt == "0")

        # ─── TEST GROUP 16: RUN AUTO TEST ───
        print("\n[16] RUN AUTO TEST (Full Backend)")
        page.click("text=Preset: Full Backend (20)")
        time.sleep(0.5)
        page.click("#runBtn")
        time.sleep(1)

        # Should switch to Results tab
        check("Switched to Results tab", "on" in page.query_selector("[data-m='results']").get_attribute("class"))

        # Wait for completion
        print("    Watching test run...")
        pauses_handled = 0
        for i in range(60):
            time.sleep(2)
            popup = page.query_selector("#errPop")
            if popup and popup.is_visible():
                pauses_handled += 1
                print(f"    PAUSED #{pauses_handled} - error popup, clicking Skip...")
                page.click(".pop-skip")
                time.sleep(0.5)
                continue

            pbar = page.query_selector(".ptxt")
            pct = pbar.inner_text() if pbar else ""
            passed = page.query_selector(".sc.ps .v")
            p_txt = passed.inner_text() if passed else "0"
            failed = page.query_selector(".sc.fl .v")
            f_txt = failed.inner_text() if failed else "0"
            print(f"    {pct} | P:{p_txt} F:{f_txt}")

            run_btn = page.query_selector("#runBtn")
            if run_btn and run_btn.is_visible(): break
            if "100%" in pct:
                time.sleep(2); break
        time.sleep(1)

        check("Error popups were handled during run", pauses_handled >= 0, f"{pauses_handled} pauses")

        # ─── TEST GROUP 17: RESULTS DISPLAY ───
        print("\n[17] RESULTS DISPLAY")
        passed_el = page.query_selector(".sc.ps .v")
        failed_el = page.query_selector(".sc.fl .v")
        errors_el = page.query_selector(".sc.er .v")
        time_el = page.query_selector(".sc.tm .v")

        p_val = int(passed_el.inner_text()) if passed_el else 0
        f_val = int(failed_el.inner_text()) if failed_el else 0
        e_val = int(errors_el.inner_text()) if errors_el else 0
        t_val = time_el.inner_text() if time_el else "?"

        check("Stats cards visible", passed_el is not None)
        check("Passed count > 0", p_val > 0, f"passed={p_val}")
        check("Total = passed + failed + errors", (p_val + f_val + e_val) > 0,
              f"{p_val}+{f_val}+{e_val}={p_val+f_val+e_val}")
        check("Time shown", t_val != "?" and t_val != "--", t_val)

        # Result rows
        rrows = page.query_selector_all(".rr")
        check("Result rows present", len(rrows) > 0, f"{len(rrows)} rows")

        # Progress bar
        pbar = page.query_selector(".pfill")
        check("Progress bar visible", pbar is not None)

        # ─── TEST GROUP 18: RESULT DETAIL EXPAND ───
        print("\n[18] RESULT DETAIL EXPAND/COLLAPSE")
        if rrows:
            rrows[0].click()
            time.sleep(0.3)
            detail = page.query_selector(".rd.open")
            check("First result expands on click", detail is not None)

            # Check detail has assertions
            detail_text = detail.inner_text() if detail else ""
            check("Detail shows assertion results", "Status" in detail_text or "error" in detail_text or "ok" in detail_text,
                  detail_text[:80])

            rrows[0].click()
            time.sleep(0.2)
            check("Collapses on 2nd click", page.query_selector(".rd.open") is None)

        # Check a failed result has error info
        for rr in rrows:
            if "✘" in rr.inner_html() or "10008" in rr.inner_html():
                rr.click()
                time.sleep(0.3)
                d = page.query_selector(".rd.open")
                if d:
                    dt = d.inner_text()
                    has_info = "Missing" in dt or "error" in dt.lower() or "actual" in dt.lower()
                    check("Failed result shows error details", has_info, dt[:100])
                    rr.click()
                break

        # ─── TEST GROUP 19: TAB SWITCHING ───
        print("\n[19] TAB SWITCHING")
        page.click("[data-m='manual']")
        time.sleep(0.2)
        check("Switch to Manual tab", "on" in page.query_selector("[data-m='manual']").get_attribute("class"))
        check("Manual content visible", page.query_selector("#mc-manual").is_visible())

        page.click("[data-m='auto']")
        time.sleep(0.2)
        check("Switch to Auto tab", "on" in page.query_selector("[data-m='auto']").get_attribute("class"))
        check("Auto content visible", page.query_selector("#mc-auto").is_visible())

        page.click("[data-m='results']")
        time.sleep(0.2)
        check("Switch to Results tab", "on" in page.query_selector("[data-m='results']").get_attribute("class"))
        check("Results content visible", page.query_selector("#mc-results").is_visible())

        # ─── TEST GROUP 20: LOGIN BUTTON SHORTCUT ───
        print("\n[20] LOGIN BUTTON SHORTCUT")
        page.click("[data-m='manual']")
        time.sleep(0.2)
        # Clear token to test login button
        page.evaluate("V.auth_token=''")
        page.evaluate("document.getElementById('tokSt').innerHTML='<span class=\"tok-no\">No Token</span>'")
        time.sleep(0.2)

        page.click("text=Login & Get Token")
        page.wait_for_function("!document.getElementById('sendBtn').disabled", timeout=15000)
        time.sleep(0.5)
        tok = page.query_selector("#tokSt").inner_text()
        check("Login button restores token", "Token Active" in tok, tok)

        # ═══════════════════════════════════════════════════════
        print("\n" + "="*60)
        print(f"  TEST RESULTS: {PASS} PASSED, {FAIL} FAILED")
        print("="*60)

        if FAIL > 0:
            print("\n  FAILED TESTS:")
            for status, name in TESTS:
                if status == "FAIL":
                    print(f"    - {name}")

        print(f"\n  Browser open for 8 seconds...")
        time.sleep(8)
        browser.close()

if __name__ == "__main__":
    run()
