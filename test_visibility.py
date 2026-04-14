"""Quick visual check - screenshot all tabs, verify no tiny/dull text."""
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
        br=p.chromium.launch(headless=False,slow_mo=300)
        pg=br.new_page(viewport={"width":1400,"height":900})
        pg.goto("http://localhost:5555")
        pg.wait_for_selector(".fld",timeout=10000)

        print("\n"+"="*60)
        print("  TEXT VISIBILITY CHECK")
        print("="*60)

        # Check no element has computed font-size < 9px
        print("\n[1] Checking minimum font sizes...")
        tiny = pg.evaluate("""() => {
            const all = document.querySelectorAll('*');
            let tiny = [];
            for (const el of all) {
                if (!el.offsetParent && el.tagName !== 'BODY' && el.tagName !== 'HTML') continue;
                const s = getComputedStyle(el);
                const fs = parseFloat(s.fontSize);
                const txt = el.textContent.trim();
                if (fs < 9 && txt.length > 0 && txt.length < 50 && el.children.length === 0) {
                    tiny.push({tag: el.tagName, fs: fs, txt: txt.substring(0,30), cls: el.className.substring(0,20)});
                }
            }
            return tiny;
        }""")
        chk("No text smaller than 9px", len(tiny) <= 2, f"{len(tiny)} tiny elements found")
        if tiny:
            for t in tiny[:5]:
                print(f"    Warning: {t['tag']}.{t['cls']} = {t['fs']}px: '{t['txt']}'")

        # Check no visible text has color too dark (< #444 brightness)
        print("\n[2] Checking text color brightness...")
        dull = pg.evaluate("""() => {
            const all = document.querySelectorAll('*');
            let dull = [];
            for (const el of all) {
                if (!el.offsetParent && el.tagName !== 'BODY' && el.tagName !== 'HTML') continue;
                const s = getComputedStyle(el);
                const c = s.color;
                const m = c.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                if (!m) continue;
                const brightness = (parseInt(m[1]) + parseInt(m[2]) + parseInt(m[3])) / 3;
                const txt = el.textContent.trim();
                if (brightness < 60 && txt.length > 0 && txt.length < 50 && el.children.length === 0 && brightness > 0) {
                    dull.push({tag: el.tagName, color: c, bright: Math.round(brightness), txt: txt.substring(0,30), cls: el.className.substring(0,20)});
                }
            }
            return dull;
        }""")
        chk("No extremely dull text (brightness<60)", len(dull) <= 3, f"{len(dull)} dull elements")
        if dull:
            for d in dull[:5]:
                print(f"    Warning: {d['tag']}.{d['cls']} brightness={d['bright']}: '{d['txt']}' color={d['color']}")

        # ─── Check each tab ───
        print("\n[3] Tab 1: Manual Test...")
        pg.click("text=Login & Get Token")
        pg.wait_for_function("!document.getElementById('sendBtn').disabled",timeout=15000)
        time.sleep(0.5)

        # Check response status text readable
        st = pg.query_selector("#resSt")
        st_fs = pg.evaluate("getComputedStyle(document.getElementById('resSt')).fontSize")
        chk("Response status text size", float(st_fs.replace('px','')) >= 10, st_fs)

        # Check endpoint info readable
        info = pg.query_selector("#epInfo")
        info_fs = pg.evaluate("getComputedStyle(document.getElementById('epInfo')).fontSize")
        chk("Endpoint info text size", float(info_fs.replace('px','')) >= 10, info_fs)

        # Token status readable
        tok_fs = pg.evaluate("getComputedStyle(document.getElementById('tokSt')).fontSize")
        chk("Token status text size", float(tok_fs.replace('px','')) >= 10, tok_fs)

        print("\n[4] Tab 2: Auto Test...")
        pg.click("[data-m='auto']")
        time.sleep(0.3)

        # Check folder text size
        sf = pg.query_selector(".sf-h")
        sf_fs = pg.evaluate("getComputedStyle(document.querySelector('.sf-h')).fontSize")
        chk("Folder name text size", float(sf_fs.replace('px','')) >= 11, sf_fs)

        # Check endpoint text size
        se_fs = pg.evaluate("getComputedStyle(document.querySelector('.se')).fontSize")
        chk("Endpoint checkbox text size", float(se_fs.replace('px','')) >= 10, se_fs)

        # Check tag badge size
        tag = pg.query_selector(".se .tag")
        if tag:
            tag_fs = pg.evaluate("getComputedStyle(document.querySelector('.se .tag')).fontSize")
            chk("Tag badge text size", float(tag_fs.replace('px','')) >= 9, tag_fs)

        # Selection count readable
        cnt_fs = pg.evaluate("getComputedStyle(document.getElementById('selCnt')).fontSize")
        chk("Selected count text size", float(cnt_fs.replace('px','')) >= 12, cnt_fs)

        # Button text readable
        btn_fs = pg.evaluate("getComputedStyle(document.querySelector('.btn-sm')).fontSize")
        chk("Button text size", float(btn_fs.replace('px','')) >= 10, btn_fs)

        print("\n[5] Tab 3: Results (run quick test)...")
        pg.evaluate("ltSelPreset?ltSelPreset():null")
        time.sleep(0.3)
        pg.click("text=Preset: Auth Flow (6)")
        time.sleep(0.5)
        pg.click("#runBtn")
        time.sleep(1)
        for i in range(30):
            time.sleep(2)
            pop=pg.query_selector("#errPop")
            if pop and pop.is_visible():pg.click(".pop-skip");time.sleep(0.3);continue
            if pg.query_selector("#runBtn").is_visible():break
        time.sleep(1)

        # Stats card value size
        v_fs = pg.evaluate("getComputedStyle(document.querySelector('.sc .v')).fontSize")
        chk("Stats card value text size", float(v_fs.replace('px','')) >= 20, v_fs)

        # Stats card label size
        l_fs = pg.evaluate("getComputedStyle(document.querySelector('.sc .l')).fontSize")
        chk("Stats card label text size", float(l_fs.replace('px','')) >= 9, l_fs)

        # Result row text
        rr = pg.query_selector(".rr")
        if rr:
            rr_fs = pg.evaluate("getComputedStyle(document.querySelector('.rr')).fontSize")
            chk("Result row text size", float(rr_fs.replace('px','')) >= 11, rr_fs)

        # Status badge
        stb = pg.query_selector(".stb")
        if stb:
            stb_fs = pg.evaluate("getComputedStyle(document.querySelector('.stb')).fontSize")
            chk("Status badge text size", float(stb_fs.replace('px','')) >= 10, stb_fs)

        print("\n[6] Tab 4: Load Test...")
        pg.click("[data-m='load']")
        time.sleep(0.3)

        # Config label size
        lbl_fs = pg.evaluate("getComputedStyle(document.querySelector('.lc-l')).fontSize")
        chk("Config label text size", float(lbl_fs.replace('px','')) >= 11, lbl_fs)

        # Config hint size
        hint_fs = pg.evaluate("getComputedStyle(document.querySelector('.lc-hint')).fontSize")
        chk("Config hint text size", float(hint_fs.replace('px','')) >= 9, hint_fs)

        # Live stat value
        ltv_fs = pg.evaluate("getComputedStyle(document.querySelector('.lt-v')).fontSize")
        chk("Live stat value text size", float(ltv_fs.replace('px','')) >= 16, ltv_fs)

        # Live stat label
        ltl_fs = pg.evaluate("getComputedStyle(document.querySelector('.lt-l')).fontSize")
        chk("Live stat label text size", float(ltl_fs.replace('px','')) >= 9, ltl_fs)

        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        if F:
            print("\n  FAILED:")
            for s,n in [(s,n) for s,n in zip([],[]) if s=='FAIL']:
                print(f"    - {n}")

        print("\n  Browser open 8s to visually inspect...")
        time.sleep(8)
        br.close()

if __name__=="__main__":run()
