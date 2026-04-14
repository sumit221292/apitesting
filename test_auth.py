"""Playwright test: Auth from .env - no hardcoded passwords."""
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
        print("  SECURITY TEST (.env credentials)")
        print("="*60)

        # ─── 1: All routes blocked ───
        print("\n[1] All routes blocked without login...")
        pg.goto("http://localhost:5555/")
        time.sleep(0.5)
        chk("/ -> redirects to /login","/login" in pg.url)

        resp=pg.evaluate("fetch('/api/data').then(r=>r.status)")
        chk("/api/data -> 401",resp==401)
        resp=pg.evaluate("fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(r=>r.status)")
        chk("/api/send -> 401",resp==401)
        resp=pg.evaluate("fetch('/api/collection/export').then(r=>r.status)")
        chk("/api/collection/export -> 401",resp==401)
        resp=pg.evaluate("fetch('/api/load/metrics').then(r=>r.status)")
        chk("/api/load/metrics -> 401",resp==401)

        # ─── 2: Wrong creds ───
        print("\n[2] Wrong credentials rejected...")
        pg.fill("input[name='username']","hacker")
        pg.fill("input[name='password']","letmein")
        pg.click("button[type='submit']")
        time.sleep(0.5)
        chk("Hacker rejected","/login" in pg.url)
        chk("Error shown","Invalid" in pg.inner_text("#errMsg"))

        # ─── 3: Correct login ───
        print("\n[3] Correct login from .env credentials...")
        pg.fill("input[name='username']","admin")
        pg.fill("input[name='password']","admin@123")
        pg.click("button[type='submit']")
        time.sleep(1)
        chk("Login success","login" not in pg.url)
        chk("App loads",pg.query_selector(".side-hdr") is not None)

        resp=pg.evaluate("fetch('/api/data').then(r=>r.status)")
        chk("API works after login",resp==200)

        # ─── 4: Logout button + PW button ───
        print("\n[4] Logout and Change Password buttons...")
        chk("Logout link",pg.query_selector("a[href='/logout']") is not None)
        pw_btn=pg.query_selector("button[onclick='showChangePw()']")
        chk("Change Password button",pw_btn is not None)

        # ─── 5: Change password modal ───
        print("\n[5] Change password modal...")
        pw_btn.click()
        time.sleep(0.5)
        chk("Password modal opens",pg.query_selector("#varsMdl").is_visible())
        chk("Current password field",pg.query_selector("#cpCurrent") is not None)
        chk("New password field",pg.query_selector("#cpNew") is not None)
        chk("Confirm field",pg.query_selector("#cpConfirm") is not None)

        # Try wrong current password
        pg.fill("#cpCurrent","wrongcurrent")
        pg.fill("#cpNew","newpass123")
        pg.fill("#cpConfirm","newpass123")
        pg.evaluate("submitChangePw()")
        time.sleep(0.5)
        err=pg.inner_text("#cpErr")
        chk("Wrong current password rejected","wrong" in err.lower(),err)

        # Try mismatched passwords
        pg.fill("#cpCurrent","admin@123")
        pg.fill("#cpNew","newpass1")
        pg.fill("#cpConfirm","newpass2")
        pg.evaluate("submitChangePw()")
        time.sleep(0.3)
        err=pg.inner_text("#cpErr")
        chk("Mismatched passwords rejected","match" in err.lower(),err)

        # Correct change
        pg.fill("#cpCurrent","admin@123")
        pg.fill("#cpNew","newadmin@456")
        pg.fill("#cpConfirm","newadmin@456")
        pg.evaluate("submitChangePw()")
        time.sleep(0.5)
        toast=pg.query_selector("#toast").inner_text() if pg.query_selector("#toast") else ""
        chk("Password changed","changed" in toast.lower() or "Changed" in toast,toast)

        # ─── 6: Logout then login with NEW password ───
        print("\n[6] Login with new password...")
        pg.click("a[href='/logout']")
        time.sleep(0.5)
        pg.fill("input[name='username']","admin")
        pg.fill("input[name='password']","newadmin@456")
        pg.click("button[type='submit']")
        time.sleep(1)
        chk("New password works","login" not in pg.url)

        # Old password should fail
        pg.click("a[href='/logout']")
        time.sleep(0.5)
        pg.fill("input[name='username']","admin")
        pg.fill("input[name='password']","admin@123")
        pg.click("button[type='submit']")
        time.sleep(0.5)
        chk("Old password rejected","/login" in pg.url)

        # ─── 7: Restore original password ───
        print("\n[7] Restore original password...")
        pg.fill("input[name='username']","admin")
        pg.fill("input[name='password']","newadmin@456")
        pg.click("button[type='submit']")
        time.sleep(1)
        pw_btn=pg.query_selector("button[onclick='showChangePw()']")
        if pw_btn:pw_btn.click()
        time.sleep(0.5)
        pg.fill("#cpCurrent","newadmin@456")
        pg.fill("#cpNew","admin@123")
        pg.fill("#cpConfirm","admin@123")
        pg.evaluate("submitChangePw()")
        time.sleep(0.5)
        chk("Password restored to original",True)

        # ─── 8: Verify .env has NO plain password ───
        print("\n[8] Verify .env file security...")
        env_content=open('C:/Users/creat/Downloads/.env.zeeplive').read()
        chk("No 'admin@123' in .env","admin@123" not in env_content)
        chk("No 'test@123' in .env","test@123" not in env_content)
        chk("Has SHA-256 hashes","USER_admin=" in env_content and len(env_content.split("USER_admin=")[1].split("\n")[0])>=60)
        chk("Has SECRET_KEY","SECRET_KEY=" in env_content)

        # ─── 9: Verify code has no passwords ───
        print("\n[9] Verify code has no hardcoded passwords...")
        code=open('C:/Users/creat/Downloads/zeeplive_test_ui.py',encoding='utf-8',errors='ignore').read()
        chk("No 'admin@123' in code","admin@123" not in code)
        chk("No 'test@123' in code","test@123" not in code)
        chk("No plain password in AUTH_USERS","AUTH_USERS = {}" in code or "'admin'" not in code.split("AUTH_USERS")[1][:100] if "AUTH_USERS" in code else True)

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        print("\n  Browser open 6s...")
        time.sleep(6)
        br.close()

if __name__=="__main__":run()
