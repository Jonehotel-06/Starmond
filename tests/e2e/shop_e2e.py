"""Customer journey through the real UI against the local stack + mock Paystack."""
import asyncio, sys, time, os
from playwright.async_api import async_playwright
BASE='http://localhost:5173'; R=[]; U=str(int(time.time()))[-6:]
EMAIL=f'ada{U}@example.test'; PW='Shopper#Pass2026'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); ctx = await b.new_context(viewport={'width':1366,'height':900}); pg = await ctx.new_page()
        errs=[]
        pg.on('pageerror', lambda x: errs.append('PAGEERROR '+str(x)[:300]))
        pg.on('console', lambda m: errs.append('console: '+m.text[:250]) if m.type=='error' and 'Failed to load resource' not in m.text else None)
        async def onresp(r):
            if r.status>=400 and '/api/' in r.url and not (r.status==403 and r.url.endswith('/auth/me/')):
                try: t=(await r.text())[:260]
                except Exception: t=''
                errs.append(f'HTTP {r.status} {r.request.method} {r.url.replace(BASE,"")[:90]} {t}')
        pg.on('response', onresp)
        async def step(name, coro):
            n=len(errs)
            try: await coro; R.append((len(errs)==n,name, errs[n:]))
            except Exception as x:
                R.append((False,name,[str(x)[:400]]+errs[n:])); await pg.screenshot(path=f"/tmp/fail-{name.replace(' ','_')}.png")
        async def go(path): await pg.goto(BASE+path, wait_until='networkidle'); await pg.wait_for_timeout(500)
        async def api(path): return await pg.evaluate("async (p)=>{const r=await fetch('/api'+p,{credentials:'include'});return r.json()}", path)
        st={}
        async def register():
            await go('/register.html'); f='[data-register-form] '
            await pg.fill(f+'[name=full_name]','Ada Shopper'); await pg.fill(f+'[name=email]',EMAIL); await pg.fill(f+'[name=phone]','08031234567')
            await pg.fill(f+'[name=password]',PW); await pg.fill(f+'[name=password_confirm]',PW)
            if await pg.locator(f+'[name=accept_terms]').count(): await pg.check(f+'[name=accept_terms]')
            await pg.click(f+'button[type=submit]'); await pg.wait_for_timeout(2500)
            st['after_register']=pg.url.replace(BASE,'')
        await step('register', register())
        async def login():
            me=await api('/auth/me/')
            if me.get('status')=='success': return
            await go('/login.html'); await pg.fill('[data-login-form] [name=email]',EMAIL); await pg.fill('[data-login-form] [name=password]',PW)
            await pg.click('[data-login-form] button[type=submit]'); await pg.wait_for_timeout(2500)
            me=await api('/auth/me/'); assert me.get('status')=='success', (pg.url, await pg.locator('[data-login-form] [role=alert]').all_inner_texts())
        await step('login', login())
        async def browse():
            await go('/shop.html'); n=await pg.locator('.product-card').count(); assert n>=8, f'cards={n}'
            await go('/search.html?q=charger'); n=await pg.locator('.product-card').count(); assert n>=1, f'search cards={n}'
        await step('shop + search listing', browse())
        async def pdp():
            await go('/product.html?slug=chg-65w'); assert 'Fast Charger' in await pg.inner_text('h1')
            await pg.click('[data-pdp-add]'); await pg.wait_for_timeout(1500)
            c=await api('/cart/'); items=c['data'].get('items',[]); assert len(items)==1, c
        await step('product page add to cart', pdp())
        async def wishlist():
            btn=pg.locator('[data-wishlist-toggle], [data-pdp-wishlist]').first
            if await btn.count(): await btn.click(); await pg.wait_for_timeout(1200)
            await go('/wishlist.html'); n=await pg.locator('.product-card, [data-wishlist-item]').count(); assert n>=1, f'wishlist items={n}'
        await step('wishlist', wishlist())
        async def cart():
            await go('/cart.html'); t=await pg.inner_text('main'); assert 'Fast Charger' in t, t[:200]
            inc=pg.locator('[data-qty-inc], [data-cart-inc], button[aria-label*="Increase"]').first
            await inc.click(); await pg.wait_for_timeout(1500)
            c=await api('/cart/'); assert c['data']['items'][0]['quantity']==2, c['data']['items'][0]
        await step('cart quantity update', cart())
        async def checkout():
            await go('/checkout.html'); f='[data-checkout-form] '
            for k,v in [('full_name','Ada Shopper'),('email',EMAIL),('phone','08031234567'),('address_line1','12 Allen Avenue'),('city','Ikeja')]:
                if await pg.locator(f+f'[name={k}]').count(): await pg.fill(f+f'[name={k}]',v)
            await pg.select_option(f+'[name=state]', label='Lagos'); await pg.wait_for_timeout(1800)
            opts=pg.locator('[data-delivery-options] input[type=radio]'); n=await opts.count(); assert n>=1, 'no delivery options: '+(await pg.inner_text('[data-delivery-options]'))[:200]
            await opts.first.check(); await pg.wait_for_timeout(1500)
            st['total']=(await pg.inner_text('[data-checkout-totals]')).replace('\n',' | ')
            await pg.check('[data-checkout-form] [name=accept_terms]'); await pg.click('[data-checkout-submit]')
            await pg.wait_for_url('**/payment-*', timeout=20000); await pg.wait_for_timeout(4000)
            st['after_pay']=pg.url.replace(BASE,''); st['pay_text']=(await pg.inner_text('main'))[:300].replace('\n',' | ')
        await step('checkout + pay (mock gateway)', checkout())
        async def orders():
            d=await api('/orders/'); assert d['count']>=1, d; o=d['results'][0]; st['order']=o['reference']; st['order_status']=(o['status'],o['payment_status'])
            assert o['payment_status']=='paid', st['order_status']
            await go('/orders.html'); assert o['reference'] in await pg.inner_text('main')
            await go('/order-detail.html?reference='+o['reference']); t=await pg.inner_text('main'); assert 'Fast Charger' in t, t[:300]
            c=await api('/cart/'); assert not c['data'].get('items'), 'cart not cleared'
        await step('orders list + detail, cart cleared', orders())
        async def account():
            await go('/account.html'); t=await pg.inner_text('main'); assert 'Ada' in t or EMAIL in t, t[:200]
        await step('account page', account())
        async def track():
            await ctx.clear_cookies(); await go('/track-order.html')
            await pg.fill('main [name=reference]', st.get('order','')); await pg.fill('main [name=email]', EMAIL)
            await pg.click('main form button[type=submit]'); await pg.wait_for_timeout(2500)
            st['track']=(await pg.inner_text('main'))[:200].replace('\n',' | ')
        await step('guest order tracking', track())
        async def guest():
            await go('/product.html?slug=blb-9w'); await pg.click('[data-pdp-add]'); await pg.wait_for_timeout(1500)
            await go('/checkout.html'); f='[data-checkout-form] '
            for k,v in [('full_name','Guest Buyer'),('email','guest'+U+'@example.test'),('phone','08039876543'),('address_line1','5 Aba Road'),('city','Port Harcourt')]:
                await pg.fill(f+f'[name={k}]',v)
            await pg.select_option(f+'[name=state]', label='Rivers'); await pg.wait_for_timeout(1800)
            await pg.locator('[data-delivery-options] input[type=radio]').first.check(); await pg.wait_for_timeout(1200)
            await pg.check('[data-checkout-form] [name=accept_terms]'); await pg.click('[data-checkout-submit]'); await pg.wait_for_url('**/payment-*', timeout=20000); await pg.wait_for_timeout(4000)
            st['guest_after_pay']=pg.url.replace(BASE,''); st['guest_text']=(await pg.inner_text('main'))[:200].replace('\n',' | ')
            assert 'success' in pg.url, pg.url
        await step('guest checkout + pay', guest())
        await b.close()
    for ok,name,e in R:
        print(('PASS ' if ok else 'FAIL ')+name)
        for x in e: print('      '+x)
    for k,v in st.items(): print(f'  {k}: {v}')
asyncio.run(main())
