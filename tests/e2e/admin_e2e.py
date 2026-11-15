"""Functional admin test through the real UI: create/edit/delete with the forms, checks API results."""
import asyncio, json, sys, struct, zlib
from playwright.async_api import async_playwright
BASE='http://localhost:5173'; R=[]
def png():
    w=h=64; raw=b''.join(b'\x00'+bytes([120,60,200])*w for _ in range(h))
    def ch(t,d): c=struct.pack('>I',len(d))+t+d; return c+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+ch(b'IDAT',zlib.compress(raw))+ch(b'IEND',b'')
open('/tmp/t.png','wb').write(png())
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={'width':1366,'height':900}); pg = await ctx.new_page()
        errs=[]
        pg.on('pageerror', lambda x: errs.append('PAGEERROR '+str(x)[:300]))
        async def onresp(r):
            if r.status>=400 and '/api/' in r.url:
                try: t=(await r.text())[:260]
                except Exception: t=''
                errs.append(f'HTTP {r.status} {r.request.method} {r.url.replace(BASE,"")[:90]} {t}')
        pg.on('response', onresp)
        async def step(name, coro):
            n=len(errs)
            try: await coro; ok=len(errs)==n; R.append((ok,name, errs[n:]))
            except Exception as x: R.append((False,name,[str(x)[:300]]+errs[n:]))
            for d in range(3):
                if await pg.locator('.dialog').count(): await pg.keyboard.press('Escape'); await pg.wait_for_timeout(250)
        async def go(path): await pg.goto(BASE+path, wait_until='networkidle'); await pg.wait_for_timeout(400)
        async def api(path):
            return await pg.evaluate("async (p)=>{const r=await fetch('/api'+p,{credentials:'include'});return r.json()}", path)
        async def save(expect_close=True):
            await pg.click('.dialog [data-save-entity]'); await pg.wait_for_timeout(1500)
            if expect_close and await pg.locator('.dialog').count():
                msg = await pg.locator('.dialog [data-form-error]:visible, .dialog .field__error:visible').all_inner_texts()
                raise Exception('dialog still open: '+' | '.join(m for m in msg if m.strip())[:250])
        async def fill(name, val): await pg.fill(f'.dialog [name="{name}"]', val)

        await go('/login.html'); await pg.fill('[data-login-form] [name=email]','owner@starmond.test'); await pg.fill('[data-login-form] [name=password]','Owner#Pass2026')
        await pg.click('[data-login-form] button[type=submit]'); await pg.wait_for_timeout(2500)

        async def category():
            await go('/admin/categories.html'); await pg.click('[data-create]'); await pg.wait_for_timeout(600)
            await fill('name','E2E Garden'); await save()
            assert 'E2E Garden' in await pg.inner_text('tbody')
        await step('category create', category())
        async def product():
            await go('/admin/products.html'); await pg.click('[data-create]'); await pg.wait_for_timeout(900)
            await fill('name','E2E Hose 20m'); await fill('sku','E2E-HOSE'); await fill('regular_price','9500')
            await pg.select_option('.dialog [name="category"]', label='E2E Garden')
            if await pg.locator('.dialog [name="stock_quantity"]').count(): await fill('stock_quantity','12')
            await save()
            await pg.fill('[data-module-search]','E2E-HOSE'); await pg.wait_for_timeout(1200)
            assert 'E2E Hose 20m' in await pg.inner_text('tbody')
        await step('product create', product())
        async def product_edit():
            await pg.click('tbody tr:first-child [data-edit]'); await pg.wait_for_timeout(900)
            await fill('sale_price','8000'); await save()
            d=await api('/products/admin/?search=E2E-HOSE'); r=d['results'][0]
            assert str(r.get('sale_price')).startswith('8000'), r.get('sale_price')
        await step('product edit sale price', product_edit())
        async def product_images():
            await pg.click('tbody tr:first-child [aria-label^="Manage images"]'); await pg.wait_for_timeout(900)
            await pg.set_input_files('.dialog input[type=file]','/tmp/t.png')
            alt = pg.locator('.dialog [name="alt_text"]')
            if await alt.count(): await alt.fill('Green garden hose')
            await pg.click('.dialog form[data-upload] button[type=submit]'); await pg.wait_for_timeout(2500)
            n = await pg.locator('.dialog .media-card').count(); assert n==1, f'media cards={n}'
        await step('product image upload', product_images())
        async def product_var():
            await pg.click('tbody tr:first-child [aria-label^="Manage variations"]'); await pg.wait_for_timeout(900)
            await pg.click('.dialog >> text=Add variation'); await pg.wait_for_timeout(700)
            top='.dialog-backdrop:last-of-type .dialog, .dialog:last-of-type'
            await pg.locator('.dialog [name="sku"]').last.fill('E2E-HOSE-30')
            await pg.locator('.dialog [name="name"]').last.fill('30 metres')
            await pg.locator('.dialog [name="options"]').last.fill('Length: 30m')
            if await pg.locator('.dialog [name="stock_quantity"]').count(): await pg.locator('.dialog [name="stock_quantity"]').last.fill('5')
            await pg.locator('.dialog button:has-text("Add variation")').last.click(); await pg.wait_for_timeout(2000)
            d=await api('/products/admin/?search=E2E-HOSE'); r=d['results'][0]
            det=await api(f"/products/admin/{r['id']}/"); vs=det.get('data',det).get('variations',[])
            assert any(v['sku']=='E2E-HOSE-30' for v in vs), vs
        await step('product variation add', product_var())
        async def inventory():
            await go('/admin/inventory.html'); await pg.fill('[data-module-search]','E2E-HOSE'); await pg.wait_for_timeout(1200)
            await pg.click('tbody tr:first-child [aria-label^="Receive stock"]'); await pg.wait_for_timeout(600)
            await fill('quantity','8'); await pg.locator('.dialog button[type=submit], .dialog [data-save]').last.click(); await pg.wait_for_timeout(1500)
            assert not await pg.locator('.dialog').count(), 'receive dialog still open: '+' '.join(await pg.locator('.dialog [role=alert]:visible').all_inner_texts())
        await step('inventory receive', inventory())
        async def zone():
            await go('/admin/shipping-zones.html'); await pg.click('[data-create]'); await pg.wait_for_timeout(700)
            await fill('name','E2E Zone'); await pg.locator('.dialog .checklist input[type=checkbox]').nth(3).check(); await save()
            assert 'E2E Zone' in await pg.inner_text('tbody')
        await step('shipping zone create', zone())
        async def method():
            await go('/admin/delivery.html'); await pg.click('[data-create]'); await pg.wait_for_timeout(900)
            await fill('name','E2E Courier'); await fill('fee','2500'); await fill('min_days','1'); await fill('max_days','3'); await save()
            assert 'E2E Courier' in await pg.inner_text('tbody')
        await step('delivery method create', method())
        async def promo():
            await go('/admin/promotions.html'); await pg.click('[data-create]'); await pg.wait_for_timeout(900)
            names = await pg.eval_on_selector_all('.dialog [name]','els=>els.map(e=>e.name+":"+e.type+(e.required?"*":""))'); print('promo fields', names)
            await fill('name','E2E Ten'); await fill('code','E2ETEN'); await fill('value','10'); await save()
            assert 'E2ETEN' in await pg.inner_text('tbody')
        await step('promotion create', promo())
        async def role():
            await go('/admin/roles.html'); await pg.click('[data-create]'); await pg.wait_for_timeout(1200)
            await fill('name','E2E Stock Clerk'); await pg.check('.dialog .checklist label:has-text("Inventory View") input'); await pg.check('.dialog .checklist label:has-text("Dashboard View") input'); await save()
            assert 'E2E Stock Clerk' in await pg.inner_text('tbody')
        await step('role create', role())
        async def staff():
            await go('/admin/staff.html'); await pg.click('[data-create]'); await pg.wait_for_timeout(1200)
            await fill('email','clerk@starmond.test'); await fill('full_name','Clara Clerk'); await pg.select_option('.dialog [name="role"]', label='E2E Stock Clerk'); await fill('temporary_password','Clerk#Pass2026x'); await save()
            assert 'clerk@starmond.test' in await pg.inner_text('tbody')
        await step('staff create', staff())
        async def page():
            await go('/admin/content.html'); await pg.click('tbody tr:first-child [data-edit]'); await pg.wait_for_timeout(800)
            await fill('excerpt','Edited by E2E.'); await save()
            d=await api('/cms/pages/about-us/'); assert d['data']['excerpt']=='Edited by E2E.', d['data']['excerpt']
        await step('cms page edit', page())
        async def banner():
            await go('/admin/banners.html'); await pg.click('[data-create]'); await pg.wait_for_timeout(800)
            await fill('title','E2E Sale'); await pg.set_input_files('.dialog [data-media-key-file]','/tmp/t.png'); await pg.wait_for_timeout(2500)
            k=await pg.input_value('.dialog [name="image_key"]'); assert k, 'no key after upload: '+await pg.inner_text('.dialog [data-media-key-status]')
            await save(); assert 'E2E Sale' in await pg.inner_text('tbody')
        await step('banner create with image upload', banner())
        async def settings():
            await go('/admin/settings.html'); await pg.fill('[name="contact_phone"]','+234 800 000 0000'); await pg.fill('[name="social_links.instagram"]','https://instagram.com/starmond')
            await pg.click('[data-settings-form] button[type=submit]'); await pg.wait_for_timeout(1500)
            d=await api('/cms/admin/settings/'); assert d['data']['contact_phone']=='+234 800 000 0000' and d['data']['social_links']['instagram'].endswith('starmond') and 'facebook' in d['data']['social_links'], d['data']
        await step('business settings save', settings())
        async def hero():
            await go('/admin/homepage.html'); await pg.fill('[name="homepage_hero.cta_url"]','/shop.html'); await pg.click('[data-settings-form] button[type=submit]'); await pg.wait_for_timeout(1500)
            d=await api('/cms/admin/settings/'); assert d['data']['homepage_hero']['cta_url']=='/shop.html' and d['data']['homepage_hero']['title'], d['data']['homepage_hero']
        await step('homepage hero save', hero())
        async def seo():
            await go('/admin/seo.html'); await pg.fill('[name="homepage_seo_description"]','Shop Starmond.'); await pg.click('[data-settings-form] button[type=submit]'); await pg.wait_for_timeout(1500)
            d=await api('/seo/settings/'); assert d['data']['homepage_seo_description']=='Shop Starmond.' and d['data']['enable_prerender'] is True, d['data']
        await step('seo settings save', seo())
        async def media():
            await go('/admin/media.html'); n=await pg.locator('.media-tile').count(); assert n>=1, f'tiles={n}'
        await step('media library lists uploads', media())
        async def reports():
            await go('/admin/reports.html')
            async with pg.expect_download(timeout=8000) as dl: await pg.click('[data-export="csv"]')
            f=await dl.value; assert f.suggested_filename.endswith('.csv'), f.suggested_filename
        await step('report CSV download', reports())
        async def export():
            await go('/admin/products.html')
            async with pg.expect_download(timeout=8000) as dl: await pg.click('[data-module-export], [data-export]')
            f=await dl.value; assert f.suggested_filename.endswith('.csv')
        await step('products CSV export', export())
        await b.close()
    for ok,name,e in R:
        print(('PASS ' if ok else 'FAIL ')+name)
        for x in e: print('      '+x)
asyncio.run(main())
