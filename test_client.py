import urllib.request
import urllib.parse
import http.cookiejar
import json

BASE = 'http://127.0.0.1:5000'


def make_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def post(opener, path, payload):
    url = BASE + path
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=10) as resp:
        body = resp.read().decode('utf-8')
    try:
        return json.loads(body)
    except Exception:
        return body


if __name__ == '__main__':
    print('--- Valid user flow ---')
    op1 = make_opener()
    r1 = post(op1, '/chat/message', {'action': 'identify', 'method': 'email', 'identifier': 'joao@example.com'})
    print('identify ->', r1)
    r2 = post(op1, '/chat/message', {'action': 'option', 'option': 'suporte'})
    print('option ->', r2)

    print('\n--- Lead flow (unknown email) ---')
    op2 = make_opener()
    r3 = post(op2, '/chat/message', {'action': 'identify', 'method': 'email', 'identifier': 'unknown@example.com'})
    print('identify ->', r3)
    lead = {'action':'lead','name':'Teste Lead','email':'unknown@example.com','phone':'11999999999','company':'Loja X','message':'Quero anunciar carros'}
    r4 = post(op2, '/chat/message', lead)
    print('lead ->', r4)
