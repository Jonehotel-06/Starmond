"""crawl.py path [path...] — load each page, report console errors / failed requests / page errors."""
import sys, asyncio
from playwright.async_api import async_playwright
BASE='http://localhost:5173'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={'width':1280,'height':900})
        for path in sys.argv[1:]:
            pg = await ctx.new_page(); errs=[]
            pg.on('console', lambda m, e=errs: e.append('console: '+m.text[:220]) if m.type=='error' and 'Failed to load resource' not in m.text else None)
            pg.on('pageerror', lambda x, e=errs: e.append('PAGEERROR: '+str(x)[:300]))
            pg.on('response', lambda r, e=errs: e.append(f'HTTP {r.status} {r.request.method} {r.url.replace(BASE,"")[:110]}') if r.status>=400 else None)
            try:
                await pg.goto(BASE+path, wait_until='networkidle', timeout=20000)
                await pg.wait_for_timeout(400)
            except Exception as x: errs.append('NAV: '+str(x)[:120])
            busy = await pg.locator('[aria-busy="true"]').count()
            print(('OK  ' if not errs and not busy else 'ERR ')+path+(f'  [still busy x{busy}]' if busy else ''))
            for e in dict.fromkeys(errs): print('     '+e)
            await pg.close()
        await b.close()
asyncio.run(main())
