"""Playwright test: Save, Edit, Delete endpoints."""
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
        pg.on("dialog",lambda d:d.accept())

        print("\n"+"="*60)
        print("  SAVE / EDIT / DELETE ENDPOINT TEST")
        print("="*60)

        initial=int(pg.evaluate("A.length"))
        print(f"  Initial: {initial} endpoints")

        # ─── TEST 1: Buttons hidden when no endpoint selected ───
        print("\n[1] Buttons hidden initially...")
        chk("Save hidden",not pg.query_selector("#btnSaveEp").is_visible())
        chk("Edit hidden",not pg.query_selector("#btnEditEp").is_visible())
        chk("Delete hidden",not pg.query_selector("#btnDelEp").is_visible())

        # ─── TEST 2: Select endpoint -> buttons appear ───
        print("\n[2] Select endpoint -> buttons appear...")
        pg.fill("#sideSearch","app settings")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        if visible:visible[0].click()
        time.sleep(0.3)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        chk("Save button visible",pg.query_selector("#btnSaveEp").is_visible())
        chk("Edit button visible",pg.query_selector("#btnEditEp").is_visible())
        chk("Delete button visible",pg.query_selector("#btnDelEp").is_visible())

        # ─── TEST 3: Add a test API first ───
        print("\n[3] Add test API for editing...")
        pg.evaluate("""
            fetch('/api/endpoints/add',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({folder:'Edit Test',name:'TestEditAPI',method:'POST',
                url:'https://testingphp.zeep.live/api/test-edit',needs_auth:true,
                headers:[{key:'Authorization',value:'Bearer {{auth_token}}',type:'text'}],
                body_fields:[{key:'user_id',value:'123',type:'text'},{key:'action',value:'test',type:'text'}],
                body_type:'formdata'})
            })
        """)
        time.sleep(0.5)
        pg.evaluate("reloadData()")
        time.sleep(0.5)
        after_add=int(pg.evaluate("A.length"))
        chk("Test API added",after_add==initial+1,f"{initial} -> {after_add}")

        # Select it
        pg.fill("#sideSearch","TestEditAPI")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("Test API found in sidebar",len(visible)>=1)
        if visible:visible[0].click()
        time.sleep(0.3)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        # ─── TEST 4: Save Changes (modify body in UI then save) ───
        print("\n[4] Save Changes - add field in UI then save...")
        # Switch to body tab
        body_tab=pg.query_selector_all(".m-pnl")[0].query_selector_all(".tab")[1]
        body_tab.click()
        time.sleep(0.3)

        # Verify existing fields
        kv_rows=pg.query_selector_all("#bdEd .kv")
        chk("Existing body fields loaded",len(kv_rows)>=2,f"{len(kv_rows)} rows")

        # Add a new field via UI
        pg.click("text=+ add field")
        time.sleep(0.2)
        new_rows=pg.query_selector_all("#bdEd .kv")
        last_row=new_rows[-1]
        inputs=last_row.query_selector_all("input")
        inputs[0].fill("new_field")
        inputs[1].fill("new_value")
        time.sleep(0.2)

        # Click Save
        pg.click("#btnSaveEp")
        time.sleep(1)

        # Verify save toast
        toast_text=pg.query_selector("#toast").inner_text() if pg.query_selector("#toast") else ""
        chk("Save toast shown","Saved" in toast_text or "saved" in toast_text.lower(),toast_text)

        # Re-select and verify field persisted
        pg.fill("#sideSearch","TestEditAPI")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        if visible:visible[0].click()
        time.sleep(0.3)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        # Check body has 3 fields now
        body_tab=pg.query_selector_all(".m-pnl")[0].query_selector_all(".tab")[1]
        body_tab.click()
        time.sleep(0.2)
        kv_rows=pg.query_selector_all("#bdEd .kv")
        body_text=pg.inner_text("#bdEd")
        chk("New field persisted after save","new_field" in body_text,f"{len(kv_rows)} rows, text: {body_text[:60]}")

        # ─── TEST 5: Edit endpoint (opens modal pre-filled) ───
        print("\n[5] Edit endpoint -> opens pre-filled modal...")
        pg.click("#btnEditEp")
        time.sleep(0.5)

        modal=pg.query_selector("#addApiMdl")
        chk("Edit modal opens",modal and modal.is_visible())

        # Check modal title says Edit
        title=pg.query_selector("#addApiMdl .modal-h h3").inner_text()
        chk("Modal title says 'Edit'","Edit" in title,title)

        # Check fields pre-filled
        name_val=pg.input_value("#addApiName")
        chk("Name pre-filled",name_val=="TestEditAPI",name_val)

        ep_val=pg.input_value("#addApiEndpoint")
        chk("Endpoint path pre-filled","test-edit" in ep_val,ep_val)

        method_val=pg.input_value("#addApiMethod")
        chk("Method pre-filled as POST",method_val=="POST",method_val)

        auth_val=pg.input_value("#addApiAuth")
        chk("Auth pre-filled as yes",auth_val=="yes",auth_val)

        # Check body fields loaded in KV rows
        kv_rows=pg.query_selector_all("#addApiKVFields .add-kv-row")
        chk("Body fields loaded in edit modal",len(kv_rows)>=2,f"{len(kv_rows)} rows")

        # Check submit button says Save Changes
        submit_btn=pg.query_selector("#addApiMdl button:last-child")
        btn_text=submit_btn.inner_text() if submit_btn else ""
        chk("Button says 'Save Changes'","Save" in btn_text,btn_text)

        # Change the endpoint path
        pg.fill("#addApiEndpoint","test-edit-updated")
        time.sleep(0.2)

        # Change name
        pg.fill("#addApiName","TestEditAPI Updated")
        time.sleep(0.2)

        # Save
        pg.click("#addApiMdl button:has-text('Save')")
        time.sleep(1)

        # Verify updated
        pg.evaluate("reloadData()")
        time.sleep(0.5)
        pg.fill("#sideSearch","Updated")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("Updated API found with new name",len(visible)>=1)

        if visible:
            visible[0].click()
            time.sleep(0.3)
            url=pg.input_value("#mUrl")
            chk("URL updated with new endpoint path","test-edit-updated" in url,url)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        # ─── TEST 6: Delete endpoint ───
        print("\n[6] Delete endpoint...")
        before_del=int(pg.evaluate("A.length"))

        pg.click("#btnDelEp")
        time.sleep(1)

        after_del=int(pg.evaluate("A.length"))
        chk("Endpoint deleted",after_del==before_del-1,f"{before_del} -> {after_del}")

        # Verify it's gone
        pg.fill("#sideSearch","Updated")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        chk("Deleted API no longer in sidebar",len(visible)==0)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        # Buttons should be hidden now
        chk("Save hidden after delete",not pg.query_selector("#btnSaveEp").is_visible())

        # ─── TEST 7: Save changes on existing collection API ───
        print("\n[7] Modify existing API -> Save...")
        pg.fill("#sideSearch","get gifts")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        if visible:visible[0].click()
        time.sleep(0.3)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        original_url=pg.input_value("#mUrl")

        # Change method to GET
        pg.select_option("#mSel","GET")
        time.sleep(0.2)

        # Save
        pg.click("#btnSaveEp")
        time.sleep(1)

        # Verify method saved
        pg.fill("#sideSearch","get gifts")
        time.sleep(0.5)
        visible=pg.query_selector_all(".ep-row:not(.search-hide)")
        if visible:visible[0].click()
        time.sleep(0.3)
        pg.fill("#sideSearch","")
        time.sleep(0.2)

        saved_method=pg.input_value("#mSel")
        chk("Method change saved",saved_method=="GET",f"method: {saved_method}")

        # Restore to POST
        pg.select_option("#mSel","POST")
        pg.click("#btnSaveEp")
        time.sleep(0.5)

        # Final count
        final=int(pg.evaluate("A.length"))
        chk("Final count = initial",final==initial,f"initial={initial}, final={final}")

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        print("\n  Browser open 8s...")
        time.sleep(8)
        br.close()

if __name__=="__main__":run()
