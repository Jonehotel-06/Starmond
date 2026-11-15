"""acrawl.py [path...] — log in as owner, load admin pages, report errors. No args = all admin pages.
   Env CLICK=1 also opens the create dialog and first row actions."""
import sys, os, glob, asyncio
from playwright.async_api import async_playwright
BASE='http://localhost:5173'
EMAIL=os.environ.get('EMAIL','owner@starmond.test'); PW=os.environ.get('PW','Owner#Pass2026')
async def login(ctx):
    pg = await ctx.new_page()
    await pg.goto(BASE+'/login.html', wait_until='networkidle')
    await pg.fill('[data-login-form] input[name=email]', EMAIL); await pg.fill('[data-login-form] input[name=password]', PW)
    await pg.click('[data-login-form] button[type=submit]')
    await pg.wait_for_timeout(2500)
    print('after login ->', pg.url.replace(BASE,''))
    await pg.close()
async def main():
    paths = sys.argv[1:] or sorted('/admin/'+os.path.basename(f) for f in glob.glob('/home/user/Starmond/frontend/admin/*.html'))
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={'width':1366,'height':900})
        await login(ctx)
        for path in paths:
            pg = await ctx.new_page(); errs=[]
            pg.on('console', lambda m, e=errs: e.append('console: '+m.text[:300]) if m.type=='error' and 'Failed to load resource' not in m.text else None)
            pg.on('pageerror', lambda x, e=errs: e.append('PAGEERROR: '+str(x)[:400]))
            pg.on('response', lambda r, e=errs: e.append(f'HTTP {r.status} {r.request.method} {r.url.replace(BASE,"")[:140]}') if r.status>=400 else None)
            try:
                await pg.goto(BASE+path, wait_until='networkidle', timeout=20000)
                await pg.wait_for_timeout(500)
            except Exception as x: errs.append('NAV: '+str(x)[:120])
            if os.environ.get('SHOT'): await pg.screenshot(path=f"/tmp/pg-{os.path.basename(path)}.png")
            busy = await pg.locator('[aria-busy="true"]').count()
            rows = await pg.locator('tbody tr').count()
            note=''
            if os.environ.get('CLICK'):
                try:
                    c = pg.locator('[data-create]:visible')
                    if await c.count():
                        await c.first.click(); await pg.wait_for_timeout(900)
                        n = await pg.locator('.dialog [name]').count()
                        note += f' create-dialog fields={n}'
                        if os.environ.get('SHOT'): await pg.screenshot(path=f"/tmp/dlg-{os.path.basename(path)}.png")
                        await pg.keyboard.press('Escape'); await pg.wait_for_timeout(300)
                    acts = pg.locator('tbody tr:first-child [data-row-action], tbody tr:first-child [data-edit]')
                    k = await acts.count(); note += f' row-actions={k}'
                    for i in range(k):
                        a = pg.locator('tbody tr:first-child [data-row-action], tbody tr:first-child [data-edit]').nth(i)
                        lab = (await a.get_attribute('aria-label')) or (await a.get_attribute('data-row-action')) or ''
                        if any(w in lab.lower() for w in ('delete','archive','deactivate','activate','remove','reject','approve','hide','publish')): continue
                        await a.click(); await pg.wait_for_timeout(900)
                        d = await pg.locator('.dialog').count()
                        note += f' [{lab[:22]}:{"dlg" if d else "-"}]'
                        if d and os.environ.get('SHOT'): await pg.screenshot(path=f"/tmp/act{i}-{os.path.basename(path)}.png")
                        if d: await pg.keyboard.press('Escape'); await pg.wait_for_timeout(300)
                except Exception as x: errs.append('CLICK: '+str(x)[:200])
            print(('OK  ' if not errs and not busy else 'ERR ')+path+f'  rows={rows}'+(f'  [still busy x{busy}]' if busy else '')+note)
            for e in dict.fromkeys(errs): print('     '+e)
            await pg.close()
        await b.close()
asyncio.run(main())
