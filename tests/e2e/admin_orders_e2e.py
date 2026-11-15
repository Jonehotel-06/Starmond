import asyncio
from playwright.async_api import async_playwright
BASE='http://localhost:5173'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={'width':1366,'height':900}); pg = await ctx.new_page()
        pg.on('pageerror', lambda x: print('PAGEERROR', str(x)[:300]))
        async def onresp(r):
            if r.status>=400 and '/api/' in r.url: print('HTTP', r.status, r.request.method, r.url[-70:], (await r.text())[:300])
        pg.on('response', onresp)
        async def api(path): return await pg.evaluate("async (p)=>{const r=await fetch('/api'+p,{credentials:'include'});return r.json()}", path)
        await pg.goto(BASE+'/login.html', wait_until='networkidle'); await pg.fill('[data-login-form] [name=email]','owner@starmond.test'); await pg.fill('[data-login-form] [name=password]','Owner#Pass2026')
        await pg.click('[data-login-form] button[type=submit]'); await pg.wait_for_timeout(2500)
        await pg.goto(BASE+'/admin/orders.html?payment_status=paid', wait_until='networkidle'); await pg.wait_for_timeout(600)
        rows=await pg.locator('tbody tr').count(); ref=(await pg.inner_text('tbody tr:first-child')).split()[0]; print('paid rows', rows, ref)
        # status update
        await pg.click('tbody tr:first-child [aria-label^="Update status"]'); await pg.wait_for_timeout(700)
        print('status fields', await pg.eval_on_selector_all('.dialog [name]','els=>els.map(e=>e.name+":"+e.type)'))
        await pg.select_option('.dialog [name=status]','processing'); await pg.fill('.dialog [name=note]','Picked for packing')
        await pg.locator('.dialog button[type=submit], .dialog [data-save]').last.click(); await pg.wait_for_timeout(1800)
        print('dialog open after save:', await pg.locator('.dialog').count(), [t for t in await pg.locator('.dialog [role=alert]:visible').all_inner_texts() if t.strip()])
        d=await api(f'/orders/admin/{ref}/'); o=d.get('data',d); print('status now', o['status'], 'history', len(o.get('status_history',[])))
        # detail dialog + internal note
        await pg.click('tbody tr:first-child [aria-label^="View order"]'); await pg.wait_for_timeout(1200)
        await pg.screenshot(path='/tmp/order-dlg.png')
        note=pg.locator('.dialog textarea[name=note]')
        if await note.count():
            await note.fill('Customer called to confirm address.'); await pg.locator('.dialog form:has(textarea[name=note]) button[type=submit]').click(); await pg.wait_for_timeout(1500)
            d=await api(f'/orders/admin/{ref}/'); o=d.get('data',d); print('notes', str(o.get('internal_notes'))[:120])
        else: print('NO note form')
        await pg.keyboard.press('Escape'); await pg.wait_for_timeout(400)
        # receipt
        try:
            async with ctx.expect_page(timeout=6000) as np: await pg.click('tbody tr:first-child [aria-label^="Print receipt"]')
            rp=await np.value; await rp.wait_for_timeout(1200); print('receipt:', (await rp.inner_text('body'))[:260].replace('\n',' | ')); await rp.screenshot(path='/tmp/receipt.png')
        except Exception as x: print('RECEIPT FAIL', str(x)[:200])
        await b.close()
asyncio.run(main())
