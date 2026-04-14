"""Playwright test: Load Test config explanations + API search."""
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
        pg.goto("http://localhost:5555")
        pg.wait_for_selector(".fld",timeout=10000)

        print("\n"+"="*60)
        print("  LOAD TEST: CONFIG + API SEARCH TEST")
        print("="*60)

        # Login
        pg.click("text=Login & Get Token")
        pg.wait_for_function("!document.getElementById('sendBtn').disabled",timeout=15000)
        time.sleep(0.5)

        # Go to Load Test tab
        pg.click("[data-m='load']")
        time.sleep(0.5)

        # ─── TEST 1: Tooltip ? icons ───
        print("\n[1] Config has ? tooltips...")
        q_icons=pg.query_selector_all(".lc-q")
        chk("? tooltip icons exist",len(q_icons)>=7,f"{len(q_icons)} found")

        # Check each has a title attribute
        all_have_title=all(q.get_attribute("title") for q in q_icons)
        chk("All ? icons have tooltip text",all_have_title)

        # ─── TEST 2: Hindi hints visible ───
        print("\n[2] Hindi/Urdu hints under each config...")
        hints=pg.query_selector_all(".lc-hint")
        chk("Hint texts present",len(hints)>=5,f"{len(hints)} hints")
        # Check at least one has Hindi text
        hindi_found=any("user" in h.inner_text().lower() or "dheere" in h.inner_text().lower() or "real" in h.inner_text().lower() for h in hints)
        chk("Hints in understandable language",hindi_found)

        # ─── TEST 3: Pattern dropdown has descriptions ───
        print("\n[3] Pattern dropdown options...")
        options=pg.query_selector_all("#ltPattern option")
        opt_texts=[o.inner_text() for o in options]
        chk("4 patterns available",len(options)==4,str(opt_texts))
        chk("Ramp option has description","dheere" in opt_texts[0].lower() or "gradual" in opt_texts[0].lower())

        # Change pattern and check hint updates
        pg.select_option("#ltPattern","spike")
        time.sleep(0.3)
        hint=pg.query_selector("#patternHint").inner_text()
        chk("Spike pattern hint updates",len(hint)>5,hint)

        pg.select_option("#ltPattern","stress")
        time.sleep(0.3)
        hint=pg.query_selector("#patternHint").inner_text()
        chk("Stress pattern hint updates","server" in hint.lower() or "tute" in hint.lower() or "add" in hint.lower(),hint)

        # ─── TEST 4: API Search in load test ───
        print("\n[4] API search box in endpoint list...")
        search=pg.query_selector("#ltEpSearch")
        chk("Search input exists in load test",search is not None)
        chk("Placeholder says Search",search.get_attribute("placeholder")=="Search APIs...")

        # ─── TEST 5: Search for 'wallet' ───
        print("\n[5] Search: 'wallet'")
        pg.fill("#ltEpSearch","wallet")
        time.sleep(0.5)

        visible=pg.query_selector_all(".lt-ep-row:not(.lt-hide)")
        hidden=pg.query_selector_all(".lt-ep-row.lt-hide")
        total=pg.query_selector_all(".lt-ep-row")
        chk("Wallet search filters",len(visible)>0 and len(hidden)>0,f"{len(visible)} visible, {len(hidden)} hidden of {len(total)}")
        all_match=all("wallet" in r.inner_text().lower() for r in visible)
        chk("All visible contain 'wallet'",all_match)

        # Check highlight
        hl=pg.query_selector_all(".lt-ep-hl")
        chk("Search term highlighted",len(hl)>0,f"{len(hl)} highlights")

        # ─── TEST 6: Search for 'profile' ───
        print("\n[6] Search: 'profile'")
        pg.fill("#ltEpSearch","profile")
        time.sleep(0.5)
        visible=pg.query_selector_all(".lt-ep-row:not(.lt-hide)")
        chk("Profile search finds results",len(visible)>0,f"{len(visible)} matches")

        # ─── TEST 7: Search for 'broadcast' ───
        print("\n[7] Search: 'broadcast'")
        pg.fill("#ltEpSearch","broadcast")
        time.sleep(0.5)
        visible=pg.query_selector_all(".lt-ep-row:not(.lt-hide)")
        chk("Broadcast search works",len(visible)>0,f"{len(visible)} matches")

        # ─── TEST 8: Clear search ───
        print("\n[8] Clear search...")
        pg.fill("#ltEpSearch","")
        time.sleep(0.5)
        visible=pg.query_selector_all(".lt-ep-row:not(.lt-hide)")
        total=pg.query_selector_all(".lt-ep-row")
        chk("All endpoints restored",len(visible)==len(total),f"{len(visible)} of {len(total)}")

        # ─── TEST 9: Search + Select ───
        print("\n[9] Search then select specific APIs...")
        pg.click("text=Clear")  # deselect all first
        time.sleep(0.3)

        pg.fill("#ltEpSearch","gift")
        time.sleep(0.5)
        visible=pg.query_selector_all(".lt-ep-row:not(.lt-hide)")
        # Check first 3 visible
        checked=0
        for row in visible[:3]:
            cb=row.query_selector("input[type=checkbox]")
            if cb:cb.click();checked+=1
        time.sleep(0.3)
        cnt=pg.query_selector("#ltEpCnt").inner_text()
        chk("Selected gift APIs via search",int(cnt.strip("()"))==checked,f"selected {cnt}")

        pg.fill("#ltEpSearch","")
        time.sleep(0.3)

        # ─── TEST 10: Quick load test with searched+selected APIs ───
        print("\n[10] Quick load test with selected APIs (3 VUs, 10s)...")
        # Add more APIs
        pg.evaluate("ltSelPreset()")
        time.sleep(0.5)

        pg.evaluate("document.getElementById('ltVUs').value=3;document.getElementById('ltVUsVal').textContent='3'")
        pg.evaluate("document.getElementById('ltDuration').value=10;document.getElementById('ltDurVal').textContent='10s'")
        pg.select_option("#ltPattern","ramp")

        pg.click("#ltRunBtn")
        time.sleep(1)
        chk("Load test started",not pg.query_selector("#ltRunBtn").is_visible())

        for i in range(15):
            time.sleep(2)
            if pg.query_selector("#ltRunBtn").is_visible():break
            vus=pg.query_selector("#ls-vus").inner_text()
            rps=pg.query_selector("#ls-rps").inner_text()
            total=pg.query_selector("#ls-total").inner_text()
            print(f"    VUs:{vus} RPS:{rps} Total:{total}")
        time.sleep(1)

        total_final=pg.query_selector("#ls-total").inner_text()
        chk("Load test completed with requests",int(total_final)>0,f"{total_final} requests")

        # Check summary
        summary=pg.query_selector("#ltSummary").inner_text()
        chk("Summary has endpoint breakdown","Endpoint" in summary or "Reqs" in summary,summary[:60])

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        print("\n  Browser open 8s...")
        time.sleep(8)
        br.close()

if __name__=="__main__":run()
