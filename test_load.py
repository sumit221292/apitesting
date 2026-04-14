"""Playwright HEADED test for Load Testing feature."""
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

        print("\n"+"="*60)
        print("  LOAD TEST FEATURE - FULL TEST")
        print("="*60)

        pg.goto("http://localhost:5555")
        pg.wait_for_selector(".fld",timeout=10000)

        # Login first
        print("\n[1] Login...")
        pg.click("text=Login & Get Token")
        pg.wait_for_function("!document.getElementById('sendBtn').disabled",timeout=15000)
        time.sleep(0.5)
        chk("Login OK","Token Active" in pg.query_selector("#tokSt").inner_text())

        # ─── Switch to Load Test tab ───
        print("\n[2] Load Test tab...")
        pg.click("[data-m='load']")
        time.sleep(0.5)
        chk("Tab 4 visible","on" in pg.query_selector("[data-m='load']").get_attribute("class"))

        # ─── Verify config panel ───
        print("\n[3] Config panel elements...")
        chk("Pattern selector",pg.query_selector("#ltPattern") is not None)
        chk("VUs slider",pg.query_selector("#ltVUs") is not None)
        chk("Duration slider",pg.query_selector("#ltDuration") is not None)
        chk("Ramp-up input",pg.query_selector("#ltRamp") is not None)
        chk("Think time min",pg.query_selector("#ltThinkMin") is not None)
        chk("Think time max",pg.query_selector("#ltThinkMax") is not None)
        chk("Timeout input",pg.query_selector("#ltTimeout") is not None)
        chk("Per-VU login checkbox",pg.query_selector("#ltPerVuLogin") is not None)
        chk("Start button",pg.query_selector("#ltRunBtn") is not None)
        chk("Endpoint list area",pg.query_selector("#ltEpList") is not None)

        # ─── Live stats bar ───
        print("\n[4] Live stats bar...")
        chk("VUs stat",pg.query_selector("#ls-vus") is not None)
        chk("RPS stat",pg.query_selector("#ls-rps") is not None)
        chk("Avg RT stat",pg.query_selector("#ls-avg") is not None)
        chk("P95 stat",pg.query_selector("#ls-p95") is not None)
        chk("Error stat",pg.query_selector("#ls-err") is not None)
        chk("Total stat",pg.query_selector("#ls-total") is not None)
        chk("Elapsed stat",pg.query_selector("#ls-time") is not None)

        # ─── Chart canvas ───
        print("\n[5] Chart...")
        chk("Chart canvas",pg.query_selector("#ltChart") is not None)

        # ─── Select APIs for load test ───
        print("\n[6] Select APIs...")
        pg.click("text=Select Full Backend (20)")
        time.sleep(0.5)
        cnt_text=pg.query_selector("#ltEpCnt").inner_text()
        chk("Full Backend selected",int(cnt_text.strip('()'))>0,cnt_text)

        # ─── Configure load test ───
        print("\n[7] Configure test...")
        # Set 5 VUs, 15 seconds, ramp pattern
        pg.evaluate("document.getElementById('ltVUs').value=5;document.getElementById('ltVUsVal').textContent='5'")
        pg.evaluate("document.getElementById('ltDuration').value=15;document.getElementById('ltDurVal').textContent='15s'")
        pg.fill("#ltRamp","3")
        pg.fill("#ltThinkMin","300")
        pg.fill("#ltThinkMax","800")

        vu_val=pg.evaluate("document.getElementById('ltVUs').value")
        dur_val=pg.evaluate("document.getElementById('ltDuration').value")
        chk("VUs set to 5",vu_val=="5",vu_val)
        chk("Duration set to 15s",dur_val=="15",dur_val)

        # ─── Start load test ───
        print("\n[8] Starting load test (5 VUs, 15s, ramp)...")
        pg.click("#ltRunBtn")
        time.sleep(2)

        chk("Start button hidden",not pg.query_selector("#ltRunBtn").is_visible())
        chk("Stop button visible",pg.query_selector("#ltStopBtn").is_visible())

        # ─── Monitor live metrics ───
        print("\n[9] Monitoring live metrics...")
        for i in range(20):
            time.sleep(2)
            vus=pg.query_selector("#ls-vus").inner_text()
            rps=pg.query_selector("#ls-rps").inner_text()
            avg=pg.query_selector("#ls-avg").inner_text()
            total=pg.query_selector("#ls-total").inner_text()
            elapsed=pg.query_selector("#ls-time").inner_text()
            err=pg.query_selector("#ls-err").inner_text()
            print(f"    [{elapsed}] VUs:{vus} RPS:{rps} Avg:{avg}ms Total:{total} Err:{err}")

            # Check if test done (start button back)
            if pg.query_selector("#ltRunBtn").is_visible():
                break

        time.sleep(1)

        # ─── Verify metrics were collected ───
        print("\n[10] Verify results...")
        total_final=pg.query_selector("#ls-total").inner_text()
        chk("Requests were made",int(total_final)>0,f"{total_final} total requests")
        chk("Load test finished",pg.query_selector("#ltRunBtn").is_visible())

        # ─── Verify chart was drawn ───
        canvas=pg.query_selector("#ltChart")
        chk("Chart canvas exists",canvas is not None)
        # Check if chart has data drawn (canvas not empty)
        has_data=pg.evaluate("document.getElementById('ltChart').getContext('2d').getImageData(100,100,1,1).data[3]>0")
        chk("Chart has drawn data",has_data)

        # ─── Verify summary ───
        print("\n[11] Summary report...")
        summary=pg.query_selector("#ltSummary")
        summary_text=summary.inner_text() if summary else ""
        chk("Summary shows total requests","Requests" in summary_text or "Avg" in summary_text,summary_text[:80])
        chk("Summary shows RPS","RPS" in summary_text)
        chk("Summary shows P95","P95" in summary_text)
        chk("Summary shows P99","P99" in summary_text)
        chk("Summary shows Error Rate","Error" in summary_text)

        # Per-endpoint table
        tbl=pg.query_selector(".lt-tbl")
        chk("Per-endpoint breakdown table",tbl is not None)
        rows=pg.query_selector_all(".lt-tbl tbody tr")
        chk("Endpoint rows in table",len(rows)>0,f"{len(rows)} endpoints")

        # Status distribution
        chk("Status distribution shown","200" in summary_text or "Status" in summary_text)

        # ─── Test different pattern ───
        print("\n[12] Test spike pattern (quick 10s test)...")
        pg.evaluate("document.getElementById('ltPattern').value='spike'")
        pg.evaluate("document.getElementById('ltVUs').value=8;document.getElementById('ltVUsVal').textContent='8'")
        pg.evaluate("document.getElementById('ltDuration').value=10;document.getElementById('ltDurVal').textContent='10s'")

        pg.click("#ltRunBtn")
        time.sleep(1)
        chk("Spike test started",not pg.query_selector("#ltRunBtn").is_visible())

        for i in range(15):
            time.sleep(2)
            if pg.query_selector("#ltRunBtn").is_visible():break
            elapsed=pg.query_selector("#ls-time").inner_text()
            vus=pg.query_selector("#ls-vus").inner_text()
            print(f"    [{elapsed}] VUs:{vus}")
        time.sleep(1)

        total2=pg.query_selector("#ls-total").inner_text()
        chk("Spike test completed",int(total2)>0,f"{total2} requests")

        # ═══ DONE ═══
        print("\n"+"="*60)
        print(f"  RESULTS: {P} PASSED, {F} FAILED")
        print("="*60)
        print("\n  Browser open 10s to inspect...")
        time.sleep(10)
        br.close()

if __name__=="__main__":run()
