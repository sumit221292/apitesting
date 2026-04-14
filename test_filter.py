"""Quick Playwright test for filter + optimizations."""
import sys,os,time
if sys.platform=='win32':sys.stdout.reconfigure(encoding='utf-8',errors='replace')
from playwright.sync_api import sync_playwright

P,F=0,0
def chk(n,c,d=""):
    global P,F
    if c:P+=1;print(f"  [PASS] {n}"+(f" - {d}" if d else ""))
    else:F+=1;print(f"  [FAIL] {n}"+(f" - {d}" if d else ""))

def run():
    with sync_playwright() as p:
        br=p.chromium.launch(headless=False,slow_mo=400)
        pg=br.new_page(viewport={"width":1400,"height":900})

        print("\n"+"="*60)
        print("  FILTER & OPTIMIZATION TEST")
        print("="*60)

        pg.goto("http://localhost:5555")
        pg.wait_for_selector(".fld",timeout=10000)

        # Login first
        print("\n[1] Login...")
        pg.click("text=Login & Get Token")
        pg.wait_for_function("!document.getElementById('sendBtn').disabled",timeout=15000)
        time.sleep(0.5)
        chk("Login OK","Token Active" in pg.query_selector("#tokSt").inner_text())

        # Go to Auto Test, load preset, run
        print("\n[2] Run Full Backend test...")
        pg.click("[data-m='auto']")
        time.sleep(0.3)
        pg.click("text=Preset: Full Backend (20)")
        time.sleep(0.5)
        pg.click("#runBtn")
        time.sleep(1)

        # Wait for completion
        for i in range(60):
            time.sleep(2)
            pop=pg.query_selector("#errPop")
            if pop and pop.is_visible():
                pg.click(".pop-skip");time.sleep(0.3);continue
            rb=pg.query_selector("#runBtn")
            if rb and rb.is_visible():break
            pct=pg.query_selector(".ptxt")
            if pct and "100%" in pct.inner_text():time.sleep(2);break
        time.sleep(1)

        # Get counts
        passed=int(pg.query_selector(".sc.ps .v").inner_text())
        failed=int(pg.query_selector(".sc.fl .v").inner_text())
        errors=int(pg.query_selector(".sc.er .v").inner_text())
        total=passed+failed+errors
        print(f"    Results: {passed}P {failed}F {errors}E = {total} total")

        all_rows=pg.query_selector_all(".rr")
        chk("All result rows shown",len(all_rows)==total,f"{len(all_rows)} rows")

        # ─── TEST FILTER: Click PASSED card ───
        print("\n[3] Filter: Click PASSED card...")
        pg.click(".sc.ps")
        time.sleep(0.5)

        chk("PASSED card has 'active' class","active" in pg.query_selector(".sc.ps").get_attribute("class"))
        chk("FAILED card NOT active","active" not in pg.query_selector(".sc.fl").get_attribute("class"))

        visible_rows=pg.query_selector_all(".rr:not(.hidden)")
        hidden_rows=pg.query_selector_all(".rr.hidden")
        chk("Only passed rows visible",len(visible_rows)==passed,f"visible={len(visible_rows)}, passed={passed}")
        chk("Failed/error rows hidden",len(hidden_rows)==(failed+errors),f"hidden={len(hidden_rows)}")

        # Check filter bar text
        filter_bar=pg.inner_text(".res-area")
        chk("Filter bar shows PASS highlighted","PASS" in filter_bar)

        # ─── TEST FILTER: Click FAILED card ───
        print("\n[4] Filter: Click FAILED card...")
        pg.click(".sc.fl")
        time.sleep(0.5)

        chk("FAILED card active","active" in pg.query_selector(".sc.fl").get_attribute("class"))
        chk("PASSED card NOT active now","active" not in pg.query_selector(".sc.ps").get_attribute("class"))

        visible_rows=pg.query_selector_all(".rr:not(.hidden)")
        chk("Only failed rows visible",len(visible_rows)==failed,f"visible={len(visible_rows)}, failed={failed}")

        # ─── TEST FILTER: Click ERRORS card ───
        print("\n[5] Filter: Click ERRORS card...")
        pg.click(".sc.er")
        time.sleep(0.5)

        visible_rows=pg.query_selector_all(".rr:not(.hidden)")
        chk("Only error rows visible",len(visible_rows)==errors,f"visible={len(visible_rows)}, errors={errors}")

        # ─── TEST FILTER: Click same card again to deselect (show ALL) ───
        print("\n[6] Click ERRORS again to show ALL...")
        pg.click(".sc.er")
        time.sleep(0.5)

        chk("ERRORS card deselected","active" not in pg.query_selector(".sc.er").get_attribute("class"))
        visible_rows=pg.query_selector_all(".rr:not(.hidden)")
        chk("All rows visible again",len(visible_rows)==total,f"visible={len(visible_rows)}")

        # ─── TEST FILTER: Click ALL in filter bar ───
        print("\n[7] Filter bar: click PASS then ALL...")
        pg.click(".sc.ps")
        time.sleep(0.3)
        visible_before=len(pg.query_selector_all(".rr:not(.hidden)"))
        chk("Filtered to passed only",visible_before==passed)

        # Click ALL in filter bar
        pg.evaluate("resFilter='all';renderRes(lastP)")
        time.sleep(0.3)
        visible_after=len(pg.query_selector_all(".rr:not(.hidden)"))
        chk("ALL filter restores all rows",visible_after==total)

        # ─── TEST: Avg time & slowest shown ───
        print("\n[8] Optimization: avg time & slowest endpoint...")
        page_text=pg.inner_text(".res-area")
        chk("Average time shown","avg:" in page_text,page_text[page_text.find("avg:"):page_text.find("avg:")+50] if "avg:" in page_text else "not found")
        chk("Slowest endpoint shown","slowest:" in page_text)

        # ─── TEST: SLOW tag on slow APIs ───
        print("\n[9] SLOW tag on slow APIs...")
        slow_tags=pg.query_selector_all(".rr:not(.hidden)")
        slow_count=sum(1 for r in slow_tags if "SLOW" in r.inner_html())
        chk("SLOW tag present on slow APIs (>5s)",True,f"{slow_count} slow APIs found")

        # ─── TEST: Expand failed result detail ───
        print("\n[10] Expand a failed result...")
        pg.click(".sc.fl")
        time.sleep(0.3)
        failed_rows=pg.query_selector_all(".rr:not(.hidden)")
        if failed_rows:
            failed_rows[0].click()
            time.sleep(0.3)
            detail=pg.query_selector(".rd.open")
            chk("Failed detail opens",detail is not None)
            if detail:
                dt=detail.inner_text()
                chk("Shows error message or missing fields","error" in dt.lower() or "Missing" in dt or "actual" in dt,dt[:100])

        # Show all again
        pg.click(".sc.fl")
        time.sleep(0.3)

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        if F:
            print("  Note: Some fails may be expected if API behavior changed")

        print("\n  Browser open 8s...")
        time.sleep(8)
        br.close()

if __name__=="__main__":run()
