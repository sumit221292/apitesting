"""Playwright test: Verify load test explanations and tooltips."""
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
        print("  LOAD TEST EXPLANATIONS TEST")
        print("="*60)

        # Login
        pg.click("text=Login & Get Token")
        pg.wait_for_function("!document.getElementById('sendBtn').disabled",timeout=15000)
        time.sleep(0.5)

        # Go to Load Test
        pg.click("[data-m='load']")
        time.sleep(0.5)

        # ─── TEST 1: Live stats bar tooltips ───
        print("\n[1] Live stats bar has ? tooltips...")
        stats=pg.query_selector_all("#ltStats .lc-q")
        chk("7 tooltip icons in stats bar",len(stats)==7,f"{len(stats)} found")

        # Check each has meaningful tooltip
        tooltips=[]
        for s in stats:
            t=s.get_attribute("title") or ""
            tooltips.append(t)
        chk("VUs tooltip has explanation",any("user" in t.lower() or "vu" in t.lower() for t in tooltips))
        chk("RPS tooltip has explanation",any("second" in t.lower() or "request" in t.lower() for t in tooltips))
        chk("Avg RT tooltip has explanation",any("response" in t.lower() or "millisecond" in t.lower() for t in tooltips))
        chk("P95 tooltip has explanation",any("95" in t or "percentile" in t.lower() for t in tooltips))
        chk("Error tooltip has explanation",any("error" in t.lower() or "fail" in t.lower() for t in tooltips))

        # ─── TEST 2: Run quick load test ───
        print("\n[2] Run load test (3 VUs, 15s, ramp)...")
        pg.evaluate("ltSelPreset()")
        time.sleep(0.5)
        pg.evaluate("document.getElementById('ltVUs').value=3;document.getElementById('ltVUsVal').textContent='3'")
        pg.evaluate("document.getElementById('ltDuration').value=15;document.getElementById('ltDurVal').textContent='15s'")
        pg.click("#ltRunBtn")
        time.sleep(1)

        for i in range(20):
            time.sleep(2)
            if pg.query_selector("#ltRunBtn").is_visible():break
        time.sleep(1)

        # ─── TEST 3: Summary cards have tooltips ───
        print("\n[3] Summary cards have ? tooltips...")
        summary_qs=pg.query_selector_all("#ltSummary .lc-q")
        chk("Summary cards have tooltip icons",len(summary_qs)>=6,f"{len(summary_qs)} found")

        # Check summary card titles
        summary_stats=pg.query_selector_all("#ltSummary .lt-stat")
        has_title=sum(1 for s in summary_stats if s.get_attribute("title"))
        chk("Summary cards have title tooltips",has_title>=4,f"{has_title} have titles")

        # ─── TEST 4: Status Distribution labels ───
        print("\n[4] Status Distribution has labels...")
        summary_text=pg.inner_text("#ltSummary")
        chk("Shows 'Status Distribution'","Status Distribution" in summary_text)
        chk("Shows status code labels","OK" in summary_text or "Server Error" in summary_text or "Timeout" in summary_text or "Rate Limited" in summary_text,summary_text[:200])
        chk("Shows explanation text","server ne kaise respond" in summary_text.lower() or "respond" in summary_text.lower())

        # ─── TEST 5: Per-endpoint table has tooltips ───
        print("\n[5] Per-endpoint table headers have tooltips...")
        ths=pg.query_selector_all(".lt-tbl th")
        chk("Table headers exist",len(ths)>=7,f"{len(ths)} columns")

        th_titles=sum(1 for th in ths if th.get_attribute("title"))
        chk("Table headers have title tooltips",th_titles>=5,f"{th_titles} have titles")

        # Check P50 and P95 have ? icons
        th_text=pg.inner_text(".lt-tbl thead")
        chk("P50 column exists","P50" in th_text)
        chk("P95 column exists","P95" in th_text)

        table_qs=pg.query_selector_all(".lt-tbl .lc-q")
        chk("P50/P95 have ? tooltips in table",len(table_qs)>=2,f"{len(table_qs)} tooltips")

        # ─── TEST 6: Performance summary hint ───
        print("\n[6] Performance summary hint...")
        chk("Slowest endpoint highlighted","Slowest" in summary_text,summary_text[summary_text.find("Slowest"):summary_text.find("Slowest")+80] if "Slowest" in summary_text else "not found")
        chk("Fastest endpoint highlighted","Fastest" in summary_text)
        chk("Optimization suggestion","optimize" in summary_text.lower() or "theek" in summary_text.lower())

        # ─── TEST 7: Color coding in table ───
        print("\n[7] Color coding in table...")
        # Check that avg times have color
        tds=pg.query_selector_all(".lt-tbl td")
        colored=sum(1 for td in tds if td.get_attribute("style") and "color:" in (td.get_attribute("style") or ""))
        chk("Table cells have color coding",colored>0,f"{colored} colored cells")

        # ─── TEST 8: Chart legend ───
        print("\n[8] Chart legend...")
        chart_area=pg.inner_text("body")
        chk("Chart shows RPS legend","RPS" in chart_area)
        chk("Chart shows Avg RT legend","Avg RT" in chart_area)
        chk("Chart shows Errors legend","Errors" in chart_area)
        chk("Chart shows VUs legend","VUs" in chart_area)

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        print("\n  Browser open 10s to inspect tooltips (hover over ? icons)...")
        time.sleep(10)
        br.close()

if __name__=="__main__":run()
