"""Playwright test: New Add API modal with endpoint path + body type."""
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
        print("  ADD API - ENDPOINT PATH + BODY TYPE TEST")
        print("="*60)

        # ─── TEST 1: Open modal ───
        print("\n[1] Open Add API modal...")
        pg.click("text=+ Add API")
        time.sleep(0.5)
        chk("Modal opens",pg.query_selector("#addApiMdl").is_visible())

        # ─── TEST 2: Check new fields exist ───
        print("\n[2] New fields exist...")
        chk("Base URL field",pg.query_selector("#addApiBase") is not None)
        base_val=pg.input_value("#addApiBase")
        chk("Base URL pre-filled","testingphp.zeep.live" in base_val,base_val)

        chk("Endpoint path field",pg.query_selector("#addApiEndpoint") is not None)
        ep_placeholder=pg.query_selector("#addApiEndpoint").get_attribute("placeholder")
        chk("Endpoint placeholder",ep_placeholder and len(ep_placeholder)>0,ep_placeholder)

        chk("/api/ prefix shown",pg.inner_text("#addApiMdl").count("/api/")>=1)

        chk("Body Type selector",pg.query_selector("#addApiBodyType") is not None)
        opts=pg.query_selector_all("#addApiBodyType option")
        opt_texts=[o.inner_text() for o in opts]
        chk("4 body types",len(opts)==4,str(opt_texts))
        chk("form-data option","form-data" in opt_texts[0])
        chk("urlencoded option","urlencoded" in opt_texts[1])
        chk("raw JSON option","raw" in opt_texts[2].lower() or "json" in opt_texts[2].lower())
        chk("No Body option","no body" in opt_texts[3].lower() or "none" in opt_texts[3].lower())

        chk("KV field rows exist",len(pg.query_selector_all(".add-kv-row"))>=2)
        chk("Preview area",pg.query_selector("#addApiPreview") is not None)

        # ─── TEST 3: Add API with endpoint path ───
        print("\n[3] Add API with endpoint path...")
        pg.fill("#addApiFolderNew","Test Endpoints")
        pg.fill("#addApiName","Get Health Status")
        pg.select_option("#addApiMethod","GET")
        pg.fill("#addApiEndpoint","health-check")
        pg.select_option("#addApiAuth","no")
        pg.select_option("#addApiBodyType","none")
        time.sleep(0.3)

        # Check preview
        preview=pg.inner_text("#addApiPreview")
        chk("Preview shows full URL","health-check" in preview,preview)
        chk("Preview shows GET method","GET" in preview)
        chk("Preview shows no body or none","none" in preview.lower() or "None" in preview)

        pg.click("#addApiMdl button:has-text('Add API')")
        time.sleep(1)
        chk("API added successfully",pg.query_selector("#addApiMdl") is None or not pg.query_selector("#addApiMdl").is_visible())

        # Search for it
        pg.fill("#sideSearch","health status")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("New API found in sidebar",len(visible)>=1)
        if visible:
            visible[0].click()
            time.sleep(0.3)
            url=pg.input_value("#mUrl")
            chk("URL has correct endpoint path","health-check" in url,url)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        # ─── TEST 4: Add POST API with form-data body ───
        print("\n[4] Add POST API with form-data...")
        pg.click("text=+ Add API")
        time.sleep(0.5)
        pg.fill("#addApiFolderNew","Test Endpoints")
        pg.fill("#addApiName","Submit User Data")
        pg.select_option("#addApiMethod","POST")
        pg.fill("#addApiEndpoint","submit-data")
        pg.select_option("#addApiAuth","yes")
        pg.select_option("#addApiBodyType","formdata")
        time.sleep(0.2)

        # Check KV area visible, raw hidden
        kv_visible=pg.query_selector("#addApiBodyArea").is_visible()
        raw_hidden=not pg.query_selector("#addApiRawBody").is_visible()
        chk("form-data: KV area visible",kv_visible)
        chk("form-data: Raw area hidden",raw_hidden)

        # Add fields
        rows=pg.query_selector_all(".add-kv-row")
        if len(rows)>=2:
            inputs=rows[0].query_selector_all("input")
            inputs[0].fill("user_id")
            inputs[1].fill("{{profile_id}}")
            inputs=rows[1].query_selector_all("input")
            inputs[0].fill("type")
            inputs[1].fill("1")

        time.sleep(0.3)
        preview=pg.inner_text("#addApiPreview")
        chk("Preview shows fields","user_id" in preview and "type" in preview,preview[:80])
        chk("Preview shows Bearer","Bearer" in preview or "Token" in preview)

        pg.click("#addApiMdl button:has-text('Add API')")
        time.sleep(1)

        # Verify
        pg.fill("#sideSearch","submit user")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("POST API added and found",len(visible)>=1)
        if visible:
            visible[0].click()
            time.sleep(0.3)
            body_text=pg.inner_text("#bdEd")
            chk("Body has user_id field","user_id" in body_text,body_text[:60])
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        # ─── TEST 5: Add API with raw JSON body ───
        print("\n[5] Add API with raw JSON body...")
        pg.click("text=+ Add API")
        time.sleep(0.5)
        pg.fill("#addApiFolderNew","Test Endpoints")
        pg.fill("#addApiName","Send JSON Payload")
        pg.select_option("#addApiMethod","POST")
        pg.fill("#addApiEndpoint","json-endpoint")
        pg.select_option("#addApiBodyType","raw")
        time.sleep(0.2)

        # Check raw area visible, KV hidden
        kv_hidden=not pg.query_selector("#addApiBodyArea").is_visible()
        raw_visible=pg.query_selector("#addApiRawBody").is_visible()
        chk("raw JSON: KV area hidden",kv_hidden)
        chk("raw JSON: Raw textarea visible",raw_visible)

        pg.fill("#addApiRawBody",'{"action":"test","value":42}')
        time.sleep(0.2)

        pg.click("#addApiMdl button:has-text('Add API')")
        time.sleep(1)
        chk("Raw JSON API added",not pg.query_selector("#addApiMdl").is_visible())

        # ─── TEST 6: Body type 'No Body' hides body section ───
        print("\n[6] No Body type hides body section...")
        pg.click("text=+ Add API")
        time.sleep(0.5)
        pg.select_option("#addApiBodyType","none")
        time.sleep(0.2)
        body_grp=pg.query_selector("#addApiBodyGrp")
        chk("No Body: body section hidden",body_grp and not body_grp.is_visible())

        pg.select_option("#addApiBodyType","formdata")
        time.sleep(0.2)
        chk("Switch back to formdata: body visible",body_grp and body_grp.is_visible())

        pg.evaluate("closeAllMdl()")
        time.sleep(0.3)

        # ─── TEST 7: Add field button ───
        print("\n[7] Add Field button...")
        pg.click("text=+ Add API")
        time.sleep(0.5)
        before=len(pg.query_selector_all(".add-kv-row"))
        pg.click("#addApiMdl button:has-text('+ Add Field')")
        time.sleep(0.2)
        after=len(pg.query_selector_all(".add-kv-row"))
        chk("Add Field adds a row",after==before+1,f"{before} -> {after}")

        # Remove a row
        x_btns=pg.query_selector_all(".add-kv-row .x")
        if x_btns:
            x_btns[-1].click()
            time.sleep(0.2)
            chk("Remove field works",len(pg.query_selector_all(".add-kv-row"))==after-1)

        pg.evaluate("closeAllMdl()")

        # ─── Cleanup ───
        print("\n[8] Cleanup test endpoints...")
        pg.on("dialog",lambda d:d.accept())
        pg.evaluate("""
            fetch('/api/endpoints/delete',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({names:['Get Health Status','Submit User Data','Send JSON Payload']})})
        """)
        time.sleep(0.5)
        pg.evaluate("reloadData()")
        time.sleep(0.5)
        final=pg.evaluate("A.length")
        chk("Cleanup done, back to original count",final==378,f"count: {final}")

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        print("\n  Browser open 6s...")
        time.sleep(6)
        br.close()

if __name__=="__main__":run()
