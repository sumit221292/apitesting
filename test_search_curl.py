"""Playwright test: Search API + cURL copy"""
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
        ctx=br.new_context(viewport={"width":1400,"height":900},permissions=["clipboard-read","clipboard-write"])
        pg=ctx.new_page()

        print("\n"+"="*60)
        print("  SEARCH + CURL COPY TEST")
        print("="*60)

        pg.goto("http://localhost:5555")
        pg.wait_for_selector(".fld",timeout=10000)

        # ─── TEST 1: Search box exists ───
        print("\n[1] Search box...")
        search=pg.query_selector("#sideSearch")
        chk("Search input exists",search is not None)
        chk("Placeholder text","Search" in (search.get_attribute("placeholder") or ""))

        # ─── TEST 2: Search for 'wallet' ───
        print("\n[2] Search: 'wallet'")
        pg.fill("#sideSearch","wallet")
        time.sleep(0.5)

        visible_eps=pg.query_selector_all(".ep-row:not(.search-hide)")
        hidden_eps=pg.query_selector_all(".ep-row.search-hide")
        total_eps=pg.query_selector_all(".ep-row")
        chk("Some endpoints visible",len(visible_eps)>0,f"{len(visible_eps)} visible")
        chk("Some endpoints hidden",len(hidden_eps)>0,f"{len(hidden_eps)} hidden")
        chk("Not all visible (filtered)",len(visible_eps)<len(total_eps))

        # Check visible ones contain 'wallet'
        all_have_wallet=all("wallet" in ep.inner_text().lower() for ep in visible_eps)
        chk("All visible contain 'wallet'",all_have_wallet)

        # Check folders without matches are hidden
        hidden_folders=pg.query_selector_all(".fld.search-hide")
        chk("Folders without matches hidden",len(hidden_folders)>0,f"{len(hidden_folders)} folders hidden")

        # Check matching folders auto-opened
        open_folders=pg.query_selector_all(".fld:not(.search-hide) .fld-list.open")
        chk("Matching folders auto-opened",len(open_folders)>0,f"{len(open_folders)} opened")

        # Check highlight
        highlights=pg.query_selector_all(".search-hl")
        chk("Search term highlighted",len(highlights)>0,f"{len(highlights)} highlights")

        # ─── TEST 3: Search for 'gift' ───
        print("\n[3] Search: 'gift'")
        pg.fill("#sideSearch","gift")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("Gift search finds endpoints",len(visible)>0,f"{len(visible)} matches")

        # ─── TEST 4: Search for 'xyz_nonexistent' ───
        print("\n[4] Search: 'xyz_nonexistent'")
        pg.fill("#sideSearch","xyz_nonexistent_api")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("No results for gibberish",len(visible)==0)
        hidden_flds=pg.query_selector_all(".fld.search-hide")
        chk("All folders hidden",len(hidden_flds)==30,f"{len(hidden_flds)} hidden")

        # ─── TEST 5: Clear search restores all ───
        print("\n[5] Clear search...")
        pg.fill("#sideSearch","")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("All endpoints restored",len(visible)==len(total_eps),f"{len(visible)}")
        hidden_flds=pg.query_selector_all(".fld.search-hide")
        chk("All folders visible",len(hidden_flds)==0)

        # ─── TEST 6: Search then click endpoint ───
        print("\n[6] Search 'profile' then click endpoint...")
        pg.fill("#sideSearch","profile data")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("Profile search finds results",len(visible)>0,f"{len(visible)}")
        if visible:
            visible[0].click()
            time.sleep(0.3)
            url=pg.input_value("#mUrl")
            chk("Clicking search result selects endpoint",url!="",url)

        pg.fill("#sideSearch","")
        time.sleep(0.3)

        # ─── TEST 7: cURL button exists in manual test ───
        print("\n[7] cURL button in manual test...")
        curl_btn=pg.query_selector("text=cURL")
        chk("cURL button exists next to SEND",curl_btn is not None)

        # ─── TEST 8: Login then test cURL copy ───
        print("\n[8] Login then cURL copy...")
        pg.click("text=Login & Get Token")
        pg.wait_for_function("!document.getElementById('sendBtn').disabled",timeout=15000)
        time.sleep(0.5)

        # Select an endpoint - use search to find it quickly
        pg.fill("#sideSearch","app settings")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        if visible:visible[0].click()
        time.sleep(0.3)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        # Click cURL button
        pg.click("button:has-text('cURL')")
        time.sleep(0.5)

        # Check toast appeared
        toast=pg.query_selector("#toast")
        toast_text=toast.inner_text() if toast else ""
        chk("Toast shows 'Copied'","Copied" in toast_text or "copied" in toast_text.lower(),toast_text)

        # Read clipboard
        try:
            clip=pg.evaluate("navigator.clipboard.readText()")
            chk("Clipboard has curl command","curl" in clip.lower(),clip[:80])
            chk("Curl contains URL","zeep.live" in clip,clip[:120])
            chk("Curl contains -X method","-X" in clip)
            chk("Curl has Authorization header","Authorization" in clip or "Bearer" in clip)
        except:
            chk("Clipboard read (may need permissions)",False,"clipboard API blocked")

        # ─── TEST 9: Run auto test then check cURL on result rows ───
        print("\n[9] Run quick auto test, check cURL on result rows...")
        pg.click("[data-m='auto']")
        time.sleep(0.3)
        pg.click("text=Preset: Auth Flow (6)")
        time.sleep(0.5)
        pg.click("#runBtn")
        time.sleep(1)

        for i in range(40):
            time.sleep(2)
            pop=pg.query_selector("#errPop")
            if pop and pop.is_visible():pg.click(".pop-skip");time.sleep(0.3);continue
            rb=pg.query_selector("#runBtn")
            if rb and rb.is_visible():break
        time.sleep(1)

        # Check cURL buttons on result rows
        curl_btns=pg.query_selector_all(".curl-btn")
        chk("cURL buttons on result rows",len(curl_btns)>0,f"{len(curl_btns)} buttons")

        # Click first cURL button
        if curl_btns:
            curl_btns[0].click()
            time.sleep(0.5)
            toast=pg.query_selector("#toast")
            chk("Toast shows on result cURL click","Copied" in (toast.inner_text() if toast else ""))
            try:
                clip=pg.evaluate("navigator.clipboard.readText()")
                chk("Result cURL in clipboard","curl" in clip.lower(),clip[:80])
            except:
                chk("Result clipboard read",False,"blocked")

        # ─── TEST 10: Search in Auto Test tab works too ───
        print("\n[10] Search works while on Auto Test tab...")
        pg.click("[data-m='auto']")
        time.sleep(0.3)
        pg.fill("#sideSearch","moment")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("Search works on any tab",len(visible)>0,f"{len(visible)} moment APIs")
        pg.fill("#sideSearch","")

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        print("\n  Browser open 8s...")
        time.sleep(8)
        br.close()

if __name__=="__main__":run()
