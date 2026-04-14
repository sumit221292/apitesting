"""Playwright HEADED test: Add API, Add Collection, Manage (delete), Export."""
import sys,os,time,json
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
        pg.goto("http://localhost:5555")
        pg.wait_for_selector(".fld",timeout=10000)

        print("\n"+"="*60)
        print("  ADD / REMOVE / COLLECTION MANAGEMENT TEST")
        print("="*60)

        initial_count=int(pg.evaluate("A.length"))
        print(f"  Initial endpoint count: {initial_count}")

        # ─── TEST 1: Sidebar buttons exist ───
        print("\n[1] Sidebar buttons...")
        chk("'+ Add API' button",pg.inner_text(".side").count("Add API")>0)
        chk("'+ Collection' button",pg.inner_text(".side").count("Collection")>0)
        chk("'Manage' button",pg.inner_text(".side").count("Manage")>0)

        # ─── TEST 2: Add API modal ───
        print("\n[2] Add API modal...")
        pg.click("text=+ Add API")
        time.sleep(0.5)
        mdl=pg.query_selector("#addApiMdl")
        chk("Add API modal opens",mdl and mdl.is_visible())

        # Check fields
        chk("Folder dropdown",pg.query_selector("#addApiFolder") is not None)
        chk("New folder input",pg.query_selector("#addApiFolderNew") is not None)
        chk("Name input",pg.query_selector("#addApiName") is not None)
        chk("Method select",pg.query_selector("#addApiMethod") is not None)
        chk("URL input",pg.query_selector("#addApiUrl") is not None)
        chk("Auth select",pg.query_selector("#addApiAuth") is not None)
        chk("Body textarea",pg.query_selector("#addApiBody") is not None)
        chk("Headers textarea",pg.query_selector("#addApiHeaders") is not None)

        # Folder dropdown has options from existing folders
        opts=pg.query_selector_all("#addApiFolder option")
        chk("Folder dropdown has existing folders",len(opts)>5,f"{len(opts)} options")

        # ─── TEST 3: Add a custom API ───
        print("\n[3] Add custom API endpoint...")
        pg.fill("#addApiFolderNew","My Test Folder")
        pg.fill("#addApiName","Custom Health Check")
        pg.select_option("#addApiMethod","GET")
        pg.fill("#addApiUrl","https://testingphp.zeep.live/api/health")
        pg.select_option("#addApiAuth","no")
        pg.fill("#addApiBody","status=ok")

        pg.click("#addApiMdl button:has-text('Add API')")
        time.sleep(1)

        # Check toast
        toast=pg.query_selector("#toast")
        chk("Toast shows 'added'","added" in (toast.inner_text() if toast else "").lower() or "Added" in (toast.inner_text() if toast else ""))

        # Check new count
        new_count=int(pg.evaluate("A.length"))
        chk("Endpoint count increased",new_count==initial_count+1,f"{initial_count} -> {new_count}")

        # Check new folder appears in sidebar
        sidebar_text=pg.inner_text("#sideBody")
        chk("New folder 'My Test Folder' in sidebar","My Test Folder" in sidebar_text)

        # Search for new API
        pg.fill("#sideSearch","Custom Health")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("New API searchable in sidebar",len(visible)>=1)
        pg.fill("#sideSearch","")
        time.sleep(0.3)

        # ─── TEST 4: Add another API to existing folder ───
        print("\n[4] Add API to existing folder...")
        pg.click("text=+ Add API")
        time.sleep(0.5)
        pg.select_option("#addApiFolder","03 - Profile")
        pg.fill("#addApiFolderNew","")
        pg.fill("#addApiName","Custom Profile Check")
        pg.fill("#addApiUrl","https://testingphp.zeep.live/api/custom-profile")
        pg.select_option("#addApiAuth","yes")
        pg.fill("#addApiBody","profile_id={{profile_id}}")
        pg.click("#addApiMdl button:has-text('Add API')")
        time.sleep(1)
        count_after=int(pg.evaluate("A.length"))
        chk("Second API added",count_after==new_count+1,f"{new_count} -> {count_after}")

        # ─── TEST 5: Add Collection modal ───
        print("\n[5] Add Collection modal...")
        pg.click("text=+ Collection")
        time.sleep(0.5)
        mdl=pg.query_selector("#addCollMdl")
        chk("Collection modal opens",mdl and mdl.is_visible())
        chk("File upload input",pg.query_selector("#collFile") is not None)
        chk("JSON textarea",pg.query_selector("#collJson") is not None)
        chk("Merge button",pg.inner_text("#addCollMdl").count("Merge")>0)
        chk("Replace button",pg.inner_text("#addCollMdl").count("Replace")>0)

        # Paste a mini collection
        mini_coll=json.dumps({
            "info":{"name":"Mini Test Collection"},
            "item":[{
                "name":"Mini Folder",
                "item":[{
                    "name":"Mini API Endpoint",
                    "request":{
                        "method":"GET",
                        "url":{"raw":"https://example.com/api/test"},
                        "header":[],"body":{}
                    }
                }]
            }]
        })
        pg.fill("#collJson",mini_coll)
        time.sleep(0.3)

        # Click Merge
        pg.click("text=Merge (add to existing)")
        time.sleep(1)
        merge_count=int(pg.evaluate("A.length"))
        chk("Collection merged (1 new API added)",merge_count==count_after+1,f"{count_after} -> {merge_count}")

        # Search for merged API
        pg.fill("#sideSearch","Mini API")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("Merged API searchable",len(visible)>=1)
        pg.fill("#sideSearch","")
        time.sleep(0.3)

        # ─── TEST 6: Manage modal ───
        print("\n[6] Manage modal...")
        pg.click("text=Manage")
        time.sleep(0.5)
        mdl=pg.query_selector("#manageMdl")
        chk("Manage modal opens",mdl and mdl.is_visible())

        # Check elements
        chk("Search in manage",pg.query_selector("#manageSearch") is not None)
        chk("Delete Selected button",pg.inner_text("#manageMdl").count("Delete Selected")>0)
        chk("Export JSON button",pg.inner_text("#manageMdl").count("Export JSON")>0)
        chk("Folder delete buttons",len(pg.query_selector_all("#manageList [onclick*='deleteFolder']"))>0)

        # Search in manage
        pg.fill("#manageSearch","Mini API")
        time.sleep(0.3)
        visible=pg.query_selector_all(".mg-ep:not([style*='display: none'])")
        chk("Manage search filters",len(visible)>=1,f"{len(visible)} visible")
        pg.fill("#manageSearch","")
        time.sleep(0.2)

        # ─── TEST 7: Delete single API ───
        print("\n[7] Delete single API...")
        pg.fill("#manageSearch","Mini API")
        time.sleep(0.3)
        # Find the x button for Mini API
        pg.on("dialog",lambda d:d.accept())
        mini_x=pg.query_selector_all(".mg-ep:not([style*='display: none']) .btn-sm")
        if mini_x:
            mini_x[0].click()
            time.sleep(1)
            after_del=int(pg.evaluate("A.length"))
            chk("API deleted",after_del==merge_count-1,f"{merge_count} -> {after_del}")
        else:
            chk("Found delete button for Mini API",False)

        # ─── TEST 8: Delete folder ───
        print("\n[8] Delete custom folder...")
        pg.click("text=Manage")
        time.sleep(0.5)
        pg.fill("#manageSearch","My Test Folder")
        time.sleep(0.3)

        folder_del_btns=pg.query_selector_all("#manageList [onclick*='deleteFolder']")
        # Find the My Test Folder delete button
        found=False
        for btn in folder_del_btns:
            parent=btn.evaluate("el=>el.parentElement.textContent")
            if "My Test Folder" in parent:
                btn.click();time.sleep(1);found=True;break
        if found:
            after_folder_del=int(pg.evaluate("A.length"))
            chk("Folder deleted",after_folder_del<after_del,f"from {after_del} to {after_folder_del}")
        else:
            chk("My Test Folder delete button found",False)

        # ─── TEST 9: Export collection ───
        print("\n[9] Export collection...")
        pg.click("text=Manage")
        time.sleep(0.5)

        # Check export works via API
        resp=pg.evaluate("fetch('/api/collection/export').then(r=>r.json()).then(d=>({name:d.info.name,items:d.item.length,total:d.item.reduce((s,f)=>s+(f.item?f.item.length:0),0)}))")
        chk("Export has collection name","name" in resp,resp.get('name',''))
        chk("Export has folders",resp.get('items',0)>0,f"{resp.get('items',0)} folders")
        chk("Export has endpoints",resp.get('total',0)>0,f"{resp.get('total',0)} endpoints")

        pg.click("text=Export JSON")
        time.sleep(1)
        chk("Export toast shown","export" in (pg.query_selector("#toast").inner_text() if pg.query_selector("#toast") else "").lower())

        # Close
        pg.evaluate("closeAllMdl()")
        time.sleep(0.3)

        # ─── TEST 10: Delete selected (bulk) ───
        print("\n[10] Bulk delete selected...")
        # Add 2 temp APIs first
        for i in range(2):
            pg.evaluate(f"""fetch('/api/endpoints/add',{{method:'POST',headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{folder:'Temp Folder',name:'TempAPI{i}',method:'GET',url:'https://example.com/{i}',needs_auth:false,headers:[],body_fields:[]}})
            }})""")
        time.sleep(0.5)
        pg.evaluate("reloadData()")
        time.sleep(0.5)

        before_bulk=int(pg.evaluate("A.length"))
        pg.click("text=Manage")
        time.sleep(0.5)
        pg.fill("#manageSearch","TempAPI")
        time.sleep(0.3)

        # Check both checkboxes
        cbs=pg.query_selector_all(".mg-ep:not([style*='display: none']) input[type=checkbox]")
        for cb in cbs[:2]:
            cb.click()
        time.sleep(0.2)

        cnt_text=pg.query_selector("#manageSelCnt").inner_text()
        chk("2 selected for bulk delete","2" in cnt_text,cnt_text)

        pg.click("text=Delete Selected")
        time.sleep(1)
        after_bulk=int(pg.evaluate("A.length"))
        chk("Bulk delete removed APIs",after_bulk==before_bulk-2,f"{before_bulk} -> {after_bulk}")

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        print("\n  Browser open 8s...")
        time.sleep(8)
        br.close()

if __name__=="__main__":run()
