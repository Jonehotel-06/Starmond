"""Local stand-in for api.paystack.co used ONLY for end-to-end tests.
Implements /transaction/initialize, /transaction/verify/<ref>, /refund.
The 'checkout page' (/pay/<ref>) immediately redirects back to the callback URL.
Set MOCK_OUTCOME=failed to simulate a declined card."""
import json, os, itertools
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
TX={}; ids=itertools.count(900001)
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _json(self,code,obj):
        b=json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        if self.path=='/transaction/initialize':
            ref=body['reference']; TX[ref]={**body,'id':next(ids)}
            return self._json(200,{'status':True,'message':'Authorization URL created','data':{'authorization_url':f'http://localhost:8765/pay/{ref}','access_code':'mock_'+ref,'reference':ref}})
        if self.path=='/refund':
            return self._json(200,{'status':True,'message':'Refund queued','data':{'id':next(ids),'status':'pending','amount':body.get('amount'),'transaction':{'reference':str(body.get('transaction'))}}})
        self._json(404,{'status':False,'message':'not found'})
    def do_GET(self):
        if self.path.startswith('/transaction/verify/'):
            ref=self.path.rsplit('/',1)[1]; t=TX.get(ref)
            if not t: return self._json(404,{'status':False,'message':'Transaction reference not found'})
            ok=os.environ.get('MOCK_OUTCOME','success')=='success' and not ref.endswith('FAIL')
            return self._json(200,{'status':True,'message':'Verification successful','data':{'id':t['id'],'status':'success' if ok else 'failed','reference':ref,'amount':t['amount'],'currency':t.get('currency','NGN'),'channel':'card','gateway_response':'Successful' if ok else 'Declined','paid_at':'2026-11-15T10:00:00.000Z','customer':{'email':t.get('email')}}})
        if self.path.startswith('/pay/'):
            ref=self.path.rsplit('/',1)[1]; t=TX.get(ref,{}); cb=t.get('callback_url') or 'http://localhost:5173/payment-pending.html'
            sep='&' if '?' in cb else '?'
            self.send_response(302); self.send_header('Location',f'{cb}{sep}reference={ref}&trxref={ref}'); self.end_headers(); return
        self._json(404,{'status':False,'message':'not found'})
ThreadingHTTPServer(('0.0.0.0',8765),H).serve_forever()
