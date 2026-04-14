"""
ZeepLive API Test Automation Lab
- 4-tab UI: Manual Test | Auto Test | Results | Load Test
- Login -> Token auto-inject
- Error popup with missing field fill & retry
- Load testing with virtual users, ramp-up, real-time metrics
"""
import json, re, os, sys, time, threading, requests, copy, math, statistics, hashlib, secrets
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for

requests.packages.urllib3.disable_warnings()
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout
app.config['SESSION_COOKIE_HTTPONLY'] = True       # JS can't read session cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'     # CSRF protection

# ────────────────────── Auth Config ──────────────────────
# Credentials loaded from .env file (NEVER hardcoded in code)
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env.zeeplive')
AUTH_USERS = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SEC = 300
_login_attempts = {}

def _load_env_users():
    """Load users from .env file. Format: USER_xxx=hash"""
    if not os.path.exists(ENV_FILE):
        return {}
    users = {}
    with open(ENV_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or '=' not in line: continue
            key, val = line.split('=', 1)
            key, val = key.strip(), val.strip()
            if key.startswith('USER_'):
                username = key[5:].lower()
                users[username] = val
            elif key == 'SECRET_KEY':
                app.secret_key = val
    return users

def _setup_first_run():
    """First run - create .env with user-set credentials."""
    print("\n  ========================================")
    print("  FIRST RUN SETUP - Create Login Credentials")
    print("  ========================================")
    print("  (Credentials saved in .env.zeeplive file)")
    print("  (Code mein koi password nahi hoga)\n")

    users = {}
    while True:
        username = input("  Enter username (or 'done' to finish): ").strip()
        if username.lower() == 'done':
            break
        if not username:
            continue
        password = input(f"  Enter password for '{username}': ").strip()
        if len(password) < 4:
            print("  Password too short (min 4 chars)")
            continue
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        users[username] = pw_hash
        print(f"  Added user: {username}")

    if not users:
        print("  No users added! You must add at least one user.")
        print("  Run the app again to set up credentials.")
        sys.exit(1)

    # Generate secret key
    secret = secrets.token_hex(32)

    # Write .env file
    with open(ENV_FILE, 'w') as f:
        f.write("# ZeepLive Test Lab - Auth Credentials\n")
        f.write("# DO NOT share this file or commit to git!\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n\n")
        f.write(f"SECRET_KEY={secret}\n\n")
        for username, pw_hash in users.items():
            f.write(f"USER_{username}={pw_hash}\n")

    print(f"\n  Saved to: {ENV_FILE}")
    print(f"  Users: {', '.join(users.keys())}")
    print("  DO NOT share .env.zeeplive file!\n")
    return users, secret

def _load_env_system():
    """Load users from system environment variables (Railway/Docker)."""
    users = {}
    for k, v in os.environ.items():
        if k.startswith('USER_') and len(v) > 20:
            users[k[5:].lower()] = v
    return users

def init_auth():
    """Initialize auth - from system env (Railway) > .env file > first-run setup."""
    global AUTH_USERS
    # 1. Try system environment (Railway, Docker, etc.)
    AUTH_USERS = _load_env_system()
    if AUTH_USERS:
        print(f"  Auth: {len(AUTH_USERS)} users loaded from system environment")
        return
    # 2. Try .env file
    if os.path.exists(ENV_FILE):
        AUTH_USERS = _load_env_users()
        if AUTH_USERS:
            print(f"  Auth: {len(AUTH_USERS)} users loaded from .env.zeeplive")
            return
    # 3. First run setup (interactive)
    if sys.stdin.isatty():
        users, secret = _setup_first_run()
        AUTH_USERS = users
        app.secret_key = secret
    else:
        print("  ERROR: No users configured! Set USER_admin=<sha256hash> in environment.")
        sys.exit(1)

def check_auth():
    return session.get('logged_in') == True

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not check_auth():
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def is_locked_out(ip):
    info = _login_attempts.get(ip)
    if not info: return False
    if info['count'] >= MAX_LOGIN_ATTEMPTS:
        elapsed = time.time() - info['last_time']
        if elapsed < LOGIN_LOCKOUT_SEC:
            return True
        else:
            _login_attempts.pop(ip, None)
            return False
    return False

def record_failed_login(ip):
    if ip not in _login_attempts:
        _login_attempts[ip] = {'count': 0, 'last_time': 0}
    _login_attempts[ip]['count'] += 1
    _login_attempts[ip]['last_time'] = time.time()

def clear_login_attempts(ip):
    _login_attempts.pop(ip, None)

LOGIN_PAGE = r'''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Login - ZeepLive Test Lab</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a0a;color:#e0e0e0;height:100vh;display:flex;align-items:center;justify-content:center}
.login-box{background:#111;border:1px solid #222;border-radius:12px;padding:40px;width:400px;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.login-box h1{color:#4fc3f7;font-size:22px;text-align:center;margin-bottom:6px}
.login-box .sub{color:#888;font-size:12px;text-align:center;margin-bottom:24px}
.login-box label{display:block;font-size:12px;color:#aaa;margin-bottom:4px;font-weight:600}
.login-box input{width:100%;padding:10px 14px;background:#0a0a0a;color:#eee;border:1px solid #333;border-radius:6px;font-size:13px;margin-bottom:16px;font-family:Consolas,monospace}
.login-box input:focus{border-color:#4fc3f7;outline:none}
.login-box button{width:100%;padding:12px;background:#2e7d32;color:#fff;border:none;border-radius:6px;font-weight:700;cursor:pointer;font-size:14px}
.login-box button:hover{background:#388e3c}
.login-box button:disabled{background:#333;color:#666;cursor:not-allowed}
.err{color:#ef5350;font-size:11px;text-align:center;margin-bottom:12px;min-height:16px}
.lock{color:#ff8f00;font-size:11px;text-align:center;margin-bottom:12px}
.footer{text-align:center;margin-top:16px;font-size:10px;color:#444}
</style></head><body>
<div class="login-box">
    <h1>ZeepLive Test Lab</h1>
    <div class="sub">Login to access API testing tools</div>
    <div class="err" id="errMsg">{{ error }}</div>
    {% if locked %}
    <div class="lock">Too many attempts. Try again in {{ lockout_remaining }} seconds.</div>
    {% else %}
    <form method="POST" action="/login">
        <label>Username</label>
        <input type="text" name="username" placeholder="Enter username" required autofocus autocomplete="off">
        <label>Password</label>
        <input type="password" name="password" placeholder="Enter password" required autocomplete="off">
        <button type="submit">Login</button>
    </form>
    {% endif %}
    <div class="footer">Authorized personnel only</div>
</div>
</body></html>
'''

COLLECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "ZeepLive_Complete_API_Collection_FIXED (2).json")

STATE = {
    'variables': {},
    'folders': [],
    'all_endpoints': [],
    'history': [],
    'suite_results': [],
    'suite_progress': {
        'running': False, 'current': 0, 'total': 0,
        'current_name': '', 'results': [], 'start_time': 0, 'stats': {},
    },
    'suite_paused': False,
    'pause_data': None,
    'extra_fields_response': None,
    'custom_fields': {},  # {endpoint_name: {field: value}}
    # Load test
    'load': {
        'running': False, 'config': {}, 'start_time': 0,
        'metrics': [],       # [{ts, active_vus, rps, avg_rt, err_rate, p95, reqs_total, errs_total}]
        'requests': [],      # [{ts, endpoint, status, time_ms, error, vu_id}]
        'summary': None,
    },
}

# ────────────────────── Collection Loader ──────────────────────

def load_collection():
    with open(COLLECTION_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for v in data.get('variable', []):
        STATE['variables'][v['key']] = v.get('value', '')
    # Load API credentials from .env if available, else use collection defaults
    api_creds = _load_api_creds()
    STATE['variables'].update(api_creds)
    STATE['folders'], STATE['all_endpoints'] = [], []
    _parse(data.get('item', []), STATE['folders'], STATE['all_endpoints'])

def _load_api_creds():
    """Load ZeepLive API credentials from system env or .env file."""
    defaults = {'base_url': 'https://testingphp.zeep.live/api'}
    # System env first (Railway)
    for k, v in os.environ.items():
        if k.startswith('API_') and v:
            defaults[k[4:].lower()] = v
    # Then .env file
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' not in line or line.startswith('#'): continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip()
                if k.startswith('API_') and k not in os.environ:
                    defaults[k[4:].lower()] = v
    return defaults

def _parse(items, folders, eps, parent=""):
    for it in items:
        if 'item' in it:
            fld = {'name': it['name'], 'endpoints': []}
            _parse(it['item'], folders, eps, it['name'])
            fld['endpoints'] = [e for e in eps if e['folder'] == it['name']]
            folders.append(fld)
        elif 'request' in it:
            req = it['request']
            url = req.get('url', {})
            raw = url.get('raw', '') if isinstance(url, dict) else url
            hdrs = req.get('header', [])
            has_auth = any(h.get('key') == 'Authorization' for h in hdrs if not h.get('disabled'))
            eps.append({
                'name': it['name'], 'folder': parent,
                'method': req.get('method', 'GET'), 'url': raw,
                'headers': hdrs, 'body': req.get('body', {}),
                'auth': req.get('auth', {}), 'event': it.get('event', []),
                'needs_auth': has_auth or req.get('auth', {}).get('type') != 'noauth',
            })

def rv(text):
    if not isinstance(text, str): return text
    return re.sub(r'\{\{(\w+)\}\}', lambda m: STATE['variables'].get(m.group(1), m.group(0)), text)

# ────────────────────── Error Parser ──────────────────────

def parse_error_fields(resp_text):
    try: rj = json.loads(resp_text)
    except: return []
    if not isinstance(rj, dict) or rj.get('success') != False: return []
    err = rj.get('error', '') or ''
    fields = []
    for m in re.finditer(r'The\s+(.+?)\s+field\s+is\s+required', str(err), re.I):
        fields.append({'name': m.group(1).strip().replace(' ', '_'), 'reason': f'required'})
    for m in re.finditer(r"Column\s+'(\w+)'\s+cannot\s+be\s+null", str(err), re.I):
        fields.append({'name': m.group(1), 'reason': 'cannot be null'})
    for m in re.finditer(r'The\s+(.+?)\s+must\s+be\s+(.+?)[\.\,]', str(err), re.I):
        fn = m.group(1).strip().replace(' ', '_')
        if not any(f['name'] == fn for f in fields):
            fields.append({'name': fn, 'reason': f'must be {m.group(2)}'})
    errs = rj.get('errors', {})
    if isinstance(errs, dict):
        for k, v in errs.items():
            if not any(f['name'] == k for f in fields):
                fields.append({'name': k, 'reason': v[0] if isinstance(v, list) else str(v)})
    return fields

# ────────────────────── Execution Engine ──────────────────────

def execute_single(ep_data, extra_body=None, timeout=30):
    method = ep_data['method'].upper()
    url = rv(ep_data['url'])
    needs_auth = ep_data.get('needs_auth', True)

    # Headers
    headers = {}
    for h in ep_data.get('headers', []):
        if h.get('disabled'): continue
        k, v = h['key'], rv(h.get('value', ''))
        if k == 'Authorization' and needs_auth:
            tok = STATE['variables'].get('auth_token', '')
            if tok: v = f'Bearer {tok}'
        headers[k] = v
    if needs_auth and 'Authorization' not in headers:
        tok = STATE['variables'].get('auth_token', '')
        if tok: headers['Authorization'] = f'Bearer {tok}'

    # Body
    bcfg = ep_data.get('body', {})
    bdata, btype = None, None
    if bcfg:
        mode = bcfg.get('mode', '')
        if mode in ('formdata', 'urlencoded'):
            bdata = {}
            for f in bcfg.get(mode, []):
                if not f.get('disabled'): bdata[f['key']] = rv(f.get('value', ''))
            btype = 'form'
            if headers.get('Content-Type') == 'application/json':
                del headers['Content-Type']
        elif mode == 'raw':
            raw = rv(bcfg.get('raw', ''))
            try: bdata, btype = json.loads(raw), 'json'
            except: bdata, btype = raw, 'raw'

    if extra_body and isinstance(bdata, dict):
        bdata.update(extra_body)
    elif extra_body and bdata is None:
        bdata, btype = extra_body, 'form'

    start = time.time()
    res = {
        'endpoint_name': ep_data.get('name', ''), 'method': method, 'url': url,
        'needs_auth': needs_auth, 'status_code': 0, 'response_body': None,
        'response_headers': {}, 'time_ms': 0, 'size': 0, 'error': None,
        'success': False, 'missing_fields': [], 'api_error': None,
        'extracted_vars': {}, 'request_body': bdata,
        'timestamp': datetime.now().isoformat(),
    }
    try:
        kw = {'headers': headers, 'verify': False, 'timeout': timeout}
        if btype == 'json': kw['json'] = bdata
        elif btype in ('form',): kw['data'] = bdata
        elif btype == 'raw': kw['data'] = bdata
        resp = requests.request(method, url, **kw)
        if resp.status_code == 405 and method == 'POST':
            resp = requests.get(url, headers=headers, params=bdata if isinstance(bdata, dict) else {},
                                verify=False, timeout=timeout)
            res['method'] = 'GET(auto)'
        res['status_code'] = resp.status_code
        res['response_body'] = resp.text
        res['response_headers'] = dict(resp.headers)
        res['time_ms'] = int((time.time() - start) * 1000)
        res['size'] = len(resp.content)
        res['success'] = True
        res['missing_fields'] = parse_error_fields(resp.text)
        try:
            rj = resp.json()
            if isinstance(rj, dict) and rj.get('success') == False:
                res['api_error'] = rj.get('error', '')
            if isinstance(rj, dict) and rj.get('success') and isinstance(rj.get('result'), dict):
                r = rj['result']
                for k in ('token', 'profile_id', 'name', 'gender', 'mobile'):
                    if k in r and r[k]:
                        vk = 'auth_token' if k == 'token' else k
                        STATE['variables'][vk] = str(r[k])
                        res['extracted_vars'][vk] = str(r[k])
        except: pass
    except Exception as e:
        res['time_ms'] = int((time.time() - start) * 1000)
        res['error'] = f"{type(e).__name__}: {e}"
    STATE['history'].append({
        'method': method, 'url': url, 'status': res['status_code'],
        'time_ms': res['time_ms'], 'name': ep_data.get('name', ''),
    })
    return res

# ────────────────────── Suite Runner ──────────────────────

def run_suite_bg(suite):
    pr = STATE['suite_progress']
    pr.update({'running': True, 'current': 0, 'total': len(suite['steps']),
               'results': [], 'start_time': time.time(), 'current_name': '',
               'stats': {'passed': 0, 'failed': 0, 'errors': 0, 'total_time': 0},
               'suite_name': suite.get('name', 'Test')})

    for i, step in enumerate(suite['steps']):
        if not pr['running']: break
        pr['current'] = i + 1
        pr['current_name'] = step.get('name', f'Step {i+1}')
        ep = _find_ep(step.get('endpoint_name', ''))
        if not ep:
            pr['results'].append({'step': i+1, 'name': step.get('name',''),
                'status': 'error', 'error': 'Endpoint not found',
                'status_code': 0, 'time_ms': 0, 'assertions': [],
                'missing_fields': [], 'needs_auth': False})
            pr['stats']['errors'] += 1; continue

        # Use a deep copy so we don't mutate the original endpoint
        ep_copy = copy.deepcopy(ep)
        # Include saved custom fields for this endpoint
        cf_extra = STATE['custom_fields'].get(ep['name'])
        res = execute_single(ep_copy, extra_body=cf_extra, timeout=step.get('timeout', 30))

        # If missing fields → pause for user input
        if res['missing_fields'] and res.get('api_error'):
            STATE['suite_paused'] = True
            STATE['pause_data'] = {
                'step_idx': i, 'step_name': step.get('name', ep['name']),
                'endpoint_name': ep['name'],
                'missing_fields': res['missing_fields'],
                'api_error': res['api_error'],
                'status_code': res['status_code'],
            }
            STATE['extra_fields_response'] = None
            t0 = time.time()
            while STATE['suite_paused'] and (time.time() - t0) < 300:
                if not pr['running']: break
                time.sleep(0.3)
            STATE['suite_paused'] = False
            extra = STATE['extra_fields_response']
            STATE['extra_fields_response'] = None
            if extra and extra.get('action') == 'retry':
                res = execute_single(ep_copy, extra_body=extra.get('fields', {}),
                                     timeout=step.get('timeout', 30))

        # Assertions
        asserts = [
            {'type': 'status_2xx', 'label': 'Status 2xx'},
            {'type': 'no_error', 'label': 'No connection error'},
        ]
        if ep.get('needs_auth'):
            asserts.append({'type': 'not_401_403', 'label': 'Auth OK'})
        outcomes = _run_asserts(res, asserts)

        st = 'passed' if all(o['passed'] for o in outcomes) else 'failed'
        if res.get('error'): st = 'error'

        pr['results'].append({
            'step': i+1, 'name': step.get('name', ep['name']),
            'endpoint_name': ep['name'], 'method': res['method'],
            'url': res['url'], 'needs_auth': ep.get('needs_auth', False),
            'status': st, 'status_code': res['status_code'],
            'time_ms': res['time_ms'], 'assertions': outcomes,
            'extracted_vars': res.get('extracted_vars', {}),
            'error': res.get('error'), 'api_error': res.get('api_error'),
            'missing_fields': res.get('missing_fields', []),
            'response_body': (res.get('response_body') or '')[:3000],
            'request_body': res.get('request_body'),
        })
        pr['stats']['total_time'] += res['time_ms']
        pr['stats']['passed' if st == 'passed' else 'failed' if st == 'failed' else 'errors'] += 1
        if step.get('stop_on_fail') and st != 'passed': break
        time.sleep(step.get('delay_after', 300) / 1000)

    pr['running'] = False
    pr['stats']['total_elapsed'] = int((time.time() - pr['start_time']) * 1000)
    STATE['suite_results'].append({
        'suite_name': suite.get('name', ''),
        'timestamp': datetime.now().isoformat(),
        'stats': dict(pr['stats']), 'results': list(pr['results']),
    })

def _find_ep(name):
    for e in STATE['all_endpoints']:
        if e['name'] == name: return e
    for e in STATE['all_endpoints']:
        if name.lower() in e['name'].lower(): return e
    return None

def _run_asserts(res, asserts):
    out = []
    for a in asserts:
        t = a['type']; o = {'check': a.get('label', t), 'passed': False, 'actual': ''}
        if t == 'status_2xx':
            o['actual'] = str(res['status_code']); o['passed'] = 200 <= res['status_code'] < 300
        elif t == 'no_error':
            o['actual'] = res.get('error') or 'ok'; o['passed'] = res.get('error') is None
        elif t == 'not_401_403':
            o['actual'] = str(res['status_code']); o['passed'] = res['status_code'] not in (401, 403)
        out.append(o)
    return out

def _safe(ep):
    n = ep['name'].lower()
    bad = ['delete','update','add','create','upload','send','report','block','change','save','remove','deduct','follow','logout','register','stop','kick','exit']
    ok = ['get','list','check','details','data','points','balance','history','count','settings','price','plan','country','banner','search','status','level']
    if any(w in n for w in bad): return False
    if any(w in n for w in ok): return True
    return ep['method'] == 'GET'

# ────────────────────── Load Test Engine ──────────────────────

def _load_vu_worker(vu_id, config, endpoints, lock):
    """Single virtual user worker - simulates real user behavior."""
    L = STATE['load']
    session = requests.Session()
    session.verify = False
    token = STATE['variables'].get('auth_token', '')

    # If each VU should login independently
    if config.get('per_vu_login'):
        login_ep = _find_ep('Login User (Device Manual Login)')
        if login_ep:
            res = execute_single(login_ep, timeout=15)
            if res.get('extracted_vars', {}).get('auth_token'):
                token = res['extracted_vars']['auth_token']

    think_min = config.get('think_time_min', 500) / 1000
    think_max = config.get('think_time_max', 2000) / 1000

    import random
    while L['running']:
        ep = random.choice(endpoints)
        url = rv(ep['url'])

        # Build request
        headers = {}
        for h in ep.get('headers', []):
            if not h.get('disabled'):
                headers[h['key']] = rv(h.get('value', ''))
        if ep.get('needs_auth') and token:
            headers['Authorization'] = f'Bearer {token}'
        if headers.get('Content-Type') == 'application/json':
            del headers['Content-Type']

        bcfg = ep.get('body', {})
        bdata = None
        if bcfg:
            mode = bcfg.get('mode', '')
            if mode in ('formdata', 'urlencoded'):
                bdata = {}
                for f in bcfg.get(mode, []):
                    if not f.get('disabled'): bdata[f['key']] = rv(f.get('value', ''))

        start = time.time()
        entry = {'ts': time.time(), 'endpoint': ep['name'], 'status': 0,
                 'time_ms': 0, 'error': None, 'vu_id': vu_id}
        try:
            kw = {'headers': headers, 'verify': False, 'timeout': config.get('req_timeout', 30)}
            if bdata: kw['data'] = bdata
            resp = session.request(ep['method'], url, **kw)
            if resp.status_code == 405 and ep['method'] == 'POST':
                resp = session.get(url, headers=headers, params=bdata or {}, verify=False,
                                   timeout=config.get('req_timeout', 30))
            entry['status'] = resp.status_code
            entry['time_ms'] = int((time.time() - start) * 1000)
        except Exception as e:
            entry['time_ms'] = int((time.time() - start) * 1000)
            entry['error'] = str(e)[:100]

        with lock:
            L['requests'].append(entry)

        # Think time (simulate real user)
        if L['running']:
            time.sleep(random.uniform(think_min, think_max))

def _load_metrics_collector(config, lock):
    """Collect metrics every second."""
    L = STATE['load']
    interval = 1
    while L['running']:
        time.sleep(interval)
        now = time.time()
        elapsed = now - L['start_time']
        window = 3  # look at last 3 seconds for rates

        with lock:
            recent = [r for r in L['requests'] if r['ts'] > now - window]
            all_reqs = list(L['requests'])

        rps = len(recent) / window if recent else 0
        times = [r['time_ms'] for r in recent if r['time_ms'] > 0]
        errs = [r for r in recent if r.get('error') or r['status'] >= 500 or r['status'] == 0]
        err_rate = (len(errs) / len(recent) * 100) if recent else 0

        avg_rt = statistics.mean(times) if times else 0
        p50 = sorted(times)[len(times)//2] if times else 0
        p95 = sorted(times)[int(len(times)*0.95)] if len(times) > 1 else (times[0] if times else 0)
        p99 = sorted(times)[int(len(times)*0.99)] if len(times) > 1 else (times[0] if times else 0)
        mx = max(times) if times else 0

        # Count active VUs
        active = len(set(r['vu_id'] for r in recent))

        metric = {
            'ts': round(elapsed, 1), 'active_vus': active, 'rps': round(rps, 1),
            'avg_rt': round(avg_rt), 'p50': round(p50), 'p95': round(p95), 'p99': round(p99),
            'max_rt': round(mx), 'err_rate': round(err_rate, 1),
            'reqs_total': len(all_reqs),
            'errs_total': sum(1 for r in all_reqs if r.get('error') or r['status'] >= 500 or r['status'] == 0),
        }
        L['metrics'].append(metric)

def _load_test_runner(config):
    """Main load test orchestrator."""
    L = STATE['load']
    L['running'] = True
    L['config'] = config
    L['start_time'] = time.time()
    L['metrics'] = []
    L['requests'] = []
    L['summary'] = None

    # Resolve endpoint names to objects
    ep_names = config.get('endpoints', [])
    endpoints = [_find_ep(n) for n in ep_names if _find_ep(n)]
    if not endpoints:
        L['running'] = False; return

    max_vus = config.get('max_vus', 10)
    ramp_up = config.get('ramp_up', 5)  # seconds to reach max
    duration = config.get('duration', 30)  # total test duration in seconds
    pattern = config.get('pattern', 'ramp')  # ramp, constant, spike, stress

    lock = threading.Lock()
    pool = ThreadPoolExecutor(max_workers=max_vus + 2)
    futures = []

    # Start metrics collector
    pool.submit(_load_metrics_collector, config, lock)

    start = time.time()
    launched = 0

    while L['running'] and (time.time() - start) < duration:
        elapsed = time.time() - start

        # Calculate target VUs based on pattern
        if pattern == 'constant':
            target = max_vus
        elif pattern == 'ramp':
            if elapsed < ramp_up:
                target = max(1, int(max_vus * elapsed / ramp_up))
            else:
                target = max_vus
        elif pattern == 'spike':
            # Normal for 40%, spike at 50%, back to normal
            if elapsed < duration * 0.4:
                target = max(1, max_vus // 3)
            elif elapsed < duration * 0.6:
                target = max_vus
            else:
                target = max(1, max_vus // 3)
        elif pattern == 'stress':
            # Keep increasing every 10% of duration
            step = min(10, int(elapsed / (duration / 10)) + 1)
            target = max(1, int(max_vus * step / 10))
        else:
            target = max_vus

        # Launch new VUs if needed
        while launched < target:
            launched += 1
            fut = pool.submit(_load_vu_worker, launched, config, endpoints, lock)
            futures.append(fut)

        time.sleep(0.5)

    L['running'] = False
    # Wait for workers to stop (they check L['running'])
    time.sleep(2)

    # Build summary
    all_reqs = L['requests']
    if all_reqs:
        times = [r['time_ms'] for r in all_reqs if r['time_ms'] > 0]
        errors = [r for r in all_reqs if r.get('error') or r['status'] >= 500 or r['status'] == 0]
        st_times = sorted(times) if times else [0]

        # Per-endpoint breakdown
        ep_stats = defaultdict(lambda: {'count': 0, 'errors': 0, 'times': [], 'statuses': defaultdict(int)})
        for r in all_reqs:
            e = ep_stats[r['endpoint']]
            e['count'] += 1
            if r.get('error') or r['status'] >= 500 or r['status'] == 0: e['errors'] += 1
            if r['time_ms'] > 0: e['times'].append(r['time_ms'])
            e['statuses'][r['status']] += 1

        ep_breakdown = []
        for name, s in ep_stats.items():
            st = sorted(s['times']) if s['times'] else [0]
            ep_breakdown.append({
                'name': name, 'count': s['count'], 'errors': s['errors'],
                'avg': round(statistics.mean(s['times'])) if s['times'] else 0,
                'p50': st[len(st)//2] if st else 0,
                'p95': st[int(len(st)*0.95)] if len(st) > 1 else st[0],
                'max': max(st) if st else 0,
                'err_rate': round(s['errors']/s['count']*100, 1) if s['count'] else 0,
                'statuses': dict(s['statuses']),
            })
        ep_breakdown.sort(key=lambda x: x['avg'], reverse=True)

        # Status distribution
        status_dist = defaultdict(int)
        for r in all_reqs: status_dist[r['status']] += 1

        L['summary'] = {
            'total_requests': len(all_reqs),
            'total_errors': len(errors),
            'error_rate': round(len(errors)/len(all_reqs)*100, 1) if all_reqs else 0,
            'duration': round(time.time() - L['start_time'], 1),
            'avg_rps': round(len(all_reqs) / max(1, time.time() - L['start_time']), 1),
            'avg_rt': round(statistics.mean(times)) if times else 0,
            'min_rt': min(times) if times else 0,
            'p50': st_times[len(st_times)//2],
            'p95': st_times[int(len(st_times)*0.95)] if len(st_times) > 1 else st_times[0],
            'p99': st_times[int(len(st_times)*0.99)] if len(st_times) > 1 else st_times[0],
            'max_rt': max(times) if times else 0,
            'max_vus': max_vus,
            'pattern': pattern,
            'endpoints_tested': len(set(r['endpoint'] for r in all_reqs)),
            'ep_breakdown': ep_breakdown,
            'status_dist': dict(status_dist),
        }

    pool.shutdown(wait=False)

# ────────────────────── HTML ──────────────────────

HTML = r'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>ZeepLive Test Lab</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0a0a;color:#e0e0e0;height:100vh;overflow:hidden}
.app{display:flex;height:100vh}

/* Sidebar */
.side{width:280px;background:#111;border-right:1px solid #222;display:flex;flex-direction:column}
.side-hdr{padding:12px;background:#0a0a0a;border-bottom:1px solid #222;text-align:center}
.side-hdr h2{color:#4fc3f7;font-size:15px}
.side-hdr small{color:#999;font-size:11px}
.side-body{flex:1;overflow-y:auto}
.fld{border-bottom:1px solid #1a1a1a}
.fld-h{padding:7px 10px;cursor:pointer;font-size:12px;font-weight:600;color:#aaa;display:flex;justify-content:space-between}
.fld-h:hover{background:#1a1a1a;color:#fff}
.fld-h .c{background:#333;color:#ccc;padding:2px 7px;border-radius:8px;font-size:10px}
.fld-list{display:none;background:#0a0a0a}
.fld-list.open{display:block}
.ep-row{padding:5px 10px 5px 14px;cursor:pointer;font-size:11px;display:flex;align-items:center;gap:5px;border-left:2px solid transparent}
.ep-row:hover{background:#1a1a1a}
.ep-row.on{background:#1a1a1a;border-color:#4fc3f7}
.ep-row.has-custom{background:#0a0f1a;border-left-color:#1565c0}
.ep-row.has-custom.on{border-left-color:#42a5f5}
.cf-dot{background:#1565c0;color:#fff;padding:1px 5px;border-radius:8px;font-size:8px;font-weight:700;margin-left:auto;flex-shrink:0}
.bge{padding:2px 5px;border-radius:3px;font-size:9px;font-weight:700;min-width:30px;text-align:center}
.POST{background:#2e7d32;color:#fff}.GET{background:#1565c0;color:#fff}
.lk{font-size:9px;margin-left:auto;color:#ffb74d;font-weight:600}

/* Main */
.main{flex:1;display:flex;flex-direction:column}

/* Top tabs - the 3 main modes */
.mode-bar{display:flex;background:#111;border-bottom:2px solid #222}
.mode-tab{flex:1;padding:11px;text-align:center;cursor:pointer;font-size:13px;font-weight:700;color:#777;border-bottom:3px solid transparent;transition:.2s}
.mode-tab:hover{color:#ddd;background:#1a1a1a}
.mode-tab.on{color:#4fc3f7;border-color:#4fc3f7;background:#0a0a0a}
.mode-c{display:none;flex:1;overflow:hidden;flex-direction:column}
.mode-c.on{display:flex}

/* ===== TAB 1: MANUAL TEST ===== */
.manual-top{padding:8px 12px;background:#111;border-bottom:1px solid #222;display:flex;gap:6px;align-items:center}
.m-sel{padding:6px;background:#1a1a1a;color:#66bb6a;border:1px solid #333;border-radius:4px;font-weight:700;font-size:11px}
.m-url{flex:1;padding:7px 10px;background:#0a0a0a;color:#eee;border:1px solid #333;border-radius:4px;font-size:11px;font-family:Consolas,monospace}
.m-send{padding:7px 18px;background:#2e7d32;color:#fff;border:none;border-radius:4px;font-weight:700;cursor:pointer;font-size:12px}
.m-send:hover{background:#388e3c}.m-send:disabled{background:#333;color:#555}
.m-send.ld{animation:pu .8s infinite}
@keyframes pu{0%,100%{opacity:1}50%{opacity:.3}}

.manual-info{padding:5px 12px;background:#111;border-bottom:1px solid #222;font-size:11px;color:#999;display:flex;gap:10px;align-items:center}
.tok-st{margin-left:auto}
.tok-ok{color:#66bb6a;font-weight:600}.tok-no{color:#ef5350;font-weight:600}
.btn-sm{padding:3px 10px;background:#1a1a1a;color:#aaa;border:1px solid #444;border-radius:3px;font-size:10px;cursor:pointer}
.btn-sm:hover{color:#fff;border-color:#4fc3f7}
.btn-grn{background:#2e7d32;color:#fff;border-color:#2e7d32}

.manual-split{flex:1;display:flex;overflow:hidden}
.m-pnl{flex:1;display:flex;flex-direction:column;overflow:hidden}
.m-pnl+.m-pnl{border-left:1px solid #222}
.m-pnl-h{padding:7px 10px;background:#111;border-bottom:1px solid #222;font-size:12px;font-weight:600;display:flex;justify-content:space-between}
.m-pnl-h .x{color:#aaa;font-size:10px}

.tabs{display:flex;background:#0a0a0a;border-bottom:1px solid #222}
.tab{padding:5px 12px;cursor:pointer;font-size:11px;color:#888;border-bottom:2px solid transparent}
.tab:hover{color:#eee}.tab.on{color:#4fc3f7;border-color:#4fc3f7;font-weight:600}
.tc{display:none;flex:1;overflow-y:auto}.tc.on{display:flex;flex-direction:column}
.kv{display:flex;gap:4px;padding:3px 6px;align-items:center;border-bottom:1px solid #111}
.kv input{flex:1;padding:5px 7px;background:#0a0a0a;color:#eee;border:1px solid #333;border-radius:3px;font-size:11px;font-family:Consolas,monospace}
.kv input.k{max-width:130px;color:#4fc3f7}
.kv .x{background:none;border:none;color:#ef5350;cursor:pointer;font-size:12px}
.addb{padding:3px 8px;margin:4px 6px;background:none;border:1px dashed #444;color:#888;border-radius:3px;cursor:pointer;font-size:10px}
.addb:hover{border-color:#4fc3f7;color:#4fc3f7}
.rbody{flex:1;overflow-y:auto;padding:10px;background:#0a0a0a;font-family:Consolas,monospace;font-size:11px;line-height:1.6;white-space:pre-wrap;word-break:break-all}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#666;font-size:13px}

/* ===== TAB 2: AUTO TEST ===== */
.auto-top{padding:8px 12px;background:#111;border-bottom:1px solid #222;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.auto-cfg{padding:7px 12px;background:#0d0d0d;border-bottom:1px solid #222;display:flex;gap:10px;align-items:center;font-size:11px}
.auto-cfg label{color:#aaa}
.auto-cfg input,.auto-cfg select{padding:3px 6px;background:#0a0a0a;color:#eee;border:1px solid #444;border-radius:3px;font-size:11px}
.auto-cfg input[type=checkbox]{accent-color:#4fc3f7}

.sel-summary{padding:7px 12px;background:#111;border-bottom:1px solid #222;font-size:12px;display:flex;gap:12px;align-items:center;color:#ccc}
.sel-cnt{font-weight:700;color:#4fc3f7;font-size:14px}

.sel-area{flex:1;overflow-y:auto;padding:6px}
.sf{margin-bottom:4px}
.sf-h{padding:6px 8px;background:#111;border:1px solid #222;border-radius:3px;display:flex;align-items:center;gap:6px;cursor:pointer;font-size:11px;font-weight:600;color:#ccc}
.sf-h:hover{background:#1a1a1a}
.sf-h input[type=checkbox]{accent-color:#4fc3f7}
.sf-list{display:none;padding-left:16px}
.sf-list.open{display:block}
.se{padding:4px 6px;display:flex;align-items:center;gap:5px;font-size:10px;color:#ccc}
.se:hover{background:#1a1a1a}
.se input[type=checkbox]{accent-color:#66bb6a}
.se .tag{font-size:9px;padding:2px 5px;border-radius:2px;margin-left:auto;font-weight:600}
.se .tag.auth{background:#e65100;color:#fff}
.se .tag.safe{background:#2e7d32;color:#fff}
.se .tag.write{background:#f57f17;color:#fff}

/* ===== TAB 3: RESULTS ===== */
.res-area{flex:1;overflow-y:auto;padding:10px}
.pbar{width:100%;height:20px;background:#1a1a1a;border-radius:10px;overflow:hidden;margin:8px 0;position:relative}
.pfill{height:100%;border-radius:10px;transition:width .3s}
.pfill.run{background:linear-gradient(90deg,#1565c0,#42a5f5)}
.pfill.ok{background:#2e7d32}.pfill.bad{background:#c62828}
.ptxt{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:11px;font-weight:700;color:#fff}
.sg{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:8px 0}
.sc{background:#111;border:2px solid #222;border-radius:4px;padding:8px;text-align:center;cursor:pointer;transition:all .15s;user-select:none}
.sc:hover{border-color:#888;transform:scale(1.03)}
.sc.active{border-color:#4fc3f7 !important;background:#1a1a2a}
.sc .v{font-size:24px;font-weight:700}.sc .l{font-size:10px;color:#999;margin-top:2px;font-weight:600;text-transform:uppercase;letter-spacing:.5px}
.sc.ps .v{color:#66bb6a}.sc.ps.active{border-color:#66bb6a !important;background:#0a1a0a}
.sc.fl .v{color:#ef5350}.sc.fl.active{border-color:#ef5350 !important;background:#1a0a0a}
.sc.er .v{color:#ff8f00}.sc.er.active{border-color:#ff8f00 !important;background:#1a1500}
.sc.tm .v{color:#42a5f5}.sc.tm{cursor:default}
.filter-hint{font-size:10px;color:#999;text-align:center;padding:2px 0}
.rr.dim{opacity:.25}
.rr.hidden{display:none}

.rr{display:flex;align-items:center;gap:6px;padding:6px 10px;border-bottom:1px solid #1a1a1a;font-size:11px;cursor:pointer;color:#ddd}
.rr:hover{background:#1a1a1a}
.rd{display:none;padding:6px 10px 6px 30px;background:#111;border-bottom:1px solid #1a1a1a;font-size:10px;color:#ccc}
.rd.open{display:block}

.stb{padding:2px 6px;border-radius:3px;font-weight:700;font-size:10px}
.s2{background:#2e7d32;color:#fff}.s4{background:#e65100;color:#fff}.s5{background:#c62828;color:#fff}.s0{background:#333;color:#fff}

/* Error popup */
.overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:99}
.overlay.show{display:block}
.popup{display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:500px;max-height:80vh;background:#1a1a1a;border:2px solid #ef5350;border-radius:8px;z-index:100;overflow:hidden}
.popup.show{display:block}
.popup.pulse{animation:pbdr 1.5s infinite}
@keyframes pbdr{0%,100%{border-color:#ef5350}50%{border-color:#ff8a80}}
.pop-h{padding:10px 14px;background:#1c0c0c;display:flex;justify-content:space-between;align-items:center}
.pop-h h3{color:#ef5350;font-size:12px}
.pop-x{background:none;border:none;color:#888;font-size:18px;cursor:pointer}
.pop-b{padding:12px;max-height:60vh;overflow-y:auto}
.err-box{background:#0a0a0a;border:1px solid #333;border-radius:4px;padding:8px;margin-bottom:10px}
.err-msg{color:#ef5350;font-size:10px;font-family:Consolas,monospace;margin-top:4px;max-height:50px;overflow:auto}
.ef{display:flex;gap:6px;align-items:center;padding:6px 0;border-bottom:1px solid #222}
.ef label{min-width:110px;color:#ffb74d;font-size:12px;font-weight:600;font-family:Consolas,monospace}
.ef input{flex:1;padding:6px 10px;background:#0a0a0a;color:#eee;border:1px solid #444;border-radius:3px;font-size:12px;font-family:Consolas,monospace}
.ef input:focus{border-color:#ff8f00;outline:none}
.ef small{color:#999;font-size:9px}
.pop-actions{display:flex;gap:8px;margin-top:10px;justify-content:flex-end}
.pop-actions button{padding:6px 16px;border:none;border-radius:3px;font-weight:700;cursor:pointer;font-size:11px}
.pop-retry{background:#2e7d32;color:#fff}.pop-skip{background:#333;color:#888}

/* Vars modal */
.modal{display:none;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:550px;max-height:80vh;background:#1a1a1a;border:1px solid #333;border-radius:8px;z-index:100;overflow:hidden}
.modal.show{display:block}
.modal-h{padding:10px 14px;background:#111;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #222}
.modal-h h3{color:#4fc3f7;font-size:12px}
.modal-b{max-height:65vh;overflow-y:auto;padding:8px}

/* Load test config */
.lc-grp{margin-bottom:10px}
.lc-l{display:block;font-size:11px;color:#bbb;margin-bottom:4px;font-weight:600}
.lc-inp{padding:6px 8px;background:#0a0a0a;color:#eee;border:1px solid #444;border-radius:3px;font-size:11px;font-family:Consolas,monospace}
.lc-inp:focus{border-color:#4fc3f7;outline:none}
.lc-range{width:100%;accent-color:#4fc3f7;cursor:pointer}
.lc-hint{font-size:9px;color:#888;margin-top:3px}
.lc-q{display:inline-block;width:13px;height:13px;background:#222;color:#4fc3f7;border-radius:50%;text-align:center;font-size:10px;line-height:13px;cursor:help;margin-left:3px;border:1px solid #333}
.lc-q:hover{background:#4fc3f7;color:#000}
.lt-ep-row.lt-hide{display:none}
.lt-ep-hl{background:#ff8f00;color:#000;border-radius:1px;padding:0 1px}
.lt-stat{background:#111;border:1px solid #222;border-radius:4px;padding:6px 4px;text-align:center}
.lt-v{font-size:18px;font-weight:700;color:#4fc3f7;font-family:Consolas,monospace}
.lt-l{font-size:9px;color:#999;margin-top:2px;text-transform:uppercase;font-weight:600;letter-spacing:.3px}
.lt-ep-row{padding:3px 6px;display:flex;align-items:center;gap:5px;font-size:10px;color:#ccc;border-bottom:1px solid #1a1a1a}
.lt-ep-row:hover{background:#1a1a1a}
.lt-ep-row input{accent-color:#66bb6a}
.lt-tbl{width:100%;border-collapse:collapse;font-size:10px}
.lt-tbl th{background:#111;color:#aaa;padding:5px 8px;text-align:left;border-bottom:1px solid #222;font-weight:600;position:sticky;top:0}
.lt-tbl td{padding:5px 8px;border-bottom:1px solid #1a1a1a;font-family:Consolas,monospace;color:#ddd}
.lt-tbl tr:hover{background:#1a1a1a}

/* Search */
.ep-row.search-hide{display:none}
.fld.search-hide{display:none}
.search-hl{background:#ff8f00;color:#000;border-radius:1px;padding:0 1px}
#sideSearch:focus{border-color:#4fc3f7;outline:none}

/* Copy curl button in results */
.curl-btn{background:none;border:1px solid #444;color:#aaa;padding:2px 6px;border-radius:2px;font-size:9px;cursor:pointer;margin-left:4px;white-space:nowrap}
.curl-btn:hover{border-color:#4fc3f7;color:#4fc3f7}
.copied{color:#66bb6a !important;border-color:#66bb6a !important}

/* Toast */
.toast{position:fixed;bottom:20px;right:20px;background:#2e7d32;color:#fff;padding:8px 16px;border-radius:6px;font-size:11px;font-weight:700;z-index:200;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}

.jk{color:#42a5f5}.js{color:#66bb6a}.jn{color:#ffb74d}.jb{color:#ef5350}.jl{color:#888}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:#0a0a0a}::-webkit-scrollbar-thumb{background:#333;border-radius:2px}
</style></head><body>
<div class="app">

<!-- Sidebar: endpoint list -->
<div class="side">
    <div class="side-hdr">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <h2 style="margin:0">ZeepLive APIs</h2>
            <span style="display:flex;gap:4px">
                <button class="btn-sm" onclick="showChangePw()" style="font-size:9px;padding:2px 6px" title="Change password">PW</button>
                <a href="/logout" style="color:#ef5350;font-size:10px;text-decoration:none;padding:2px 8px;border:1px solid #ef5350;border-radius:3px" title="Logout and lock">Logout</a>
            </span>
        </div>
        <small id="epCnt"></small>
    </div>
    <div style="padding:4px 6px;border-bottom:1px solid #222">
        <input type="text" id="sideSearch" placeholder="Search APIs..." oninput="searchAPI(this.value)"
               style="width:100%;padding:5px 8px;background:#0a0a0a;color:#eee;border:1px solid #333;border-radius:4px;font-size:11px;font-family:Consolas,monospace">
    </div>
    <div style="padding:3px 6px;border-bottom:1px solid #222;display:flex;gap:3px">
        <button class="btn-sm" onclick="showAddApi()" style="flex:1;text-align:center">+ Add API</button>
        <button class="btn-sm" onclick="showAddCollection()" style="flex:1;text-align:center">+ Collection</button>
        <button class="btn-sm" onclick="showManage()" style="flex:1;text-align:center">Manage</button>
    </div>
    <div class="side-body" id="sideBody"></div>
</div>

<!-- Main -->
<div class="main">
    <!-- 3 clear modes -->
    <div class="mode-bar">
        <div class="mode-tab on" data-m="manual" onclick="swMode(this)">1. Manual Test</div>
        <div class="mode-tab" data-m="auto" onclick="swMode(this)">2. Auto Test</div>
        <div class="mode-tab" data-m="results" onclick="swMode(this)">3. Results</div>
        <div class="mode-tab" data-m="load" onclick="swMode(this)">4. Load Test</div>
    </div>

    <!-- ===== MODE 1: MANUAL TEST ===== -->
    <div class="mode-c on" id="mc-manual">
        <div class="manual-top">
            <select class="m-sel" id="mSel"><option>POST</option><option>GET</option><option>PUT</option><option>DELETE</option></select>
            <input class="m-url" id="mUrl" placeholder="Select endpoint from sidebar, then click SEND">
            <button class="m-send" id="sendBtn" onclick="doSend()">SEND</button>
            <button class="btn-sm" onclick="copyCurl()" title="Copy as cURL" style="font-size:11px;padding:7px 10px">cURL</button>
        </div>
        <div class="manual-info">
            <span id="epInfo">No endpoint selected</span>
            <button class="btn-sm btn-grn" onclick="doLogin()">Login & Get Token</button>
            <button class="btn-sm" onclick="showVars()">Variables</button>
            <button class="btn-sm" id="btnSaveEp" onclick="saveEndpoint()" style="display:none;background:#1565c0;color:#fff;border-color:#1565c0">Save Changes</button>
            <button class="btn-sm" id="btnEditEp" onclick="editEndpoint()" style="display:none">Edit</button>
            <button class="btn-sm" id="btnDelEp" onclick="deleteEndpoint()" style="display:none;color:#ef5350;border-color:#ef5350">Delete</button>
            <span class="tok-st" id="tokSt"></span>
        </div>
        <div class="manual-split">
            <div class="m-pnl">
                <div class="m-pnl-h"><span>Request</span></div>
                <div class="tabs"><div class="tab on" onclick="swTab(this,'th')">Headers</div><div class="tab" onclick="swTab(this,'tb')">Body</div></div>
                <div class="tc on" id="tc-th"><div id="hdEd"></div><button class="addb" onclick="addKV('hdEd')">+ add header</button></div>
                <div class="tc" id="tc-tb"><div id="bdEd"></div><button class="addb" onclick="addKV('bdEd')">+ add field</button></div>
            </div>
            <div class="m-pnl">
                <div class="m-pnl-h"><span>Response</span><span class="x" id="resSt"></span></div>
                <div class="tabs"><div class="tab on" onclick="swTab(this,'rp')">Body</div><div class="tab" onclick="swTab(this,'rh')">Headers</div></div>
                <div class="tc on" id="tc-rp"><div class="rbody" id="resBody"><div class="empty">Select an endpoint and click SEND</div></div></div>
                <div class="tc" id="tc-rh"><div class="rbody" id="resHdr"></div></div>
            </div>
        </div>
    </div>

    <!-- ===== MODE 2: AUTO TEST ===== -->
    <div class="mode-c" id="mc-auto">
        <div class="auto-top">
            <button class="btn-sm btn-grn" id="runBtn" onclick="runSuite()">Run Selected APIs</button>
            <button class="btn-sm" style="background:#c62828;color:#fff;display:none" id="stopBtn" onclick="stopSuite()">Stop</button>
            <button class="btn-sm" onclick="selAll()">Select All</button>
            <button class="btn-sm" onclick="selNone()">Deselect All</button>
            <button class="btn-sm" onclick="selSafe()">Safe Only (read-only)</button>
            <button class="btn-sm" style="background:#1565c0;color:#fff" onclick="loadPre('full')">Preset: Full Backend (20)</button>
            <button class="btn-sm" style="background:#1565c0;color:#fff" onclick="loadPre('auth')">Preset: Auth Flow (6)</button>
        </div>
        <div class="auto-cfg">
            <label><input type="checkbox" id="cfgLogin" checked> Auto-login first</label>
            <label>Delay: <input type="number" id="cfgDelay" value="300" style="width:50px">ms</label>
            <label>Timeout: <input type="number" id="cfgTimeout" value="30" style="width:40px">s</label>
            <label><input type="checkbox" id="cfgStop"> Stop on fail</label>
        </div>
        <div class="sel-summary">
            Selected: <span class="sel-cnt" id="selCnt">0</span> APIs
            <span style="margin-left:auto;font-size:10px;color:#999">Tick the APIs you want to test. Login will run first if checked above.</span>
        </div>
        <div class="sel-area" id="selArea"></div>
    </div>

    <!-- ===== MODE 3: RESULTS ===== -->
    <div class="mode-c" id="mc-results">
        <div class="res-area" id="resArea"><div class="empty" style="padding:40px">Run Auto Test first, results will appear here</div></div>
    </div>

    <!-- ===== MODE 4: LOAD TEST ===== -->
    <div class="mode-c" id="mc-load">
        <div style="display:flex;flex:1;overflow:hidden">
            <!-- Config panel -->
            <div style="width:300px;background:#111;border-right:1px solid #222;overflow-y:auto;padding:10px;flex-shrink:0">
                <div style="font-size:13px;font-weight:700;color:#4fc3f7;margin-bottom:10px">Load Test Config</div>

                <div class="lc-grp">
                    <label class="lc-l">Load Pattern <span class="lc-q" title="How virtual users are added over time">?</span></label>
                    <select id="ltPattern" class="lc-inp" style="width:100%">
                        <option value="ramp">Ramp Up - dheere dheere users badhao</option>
                        <option value="constant">Constant - sab users ek saath start</option>
                        <option value="spike">Spike - achanak bohot users ek saath</option>
                        <option value="stress">Stress - lagatar users badhate raho</option>
                    </select>
                    <div class="lc-hint" id="patternHint">Dheere dheere VUs badhenge ramp-up time mein, fir max pe hold</div>
                </div>

                <div class="lc-grp">
                    <label class="lc-l">Virtual Users (VUs) <span class="lc-q" title="Kitne fake users ek saath API hit karenge - jaise 10 log ek saath app use kar rahe hain">?</span></label>
                    <input type="range" id="ltVUs" min="1" max="100" value="10" class="lc-range" oninput="document.getElementById('ltVUsVal').textContent=this.value">
                    <div style="display:flex;justify-content:space-between;font-size:10px;color:#999"><span>1</span><span id="ltVUsVal" style="color:#4fc3f7;font-weight:700;font-size:12px">10</span><span>100</span></div>
                    <div class="lc-hint">Jitne zyada users, utna zyada load server pe</div>
                </div>

                <div class="lc-grp">
                    <label class="lc-l">Duration <span class="lc-q" title="Test kitni der chalega - seconds mein">?</span></label>
                    <input type="range" id="ltDuration" min="10" max="300" value="30" step="5" class="lc-range" oninput="document.getElementById('ltDurVal').textContent=this.value+'s'">
                    <div style="display:flex;justify-content:space-between;font-size:10px;color:#999"><span>10s</span><span id="ltDurVal" style="color:#4fc3f7;font-weight:700">30s</span><span>5min</span></div>
                    <div class="lc-hint">Total time test chalega</div>
                </div>

                <div class="lc-grp">
                    <label class="lc-l">Ramp-up Time (sec) <span class="lc-q" title="Ramp pattern mein: kitne seconds mein sab users aa jayenge. Ex: 10s ramp = 1 user add every second for 10 VUs">?</span></label>
                    <input type="number" id="ltRamp" value="5" class="lc-inp" style="width:100%">
                    <div class="lc-hint">Kitne sec mein sab VUs active honge (sirf Ramp pattern)</div>
                </div>

                <div class="lc-grp">
                    <label class="lc-l">Think Time (ms) <span class="lc-q" title="Real user jaise: ek request ke baad kitni der ruke fir dusri bheje. 500-2000ms = normal user speed">?</span></label>
                    <div style="display:flex;gap:6px">
                        <input type="number" id="ltThinkMin" value="500" class="lc-inp" style="flex:1" placeholder="min ms">
                        <span style="color:#999;font-size:10px;padding-top:4px">to</span>
                        <input type="number" id="ltThinkMax" value="2000" class="lc-inp" style="flex:1" placeholder="max ms">
                    </div>
                    <div class="lc-hint">Har request ke beech random delay - real user jaisa behavior</div>
                </div>

                <div class="lc-grp">
                    <label class="lc-l">Request Timeout (sec) <span class="lc-q" title="Ek request max kitni der wait karega response ka. Agar itne sec mein response nahi aaya toh error count hoga">?</span></label>
                    <input type="number" id="ltTimeout" value="30" class="lc-inp" style="width:100%">
                    <div class="lc-hint">Agar response itne sec mein na aaye toh timeout error</div>
                </div>

                <div class="lc-grp">
                    <label class="lc-l"><input type="checkbox" id="ltPerVuLogin"> Har VU apna login kare <span class="lc-q" title="ON = har fake user pehle login karega apna token lega (realistic). OFF = sab users ek hi token share karenge (fast)">?</span></label>
                    <div class="lc-hint">ON = har user ka apna session (realistic). OFF = sab same token (fast)</div>
                </div>

                <div class="lc-grp">
                    <label class="lc-l">Target APIs <span id="ltEpCnt" style="color:#4fc3f7">(0)</span> <span class="lc-q" title="Ye APIs random order mein hit hongi. Sirf safe/read-only select karo taaki data corrupt na ho">?</span></label>
                    <input type="text" id="ltEpSearch" placeholder="Search APIs..." class="lc-inp" style="width:100%;margin-bottom:4px" oninput="ltSearchEp(this.value)">
                    <div style="display:flex;gap:3px;margin-bottom:4px">
                        <button class="btn-sm" onclick="ltSelSafe()" style="flex:1">Safe APIs</button>
                        <button class="btn-sm" onclick="ltSelPreset()" style="flex:1">Backend (20)</button>
                        <button class="btn-sm" onclick="ltSelNone()" style="flex:1">Clear</button>
                    </div>
                    <div id="ltEpList" style="max-height:250px;overflow-y:auto;border:1px solid #222;border-radius:3px"></div>
                </div>

                <button id="ltRunBtn" onclick="startLoad()" style="width:100%;padding:10px;background:#2e7d32;color:#fff;border:none;border-radius:4px;font-weight:700;cursor:pointer;font-size:13px;margin-top:8px">START LOAD TEST</button>
                <button id="ltStopBtn" onclick="stopLoad()" style="width:100%;padding:10px;background:#c62828;color:#fff;border:none;border-radius:4px;font-weight:700;cursor:pointer;font-size:13px;margin-top:4px;display:none">STOP TEST</button>
            </div>

            <!-- Live metrics + chart -->
            <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">
                <!-- Live stats bar -->
                <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px;padding:8px;background:#0d0d0d;border-bottom:1px solid #222" id="ltStats">
                    <div class="lt-stat" title="Abhi kitne fake users active hain jo API hit kar rahe hain"><div class="lt-v" id="ls-vus">0</div><div class="lt-l">VUs <span class="lc-q" title="Virtual Users - jitne zyada VUs, utna zyada load. Jaise 100 log ek saath app use kar rahe">?</span></div></div>
                    <div class="lt-stat" title="Har second mein kitni API requests ja rahi hain server ko"><div class="lt-v" id="ls-rps">0</div><div class="lt-l">req/s <span class="lc-q" title="Requests Per Second - server pe kitna traffic aa raha hai. Zyada = zyada load">?</span></div></div>
                    <div class="lt-stat" title="Average response time - server kitni der mein jawab deta hai"><div class="lt-v" id="ls-avg">0</div><div class="lt-l">avg ms <span class="lc-q" title="Average Response Time milliseconds mein. 500ms = 0.5 sec. Kam = fast, Zyada = slow server">?</span></div></div>
                    <div class="lt-stat" title="95% requests isse kam time mein complete hoti hain"><div class="lt-v" id="ls-p95">0</div><div class="lt-l">p95 ms <span class="lc-q" title="95th Percentile - 100 mein se 95 requests isse fast hain. Real user experience ka indicator">?</span></div></div>
                    <div class="lt-stat" title="Kitni requests fail ho rahi hain (500 errors, timeouts)"><div class="lt-v" id="ls-err">0%</div><div class="lt-l">errors <span class="lc-q" title="Error Rate % - 0% = sab ok. 5%+ = problem. 50%+ = server crash ho raha">?</span></div></div>
                    <div class="lt-stat" title="Ab tak total kitni requests bheji gai hain"><div class="lt-v" id="ls-total">0</div><div class="lt-l">total <span class="lc-q" title="Total Requests - poore test mein ab tak kitni API calls hui">?</span></div></div>
                    <div class="lt-stat" title="Test shuru hue kitna time hua"><div class="lt-v" id="ls-time">0s</div><div class="lt-l">elapsed <span class="lc-q" title="Elapsed Time - test shuru hue kitne seconds ho gaye">?</span></div></div>
                </div>

                <!-- Chart -->
                <div style="flex:1;position:relative;background:#0a0a0a;min-height:250px">
                    <canvas id="ltChart" style="width:100%;height:100%"></canvas>
                    <div style="position:absolute;top:6px;right:8px;display:flex;gap:10px;font-size:10px">
                        <span style="color:#42a5f5">-- RPS</span>
                        <span style="color:#66bb6a">-- Avg RT</span>
                        <span style="color:#ef5350">-- Errors%</span>
                        <span style="color:#ff8f00">-- VUs</span>
                    </div>
                    <div id="ltChartEmpty" class="empty" style="position:absolute;inset:0;pointer-events:none">Configure and start load test</div>
                </div>

                <!-- Summary / per-endpoint breakdown -->
                <div style="max-height:40%;overflow-y:auto;border-top:1px solid #222" id="ltSummary">
                </div>
            </div>
        </div>
    </div>
</div>
</div>

<!-- Toast notification -->
<div class="toast" id="toast"></div>

<!-- Error popup -->
<div class="overlay" id="overlay"></div>
<div class="popup" id="errPop">
    <div class="pop-h"><h3 id="popTitle">API Error</h3><button class="pop-x" onclick="popAction('skip')">&times;</button></div>
    <div class="pop-b" id="popBody"></div>
</div>

<!-- Vars modal -->
<div class="modal" id="varsMdl">
    <div class="modal-h"><h3>Variables (token, profile_id, etc)</h3><button class="pop-x" onclick="closeVars()">&times;</button></div>
    <div class="modal-b" id="varsB"></div>
</div>

<!-- Add API modal -->
<div class="modal" id="addApiMdl" style="width:620px">
    <div class="modal-h" style="background:#1a2a1a"><h3 style="color:#66bb6a">Add New API Endpoint</h3><button class="pop-x" onclick="closeAllMdl()">&times;</button></div>
    <div class="modal-b" style="padding:14px">
        <div class="lc-grp"><label class="lc-l">Folder (group name)</label>
            <select id="addApiFolder" class="lc-inp" style="width:100%"></select>
            <input id="addApiFolderNew" class="lc-inp" style="width:100%;margin-top:4px" placeholder="Or type new folder name...">
        </div>
        <div class="lc-grp"><label class="lc-l">API Name</label>
            <input id="addApiName" class="lc-inp" style="width:100%" placeholder="e.g. Get User Balance">
        </div>
        <div style="display:flex;gap:6px;align-items:flex-end">
            <div class="lc-grp" style="width:100px"><label class="lc-l">Method</label>
                <select id="addApiMethod" class="lc-inp" style="width:100%"><option>POST</option><option>GET</option><option>PUT</option><option>DELETE</option><option>PATCH</option></select>
            </div>
            <div class="lc-grp" style="flex:1"><label class="lc-l">Base URL</label>
                <input id="addApiBase" class="lc-inp" style="width:100%" value="https://testingphp.zeep.live/api">
            </div>
        </div>
        <div class="lc-grp"><label class="lc-l">Endpoint Path <span style="color:#ef5350">*</span></label>
            <div style="display:flex;align-items:center;gap:0;border:1px solid #444;border-radius:3px;overflow:hidden">
                <span style="background:#1a1a1a;color:#888;padding:6px 8px;font-size:11px;font-family:Consolas,monospace;white-space:nowrap;border-right:1px solid #444">/api/</span>
                <input id="addApiEndpoint" style="flex:1;padding:6px 8px;background:#0a0a0a;color:#4fc3f7;border:none;font-size:12px;font-family:Consolas,monospace;font-weight:600" placeholder="getUserBalance">
            </div>
            <div class="lc-hint">Sirf endpoint path likho, e.g. <b>getprofiledata</b> ya <b>wallet-history-latest</b></div>
        </div>
        <div class="lc-grp"><label class="lc-l">Needs Auth Token?</label>
            <select id="addApiAuth" class="lc-inp" style="width:100%"><option value="yes">Yes - Bearer token auto-inject hoga</option><option value="no">No - koi auth nahi chahiye</option></select>
        </div>
        <div class="lc-grp"><label class="lc-l">Request Body Type <span style="color:#ef5350">*</span></label>
            <select id="addApiBodyType" class="lc-inp" style="width:100%" onchange="toggleAddApiBody()">
                <option value="formdata">form-data (most common - key/value pairs)</option>
                <option value="urlencoded">x-www-form-urlencoded (form submit jaise)</option>
                <option value="raw">raw JSON ({"key":"value"} format)</option>
                <option value="none">No Body (GET requests jaise)</option>
            </select>
        </div>
        <div class="lc-grp" id="addApiBodyGrp"><label class="lc-l">Body Fields</label>
            <div id="addApiBodyArea">
                <div id="addApiKVFields">
                    <div style="font-size:10px;color:#888;padding:2px 0;display:flex;gap:6px"><span style="flex:1">Key</span><span style="flex:1">Value</span><span style="width:20px"></span></div>
                </div>
                <button class="btn-sm" onclick="addApiFieldRow()" style="width:100%;margin-top:4px;text-align:center">+ Add Field</button>
            </div>
            <textarea id="addApiRawBody" style="width:100%;min-height:80px;background:#0a0a0a;color:#eee;border:1px solid #444;border-radius:3px;padding:8px;font-size:11px;font-family:Consolas,monospace;resize:vertical;display:none" placeholder='{"profile_id": "{{profile_id}}", "type": 1}'></textarea>
        </div>
        <div class="lc-grp"><label class="lc-l">Extra Headers (optional)</label>
            <textarea id="addApiHeaders" style="width:100%;min-height:36px;background:#0a0a0a;color:#eee;border:1px solid #444;border-radius:3px;padding:6px;font-size:11px;font-family:Consolas,monospace;resize:vertical" placeholder="key=value, one per line (optional)"></textarea>
        </div>
        <div style="background:#111;border:1px solid #222;border-radius:4px;padding:8px;margin-bottom:8px">
            <div style="font-size:10px;color:#888;margin-bottom:4px">Preview:</div>
            <div id="addApiPreview" style="font-family:Consolas,monospace;font-size:11px;color:#4fc3f7"></div>
        </div>
        <button onclick="submitAddApi()" style="width:100%;padding:10px;background:#2e7d32;color:#fff;border:none;border-radius:4px;font-weight:700;cursor:pointer;font-size:13px">Add API</button>
    </div>
</div>

<!-- Add Collection modal -->
<div class="modal" id="addCollMdl" style="width:620px">
    <div class="modal-h" style="background:#1a1a2a"><h3 style="color:#42a5f5">Import Postman Collection</h3><button class="pop-x" onclick="closeAllMdl()">&times;</button></div>
    <div class="modal-b" style="padding:14px">
        <div class="lc-grp">
            <label class="lc-l">Upload Collection JSON file</label>
            <input type="file" id="collFile" accept=".json" style="color:#ccc;font-size:11px" onchange="previewColl(this)">
        </div>
        <div class="lc-grp">
            <label class="lc-l">Or paste JSON below</label>
            <textarea id="collJson" style="width:100%;min-height:150px;background:#0a0a0a;color:#eee;border:1px solid #444;border-radius:3px;padding:8px;font-size:10px;font-family:Consolas,monospace;resize:vertical" placeholder='Paste Postman Collection v2.1 JSON here...'></textarea>
        </div>
        <div id="collPreview" style="font-size:11px;color:#999;margin-bottom:8px"></div>
        <div style="display:flex;gap:6px">
            <button onclick="submitCollection('merge')" style="flex:1;padding:10px;background:#1565c0;color:#fff;border:none;border-radius:4px;font-weight:700;cursor:pointer;font-size:12px">Merge (add to existing)</button>
            <button onclick="submitCollection('replace')" style="flex:1;padding:10px;background:#e65100;color:#fff;border:none;border-radius:4px;font-weight:700;cursor:pointer;font-size:12px">Replace All</button>
        </div>
    </div>
</div>

<!-- Manage modal -->
<div class="modal" id="manageMdl" style="width:650px">
    <div class="modal-h"><h3>Manage APIs & Collections</h3><button class="pop-x" onclick="closeAllMdl()">&times;</button></div>
    <div class="modal-b" style="padding:0">
        <div style="padding:8px 14px;border-bottom:1px solid #222;display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            <input type="text" id="manageSearch" placeholder="Search to filter..." class="lc-inp" style="flex:1" oninput="filterManage(this.value)">
            <button class="btn-sm" style="background:#c62828;color:#fff" onclick="deleteSelected()">Delete Selected</button>
            <button class="btn-sm" onclick="exportCollection()">Export JSON</button>
            <span id="manageSelCnt" style="font-size:10px;color:#999">0 selected</span>
        </div>
        <div id="manageList" style="max-height:55vh;overflow-y:auto;padding:4px"></div>
    </div>
</div>

<script>
let F=[],A=[],V={},cur=null,sel={},pollT=null,popMode='manual',resFilter='all',lastP=null;
// Custom fields added by user (persists per endpoint until removed)
// Key: endpoint name, Value: [{key,value}]
let customFields={};

fetch('/api/data').then(r=>r.json()).then(d=>{
    F=d.folders;A=d.all_endpoints;V=d.variables;
    document.getElementById('epCnt').textContent=A.length+' endpoints';
    renderSide();renderSel();updTok();
});

// ── Sidebar ──
function renderSide(){
    let h='';F.forEach((f,i)=>{
        h+=`<div class="fld"><div class="fld-h" onclick="this.nextElementSibling.classList.toggle('open')"><span>${f.name}</span><span class="c">${f.endpoints.length}</span></div><div class="fld-list">`;
        f.endpoints.forEach((e,j)=>{
            h+=`<div class="ep-row" id="ep-${i}-${j}" onclick="pickEp(${i},${j})"><span class="bge ${e.method}">${e.method}</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${e.name}</span>${e.needs_auth?'<span class="lk">TOKEN</span>':''}</div>`;
        });h+=`</div></div>`;
    });document.getElementById('sideBody').innerHTML=h;
}

function pickEp(fi,ei){
    document.querySelectorAll('.ep-row').forEach(e=>e.classList.remove('on'));
    document.getElementById('ep-'+fi+'-'+ei).classList.add('on');
    cur=F[fi].endpoints[ei];
    cur._fi=fi;cur._ei=ei;

    // Method + URL (resolve variables)
    document.getElementById('mSel').value=cur.method;
    const resolvedUrl=rv(cur.url||'');
    document.getElementById('mUrl').value=resolvedUrl;

    // Endpoint info + custom fields badge
    const cf=customFields[cur.name];
    const cfBadge=cf&&cf.length?`<span style="background:#1565c0;color:#fff;padding:2px 7px;border-radius:3px;font-size:10px;margin-left:6px">${cf.length} custom field(s)</span>`:'';
    document.getElementById('epInfo').innerHTML=`<b>${esc(cur.name)}</b> ${cur.needs_auth?'<span style="color:#ffb74d">[needs token]</span>':'<span style="color:#66bb6a">[no auth]</span>'}${cfBadge}`;

    // Headers
    let hh='';
    (cur.headers||[]).forEach(h=>{if(!h.disabled)hh+=kvR(h.key,rv(h.value||''))});
    document.getElementById('hdEd').innerHTML=hh;

    // Body fields = original + saved custom fields
    let bh='';
    const bd=cur.body||{},m=bd.mode||'',fl=bd[m]||bd.formdata||bd.urlencoded||[];
    if(Array.isArray(fl))fl.forEach(f=>{if(!f.disabled)bh+=kvR(f.key,rv(f.value||''))});
    // Append saved custom fields
    if(cf&&cf.length){
        bh+=`<div style="border-top:2px dashed #1565c0;margin:6px 0;padding-top:4px"></div>`;
        bh+=`<div style="display:flex;justify-content:space-between;padding:3px 6px;font-size:10px;color:#42a5f5;font-weight:600"><span>Custom Fields (saved for this API)</span><button class="btn-sm" style="font-size:9px;padding:2px 6px;color:#ef5350;border-color:#ef5350" onclick="removeAllCustomFields()">Remove All Custom</button></div>`;
        cf.forEach((f,i)=>{
            bh+=`<div class="kv" style="background:#0a0f1a;border-left:2px solid #1565c0"><input class="k" value="${esc(f.key)}" style="color:#42a5f5"><input value="${esc(f.value)}"><button class="x" onclick="removeCustomField(${i})" title="Remove this saved field">&times;</button></div>`;
        });
    }
    document.getElementById('bdEd').innerHTML=bh;

    // Switch to Body tab so custom fields are visible
    if(cf&&cf.length){
        const bodyTab=document.querySelectorAll('.m-pnl')[0]?.querySelectorAll('.tab')[1];
        if(bodyTab)swTab(bodyTab,'tb');
    }

    document.getElementById('resBody').innerHTML='<div class="empty">Click SEND to test this API</div>';
    document.getElementById('resHdr').textContent='';document.getElementById('resSt').innerHTML='';
    // Show Save/Edit/Delete buttons
    document.getElementById('btnSaveEp').style.display='';
    document.getElementById('btnEditEp').style.display='';
    document.getElementById('btnDelEp').style.display='';
    swMode(document.querySelector('[data-m="manual"]'));
}

// ── Helpers ──
function kvR(k,v){return`<div class="kv"><input class="k" value="${esc(k)}"><input value="${esc(v)}"><button class="x" onclick="this.parentElement.remove()">&times;</button></div>`}
function addKV(id){document.getElementById(id).insertAdjacentHTML('beforeend',kvR('',''))}
function rv(t){return t?t.replace(/\{\{(\w+)\}\}/g,(m,k)=>V[k]||m):''}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function getKV(id){const d={};document.querySelectorAll('#'+id+' .kv').forEach(r=>{const i=r.querySelectorAll('input');if(i[0].value.trim())d[i[0].value.trim()]=i[1].value});return d}

function swMode(el){
    document.querySelectorAll('.mode-tab').forEach(t=>t.classList.remove('on'));el.classList.add('on');
    ['manual','auto','results','load'].forEach(m=>document.getElementById('mc-'+m).classList.remove('on'));
    document.getElementById('mc-'+el.dataset.m).classList.add('on');
}
function swTab(el,id){
    const p=el.closest('.m-pnl')||el.closest('.mode-c');
    p.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
    p.querySelectorAll('.tc').forEach(t=>t.classList.remove('on'));
    el.classList.add('on');document.getElementById('tc-'+id).classList.add('on');
}

function updTok(){
    document.getElementById('tokSt').innerHTML=V.auth_token
        ?`<span class="tok-ok">Token Active | ID: ${V.profile_id||'?'}</span>`
        :`<span class="tok-no">No Token - click "Login & Get Token"</span>`;
}

// ── Manual Send ──
async function doSend(){
    const b=document.getElementById('sendBtn');b.disabled=true;b.classList.add('ld');b.textContent='...';
    const bd=getKV('bdEd'),hd=getKV('hdEd');
    try{
        const r=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({method:document.getElementById('mSel').value,url:document.getElementById('mUrl').value,headers:hd,body:bd,needs_auth:cur?cur.needs_auth:true})});
        const res=await r.json();
        const sc=res.status_code,cls=sc>=500?'s5':sc>=400?'s4':sc>=200?'s2':'s0';
        document.getElementById('resSt').innerHTML=`<span class="stb ${cls}">${sc}</span> ${res.time_ms}ms`;
        try{document.getElementById('resBody').innerHTML=synHL(JSON.stringify(JSON.parse(res.body),null,2))}
        catch(e){document.getElementById('resBody').textContent=res.body}
        let rh='';for(const[k,v] of Object.entries(res.response_headers||{}))rh+=`<span class="jk">${esc(k)}</span>: ${esc(v)}\n`;
        document.getElementById('resHdr').innerHTML=rh;
        if(res.updated_variables){Object.assign(V,res.updated_variables);updTok()}
        if(res.missing_fields&&res.missing_fields.length)showPop(res.missing_fields,res.api_error,res.status_code,'manual');
    }catch(e){document.getElementById('resBody').innerHTML=`<span style="color:#ef5350">${esc(e.message)}</span>`}
    b.disabled=false;b.classList.remove('ld');b.textContent='SEND';
}
async function doLogin(){
    const ep=A.find(e=>e.url.includes('device-manual-login'));if(!ep)return;
    for(let i=0;i<F.length;i++)for(let j=0;j<F[i].endpoints.length;j++)
        if(F[i].endpoints[j].name===ep.name){pickEp(i,j);document.getElementById('ep-'+i+'-'+j).closest('.fld-list').classList.add('open');break}
    await doSend();
}

// ── Variables ──
function showVars(){
    let h='';for(const[k,v] of Object.entries(V)){
        h+=`<div class="kv"><input class="k" value="${esc(k)}" readonly style="background:#0a0a0a"><input value="${esc(v)}" onchange="V['${esc(k)}']=this.value;fetch('/api/variables',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'${esc(k)}',value:this.value})})"></div>`;
    }document.getElementById('varsB').innerHTML=h;document.getElementById('varsMdl').classList.add('show');document.getElementById('overlay').classList.add('show');
}
function closeVars(){document.getElementById('varsMdl').classList.remove('show');document.getElementById('overlay').classList.remove('show')}

// ── Error Popup ──
function showPop(fields,apiErr,code,mode,epName){
    popMode=mode;
    let h=`<div class="err-box"><span class="stb s4">${code||'ERR'}</span>`;
    if(epName)h+=` <b style="color:#42a5f5">${esc(epName)}</b>`;
    h+=` <span style="color:#ef5350">returned an error</span>`;
    if(apiErr)h+=`<div class="err-msg">${esc(String(apiErr).substring(0,300))}</div>`;
    h+=`</div><div style="font-size:11px;color:#ff8f00;margin-bottom:8px;font-weight:600">Fill these fields and retry:</div>`;
    fields.forEach((f,i)=>{
        const sug=V[f.name]||V[f.name.replace(/_/g,'')]||'';
        h+=`<div class="ef"><label>${esc(f.name)}</label><input id="pf-${i}" data-f="${esc(f.name)}" value="${esc(sug)}" placeholder="enter value"><small>${esc(f.reason)}</small></div>`;
    });
    h+=`<div class="pop-actions"><button class="pop-skip" onclick="popAction('skip')">Skip</button><button class="pop-retry" onclick="popAction('retry')">Retry with fields</button></div>`;
    document.getElementById('popBody').innerHTML=h;
    document.getElementById('popTitle').textContent=(mode==='suite'?'PAUSED - ':'')+fields.length+' missing field(s)';
    document.getElementById('errPop').classList.add('show');if(mode==='suite')document.getElementById('errPop').classList.add('pulse');
    else document.getElementById('errPop').classList.remove('pulse');
    document.getElementById('overlay').classList.add('show');
    setTimeout(()=>{const f=document.getElementById('pf-0');if(f)f.focus()},100);
}
async function popAction(act){
    const fields={};document.querySelectorAll('#popBody .ef input').forEach(inp=>{
        if(inp.dataset.f&&inp.value.trim())fields[inp.dataset.f]=inp.value.trim();
    });
    document.getElementById('errPop').classList.remove('show','pulse');
    document.getElementById('overlay').classList.remove('show');

    if(act==='retry'&&Object.keys(fields).length){
        // Save custom fields for this endpoint (persist until removed)
        if(cur&&cur.name){
            if(!customFields[cur.name])customFields[cur.name]=[];
            for(const[k,v] of Object.entries(fields)){
                // Don't duplicate
                if(!customFields[cur.name].some(f=>f.key===k)){
                    customFields[cur.name].push({key:k,value:v});
                }
            }
            refreshSidebarHighlights();
        }
    }

    if(popMode==='manual'&&act==='retry'&&Object.keys(fields).length){
        // Reload endpoint with custom fields
        if(cur&&cur._fi!==undefined)pickEp(cur._fi,cur._ei);
        await doSend();
    } else if(popMode==='suite'){
        // Also save fields for suite mode
        if(Object.keys(fields).length){
            const pauseEp=document.getElementById('popTitle')?.textContent||'';
            // Find endpoint name from pause data
            const pd=lastP?.pause_data||{};
            if(pd.endpoint_name&&!customFields[pd.endpoint_name])customFields[pd.endpoint_name]=[];
            if(pd.endpoint_name){
                for(const[k,v] of Object.entries(fields)){
                    if(!customFields[pd.endpoint_name].some(f=>f.key===k))
                        customFields[pd.endpoint_name].push({key:k,value:v});
                }
            }
            refreshSidebarHighlights();
        }
        await fetch('/api/suite-resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:act,fields})});
    }
}

// ── Custom Fields Management ──
function removeCustomField(idx){
    if(!cur||!cur.name)return;
    const cf=customFields[cur.name];
    if(cf){cf.splice(idx,1);if(!cf.length)delete customFields[cur.name]}
    refreshSidebarHighlights();
    // Reload endpoint view
    if(cur._fi!==undefined)pickEp(cur._fi,cur._ei);
}

function removeAllCustomFields(){
    if(!cur||!cur.name)return;
    if(!confirm('Remove all custom fields from "'+cur.name+'"?'))return;
    delete customFields[cur.name];
    refreshSidebarHighlights();
    if(cur._fi!==undefined)pickEp(cur._fi,cur._ei);
    showToast('Custom fields removed');
}

// ── Save / Edit / Delete Endpoint ──

async function saveEndpoint(){
    if(!cur)return alert('No endpoint selected');
    // Read current headers from UI
    const headers=[];
    document.querySelectorAll('#hdEd .kv').forEach(r=>{
        const inputs=r.querySelectorAll('input');
        if(inputs[0].value.trim())headers.push({key:inputs[0].value.trim(),value:inputs[1].value,type:'text'});
    });
    // Read current body from UI (exclude custom fields section)
    const bodyFields=[];
    document.querySelectorAll('#bdEd .kv:not([style*="0a0f1a"])').forEach(r=>{
        const inputs=r.querySelectorAll('input');
        if(inputs[0].value.trim())bodyFields.push({key:inputs[0].value.trim(),value:inputs[1].value,type:'text'});
    });
    const method=document.getElementById('mSel').value;
    const url=document.getElementById('mUrl').value;

    const r=await fetch('/api/endpoints/update',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
            name:cur.name, method, url, headers, body_fields:bodyFields,
            needs_auth:headers.some(h=>h.key==='Authorization'),
        })});
    const res=await r.json();
    if(res.ok){
        showToast('Saved: '+cur.name);
        await reloadData();
        // Re-select the endpoint
        for(let i=0;i<F.length;i++)for(let j=0;j<F[i].endpoints.length;j++)
            if(F[i].endpoints[j].name===cur.name){pickEp(i,j);return}
    }else{
        alert('Error: '+(res.error||'Save failed'));
    }
}

function editEndpoint(){
    if(!cur)return;
    // Open Add API modal pre-filled with current endpoint data
    showAddApi();
    // Fill in values
    const url=cur.url||'';
    const base=url.substring(0,url.lastIndexOf('/'));
    const endpoint=url.substring(url.lastIndexOf('/')+1);

    document.getElementById('addApiName').value=cur.name;
    document.getElementById('addApiBase').value=base||'https://testingphp.zeep.live/api';
    document.getElementById('addApiEndpoint').value=endpoint;
    document.getElementById('addApiMethod').value=cur.method||'POST';
    document.getElementById('addApiAuth').value=cur.needs_auth?'yes':'no';

    // Set folder
    const folderSel=document.getElementById('addApiFolder');
    for(let i=0;i<folderSel.options.length;i++){
        if(folderSel.options[i].value===cur.folder){folderSel.selectedIndex=i;break}
    }

    // Body type + fields
    const bd=cur.body||{};
    const mode=bd.mode||'formdata';
    if(mode==='raw'){
        document.getElementById('addApiBodyType').value='raw';
        toggleAddApiBody();
        document.getElementById('addApiRawBody').value=bd.raw||'';
    }else{
        document.getElementById('addApiBodyType').value=mode==='urlencoded'?'urlencoded':'formdata';
        toggleAddApiBody();
        // Clear existing rows and add endpoint's fields
        document.getElementById('addApiKVFields').innerHTML=`<div style="font-size:10px;color:#888;padding:2px 0;display:flex;gap:6px"><span style="flex:1">Key</span><span style="flex:1">Value</span><span style="width:20px"></span></div>`;
        const fields=bd[mode]||bd.formdata||bd.urlencoded||[];
        if(Array.isArray(fields)&&fields.length){
            fields.forEach(f=>{if(!f.disabled)addApiFieldRow(f.key,f.value||'')});
        }else{
            addApiFieldRow();
        }
    }

    // Headers (skip Authorization)
    const hdrText=(cur.headers||[]).filter(h=>!h.disabled&&h.key!=='Authorization').map(h=>h.key+'='+h.value).join('\n');
    document.getElementById('addApiHeaders').value=hdrText;

    updateAddApiPreview();

    // Change modal title and button to "Update"
    document.querySelector('#addApiMdl .modal-h h3').textContent='Edit API Endpoint';
    document.querySelector('#addApiMdl .modal-h').style.background='#1a1a2a';
    document.querySelector('#addApiMdl .modal-h h3').style.color='#42a5f5';
    // Replace submit button
    const submitBtn=document.querySelector('#addApiMdl button[onclick="submitAddApi()"]');
    if(submitBtn){
        submitBtn.textContent='Save Changes';
        submitBtn.style.background='#1565c0';
        submitBtn.onclick=async function(){
            // Delete old, then add new
            const oldName=cur.name;
            await fetch('/api/endpoints/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({names:[oldName]})});
            await submitAddApi();
        };
    }
}

async function deleteEndpoint(){
    if(!cur)return;
    if(!confirm('Delete "'+cur.name+'" ?'))return;
    const r=await fetch('/api/endpoints/delete',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({names:[cur.name]})});
    const res=await r.json();
    if(res.ok){
        showToast('Deleted: '+cur.name);
        cur=null;
        document.getElementById('epInfo').textContent='No endpoint selected';
        document.getElementById('btnSaveEp').style.display='none';
        document.getElementById('btnEditEp').style.display='none';
        document.getElementById('btnDelEp').style.display='none';
        document.getElementById('mUrl').value='';
        document.getElementById('hdEd').innerHTML='';
        document.getElementById('bdEd').innerHTML='';
        await reloadData();
    }
}

function syncCustomFieldsToBackend(){
    // Convert [{key,value}] to {key:value} for backend
    const out={};
    for(const[name,fields] of Object.entries(customFields)){
        out[name]={};
        fields.forEach(f=>out[name][f.key]=f.value);
    }
    fetch('/api/custom-fields',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(out)});
}

function refreshSidebarHighlights(){
    syncCustomFieldsToBackend();
    // Mark sidebar endpoints that have custom fields
    document.querySelectorAll('.ep-row').forEach(row=>{
        row.classList.remove('has-custom');
        row.querySelector('.cf-dot')?.remove();
    });
    F.forEach((f,fi)=>{
        f.endpoints.forEach((ep,ei)=>{
            if(customFields[ep.name]&&customFields[ep.name].length){
                const row=document.getElementById('ep-'+fi+'-'+ei);
                if(row){
                    row.classList.add('has-custom');
                    if(!row.querySelector('.cf-dot')){
                        row.insertAdjacentHTML('beforeend',`<span class="cf-dot" title="${customFields[ep.name].length} custom field(s)">${customFields[ep.name].length}</span>`);
                    }
                }
            }
        });
    });
}

// ── Auto Test Selection ──
function renderSel(){
    sel={};let h='';
    F.forEach((f,fi)=>{
        h+=`<div class="sf"><div class="sf-h" onclick="this.nextElementSibling.classList.toggle('open')">
            <input type="checkbox" id="fc-${fi}" onclick="event.stopPropagation();togFC(${fi})">
            <span style="flex:1">${f.name}</span><span class="c" style="background:#222;padding:1px 5px;border-radius:6px;font-size:10px">${f.endpoints.length}</span>
        </div><div class="sf-list">`;
        f.endpoints.forEach((ep,ei)=>{
            const k=fi+'-'+ei;sel[k]=false;
            const safe=isSafe(ep);
            h+=`<div class="se"><input type="checkbox" id="sc-${k}" onchange="sel['${k}']=this.checked;syncFolders();updCnt()">
                <span class="bge ${ep.method}" style="font-size:9px">${ep.method}</span>
                <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${ep.name}</span>
                <span class="tag ${safe?'safe':'write'}">${safe?'SAFE':'WRITE'}</span>
                ${ep.needs_auth?'<span class="tag auth">TOKEN</span>':''}
            </div>`;
        });h+=`</div></div>`;
    });document.getElementById('selArea').innerHTML=h;updCnt();
}
function isSafe(ep){
    const n=ep.name.toLowerCase();
    const bad=['delete','update','add','create','upload','send','report','block','change','save','remove','deduct','follow','logout','register','stop','kick','exit'];
    const ok=['get','list','check','details','data','points','balance','history','count','settings','price','plan','country','banner','search','status','level'];
    if(bad.some(w=>n.includes(w)))return false;if(ok.some(w=>n.includes(w)))return true;return ep.method==='GET';
}
function togFC(fi){
    const c=document.getElementById('fc-'+fi).checked;
    F[fi].endpoints.forEach((e,ei)=>{const k=fi+'-'+ei;sel[k]=c;const cb=document.getElementById('sc-'+k);if(cb)cb.checked=c});
    updCnt();
}
function syncFolders(){
    // Update each folder checkbox: checked if ALL children checked, indeterminate if SOME
    F.forEach((f,fi)=>{
        let total=0,checked=0;
        f.endpoints.forEach((e,ei)=>{total++;if(sel[fi+'-'+ei])checked++});
        const fc=document.getElementById('fc-'+fi);
        if(fc){
            fc.checked=checked>0&&checked===total;
            fc.indeterminate=checked>0&&checked<total;
        }
        // Also auto-open folder if any endpoint is selected
        if(checked>0){
            const list=fc?.closest('.sf')?.querySelector('.sf-list');
            if(list)list.classList.add('open');
        }
    });
}
function selAll(){
    for(let k in sel){sel[k]=true;const c=document.getElementById('sc-'+k);if(c)c.checked=true}
    syncFolders();updCnt();
}
function selNone(){
    for(let k in sel){sel[k]=false;const c=document.getElementById('sc-'+k);if(c)c.checked=false}
    F.forEach((f,i)=>{const c=document.getElementById('fc-'+i);if(c){c.checked=false;c.indeterminate=false}});
    updCnt();
}
function selSafe(){
    selNone();
    F.forEach((f,fi)=>f.endpoints.forEach((ep,ei)=>{
        if(isSafe(ep)){const k=fi+'-'+ei;sel[k]=true;const c=document.getElementById('sc-'+k);if(c)c.checked=true}
    }));
    syncFolders();updCnt();
}
function loadPre(t){
    fetch('/api/preset/'+t).then(r=>r.json()).then(names=>{
        selNone();
        names.forEach(nm=>{F.forEach((f,fi)=>f.endpoints.forEach((ep,ei)=>{
            if(ep.name===nm){const k=fi+'-'+ei;sel[k]=true;const c=document.getElementById('sc-'+k);if(c)c.checked=true}
        }))});
        syncFolders();updCnt();
    });
}
function updCnt(){
    let n=0;for(let k in sel)if(sel[k])n++;
    document.getElementById('selCnt').textContent=n;
}

// ── Run Suite ──
async function runSuite(){
    const names=[];
    if(document.getElementById('cfgLogin').checked)names.push('Login User (Device Manual Login)');
    F.forEach((f,fi)=>f.endpoints.forEach((ep,ei)=>{if(sel[fi+'-'+ei]&&!ep.url.includes('device-manual-login'))names.push(ep.name)}));
    if(!names.length)return alert('Select at least 1 API');
    const delay=+document.getElementById('cfgDelay').value||300;
    const timeout=+document.getElementById('cfgTimeout').value||30;
    const stopFail=document.getElementById('cfgStop').checked;
    const steps=names.map((nm,i)=>({
        name:(i+1)+'. '+nm, endpoint_name:nm, delay_after:delay, timeout,
        stop_on_fail:nm.includes('Login')?true:stopFail,
    }));
    document.getElementById('runBtn').style.display='none';document.getElementById('stopBtn').style.display='';
    swMode(document.querySelector('[data-m="results"]'));
    await fetch('/api/run-suite',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Auto Test ('+names.length+' APIs)',steps})});
    pollT=setInterval(poll,400);
}
async function stopSuite(){await fetch('/api/stop-suite',{method:'POST'});document.getElementById('runBtn').style.display='';document.getElementById('stopBtn').style.display='none'}
async function poll(){
    const p=await(await fetch('/api/suite-progress')).json();
    renderRes(p);
    if(p.paused&&p.pause_data&&p.pause_data.missing_fields&&p.pause_data.missing_fields.length&&!document.getElementById('errPop').classList.contains('show'))
        showPop(p.pause_data.missing_fields,p.pause_data.api_error,p.pause_data.status_code,'suite',p.pause_data.endpoint_name);
    if(!p.running){clearInterval(pollT);pollT=null;document.getElementById('runBtn').style.display='';document.getElementById('stopBtn').style.display='none';updTok()}
}

function filterRes(type){
    if(resFilter===type)resFilter='all'; else resFilter=type;
    if(lastP)renderRes(lastP);
}
function renderRes(p){
    lastP=p;
    const st=p.stats||{},tot=p.total||1,pct=Math.round((p.current/tot)*100);
    const cls=p.running?(p.paused?'run':'run'):(st.failed||st.errors?'bad':'ok');
    const results=p.results||[];
    const filteredCount=resFilter==='all'?results.length:results.filter(r=>r.status===resFilter).length;
    const avgTime=results.length?Math.round(results.reduce((s,r)=>s+r.time_ms,0)/results.length):0;
    const slowest=results.length?results.reduce((a,b)=>a.time_ms>b.time_ms?a:b,results[0]):null;

    let h=`<div style="display:flex;justify-content:space-between;font-size:11px;font-weight:700">
        <span>${esc(p.suite_name||'')}</span>
        <span style="color:${p.paused?'#ff8f00':'#555'}">${p.current}/${p.total} ${p.paused?'PAUSED - fill popup':p.running?esc(p.current_name):'Done'}</span>
    </div>
    <div class="pbar"><div class="pfill ${cls}" style="width:${pct}%"></div><div class="ptxt">${p.paused?'PAUSED':pct+'%'}</div></div>
    <div class="sg">
        <div class="sc ps ${resFilter==='passed'?'active':''}" onclick="filterRes('passed')"><div class="v">${st.passed||0}</div><div class="l">PASSED</div></div>
        <div class="sc fl ${resFilter==='failed'?'active':''}" onclick="filterRes('failed')"><div class="v">${st.failed||0}</div><div class="l">FAILED</div></div>
        <div class="sc er ${resFilter==='error'?'active':''}" onclick="filterRes('error')"><div class="v">${st.errors||0}</div><div class="l">ERRORS</div></div>
        <div class="sc tm"><div class="v">${st.total_time?Math.round(st.total_time/1000*10)/10+'s':'--'}</div><div class="l">TIME</div></div>
    </div>`;

    // Filter bar
    if(!p.running){
        h+=`<div style="display:flex;gap:6px;align-items:center;padding:4px 0;font-size:10px;color:#999;border-bottom:1px solid #1a1a1a;margin-bottom:4px">
            <span>Filter:</span>
            <span style="cursor:pointer;padding:1px 6px;border-radius:2px;${resFilter==='all'?'background:#333;color:#fff':''}" onclick="resFilter='all';renderRes(lastP)">ALL (${results.length})</span>
            <span style="cursor:pointer;padding:1px 6px;border-radius:2px;color:#66bb6a;${resFilter==='passed'?'background:#1a2a1a':''}" onclick="filterRes('passed')">PASS (${st.passed||0})</span>
            <span style="cursor:pointer;padding:1px 6px;border-radius:2px;color:#ef5350;${resFilter==='failed'?'background:#2a1a1a':''}" onclick="filterRes('failed')">FAIL (${st.failed||0})</span>
            <span style="cursor:pointer;padding:1px 6px;border-radius:2px;color:#ff8f00;${resFilter==='error'?'background:#2a1a00':''}" onclick="filterRes('error')">ERR (${st.errors||0})</span>
            <span style="margin-left:auto;color:#888">avg: ${avgTime}ms${slowest?' | slowest: '+esc(slowest.endpoint_name||'')+' ('+slowest.time_ms+'ms)':''}</span>
        </div>`;
    }

    results.forEach((r,i)=>{
        const show=resFilter==='all'||r.status===resFilter;
        const ic=r.status==='passed'?'<span style="color:#66bb6a">&#10004;</span>':r.status==='error'?'<span style="color:#ff8f00">&#9888;</span>':'<span style="color:#ef5350">&#10008;</span>';
        const cc=r.status_code>=500?'s5':r.status_code>=400?'s4':r.status_code>=200?'s2':'s0';
        const slow=r.time_ms>5000?'<span style="color:#ef5350;font-size:9px">SLOW</span>':'';
        h+=`<div class="rr${show?'':' hidden'}" data-ri="${i}" onclick="if(event.target.classList.contains('curl-btn'))return;document.getElementById('rd-${i}').classList.toggle('open')">
            ${ic}<span style="flex:1;font-weight:600;font-size:10px">${r.needs_auth?'<span style="color:#ff8f00;font-size:10px">TOKEN </span>':''}${esc(r.name)}</span>
            ${r.status_code?`<span class="stb ${cc}">${r.status_code}</span>`:''}
            ${slow}
            <span style="color:#999;font-size:10px">${r.time_ms}ms</span>
            <span style="font-size:9px;color:${r.assertions&&r.assertions.every(a=>a.passed)?'#66bb6a':'#ef5350'}">${r.assertions?r.assertions.filter(a=>a.passed).length+'/'+r.assertions.length:''}</span>
            <button class="curl-btn" onclick="event.stopPropagation();copyCurlFromResult(lastP.results[${i}])">cURL</button>
        </div><div class="rd" id="rd-${i}">`;
        if(r.assertions)r.assertions.forEach(a=>{h+=`<div style="padding:1px 0">${a.passed?'<span style="color:#66bb6a">&#10004;</span>':'<span style="color:#ef5350">&#10008;</span>'} ${esc(a.check)} <span style="color:#aaa">actual: ${esc(a.actual)}</span></div>`});
        if(r.api_error)h+=`<div style="color:#ef5350;margin-top:3px;font-family:Consolas,monospace;font-size:9px;padding:3px 6px;background:#1a0a0a;border-radius:2px">${esc(String(r.api_error).substring(0,200))}</div>`;
        if(r.missing_fields&&r.missing_fields.length){h+=`<div style="color:#ff8f00;margin-top:3px;font-weight:600;font-size:9px">Missing fields: `;r.missing_fields.forEach(f=>h+=`<span style="background:#1a1500;padding:1px 4px;border-radius:2px;margin-right:3px">${esc(f.name)}</span> `);h+=`</div>`}
        if(r.extracted_vars&&Object.keys(r.extracted_vars).length){h+=`<div style="color:#66bb6a;margin-top:3px;font-size:9px">`;for(const[k,v] of Object.entries(r.extracted_vars))h+=`<span style="background:#0a1a0a;padding:1px 4px;border-radius:2px;margin-right:3px">${esc(k)}=${esc(v).substring(0,40)}...</span> `;h+=`</div>`}
        if(r.response_body){let prev=r.response_body.substring(0,400);try{prev=JSON.stringify(JSON.parse(r.response_body),null,2).substring(0,400)}catch(e){}
        h+=`<details style="margin-top:3px"><summary style="cursor:pointer;color:#999;font-size:10px">response body</summary><pre style="font-size:10px;color:#888;max-height:120px;overflow:auto">${esc(prev)}</pre></details>`}
        h+=`</div>`;
    });
    if(!results.length)h+=`<div class="empty">Waiting for results...</div>`;
    document.getElementById('resArea').innerHTML=h;
}

// ── Search API ──
function searchAPI(q){
    q=q.toLowerCase().trim();
    document.querySelectorAll('.fld').forEach(fld=>{
        const eps=fld.querySelectorAll('.ep-row');
        let anyVisible=false;
        eps.forEach(ep=>{
            const name=ep.textContent.toLowerCase();
            if(!q||name.includes(q)){
                ep.classList.remove('search-hide');anyVisible=true;
                // highlight match
                if(q){
                    const span=ep.querySelector('span:nth-child(2)');
                    if(span){
                        const orig=span.textContent;
                        const idx=orig.toLowerCase().indexOf(q);
                        if(idx>=0)span.innerHTML=esc(orig.substring(0,idx))+'<span class="search-hl">'+esc(orig.substring(idx,idx+q.length))+'</span>'+esc(orig.substring(idx+q.length));
                    }
                }
            }else{
                ep.classList.add('search-hide');
            }
        });
        if(!q){
            fld.classList.remove('search-hide');
            // Remove highlights
            eps.forEach(ep=>{const s=ep.querySelector('span:nth-child(2)');if(s)s.innerHTML=esc(s.textContent)});
        }else{
            if(anyVisible){fld.classList.remove('search-hide');fld.querySelector('.fld-list').classList.add('open')}
            else fld.classList.add('search-hide');
        }
    });
}

// ── Copy cURL ──
function buildCurl(method,url,headers,body){
    let c=`curl -X ${method} '${url}'`;
    if(headers){
        for(const[k,v] of Object.entries(headers)){
            // Shorten long tokens for readability
            const val=v.length>100?v.substring(0,60)+'...':v;
            c+=` \\\n  -H '${k}: ${val}'`;
        }
    }
    if(body&&typeof body==='object'&&Object.keys(body).length){
        for(const[k,v] of Object.entries(body)){
            c+=` \\\n  -d '${k}=${v}'`;
        }
    }
    return c;
}

function copyCurl(){
    const method=document.getElementById('mSel').value;
    const url=document.getElementById('mUrl').value;
    const hd=getKV('hdEd');
    const bd=getKV('bdEd');
    // Inject token if needed
    if(cur&&cur.needs_auth&&V.auth_token&&!hd['Authorization']){
        hd['Authorization']='Bearer '+V.auth_token;
    }
    const curl=buildCurl(method,url,hd,bd);
    navigator.clipboard.writeText(curl).then(()=>showToast('cURL copied!')).catch(()=>{
        // Fallback
        const ta=document.createElement('textarea');ta.value=curl;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);
        showToast('cURL copied!');
    });
}

function copyCurlFromResult(r){
    const hd={};
    if(r.needs_auth&&V.auth_token)hd['Authorization']='Bearer '+V.auth_token;
    const curl=buildCurl(r.method||'POST',r.url||'',hd,r.request_body||{});
    navigator.clipboard.writeText(curl).then(()=>showToast('cURL copied!')).catch(()=>showToast('Copy failed'));
}

function showToast(msg){
    const t=document.getElementById('toast');
    t.textContent=msg;t.classList.add('show');
    setTimeout(()=>t.classList.remove('show'),2000);
}

// ═══ LOAD TEST ═══
let ltSel={},ltPoll=null;

function renderLtEps(){
    if(!A.length)return;
    let h='';
    A.forEach((ep,i)=>{
        const k='lt-'+i;ltSel[k]=ltSel[k]||false;
        const safe=_safe2(ep);
        h+=`<div class="lt-ep-row"><input type="checkbox" id="${k}" onchange="ltSel['${k}']=this.checked;ltUpdCnt()"><span class="bge ${ep.method}" style="font-size:9px">${ep.method}</span><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:${safe?'#ccc':'#888'}">${ep.name}</span>${safe?'<span style="color:#66bb6a;font-size:8px">SAFE</span>':'<span style="color:#ff8f00;font-size:8px">WRITE</span>'}</div>`;
    });
    document.getElementById('ltEpList').innerHTML=h;ltUpdCnt();
}
function _safe2(ep){
    const n=ep.name.toLowerCase();
    const bad=['delete','update','add','create','upload','send','report','block','change','save','remove','deduct','follow','logout','register','stop','kick','exit'];
    if(bad.some(w=>n.includes(w)))return false;return true;
}
function ltUpdCnt(){let n=0;for(let k in ltSel)if(ltSel[k])n++;document.getElementById('ltEpCnt').textContent='('+n+')'}
function ltSelSafe(){for(let k in ltSel){const i=+k.split('-')[1];const ep=A[i];ltSel[k]=_safe2(ep);const c=document.getElementById(k);if(c)c.checked=ltSel[k]};ltUpdCnt()}
function ltSelPreset(){
    fetch('/api/preset/full').then(r=>r.json()).then(names=>{
        for(let k in ltSel){ltSel[k]=false;const c=document.getElementById(k);if(c)c.checked=false}
        names.forEach(nm=>{A.forEach((ep,i)=>{if(ep.name===nm){const k='lt-'+i;ltSel[k]=true;const c=document.getElementById(k);if(c)c.checked=true}})});
        ltUpdCnt();
    });
}
function ltSelNone(){for(let k in ltSel){ltSel[k]=false;const c=document.getElementById(k);if(c)c.checked=false};ltUpdCnt()}

// Pattern hint
document.addEventListener('DOMContentLoaded',()=>{
    const hints={
        ramp:'Dheere dheere VUs badhenge ramp-up time mein, fir max pe hold',
        constant:'Sab VUs turant start - ek saath full load',
        spike:'Pehle kam load, fir 40-60% pe achanak spike, fir wapas kam',
        stress:'Har 10% duration pe naye users add - jab tak server na tute'
    };
    const sel=document.getElementById('ltPattern');
    if(sel)sel.onchange=()=>{document.getElementById('patternHint').textContent=hints[sel.value]||''};
});

function ltSearchEp(q){
    q=q.toLowerCase().trim();
    document.querySelectorAll('.lt-ep-row').forEach(row=>{
        const txt=row.textContent.toLowerCase();
        if(!q||txt.includes(q)){
            row.classList.remove('lt-hide');
            // highlight
            const span=row.querySelector('span:last-child');
            if(span&&q){
                const orig=span.textContent;
                const idx=orig.toLowerCase().indexOf(q);
                if(idx>=0)span.innerHTML=esc(orig.substring(0,idx))+'<span class="lt-ep-hl">'+esc(orig.substring(idx,idx+q.length))+'</span>'+esc(orig.substring(idx+q.length));
            }else if(span&&!q){
                span.innerHTML=esc(span.textContent);
            }
        }else{
            row.classList.add('lt-hide');
        }
    });
}

async function startLoad(){
    const eps=[];
    for(let k in ltSel)if(ltSel[k]){const i=+k.split('-')[1];eps.push(A[i].name)}
    if(!eps.length)return alert('Select at least 1 API for load test');

    const cfg={
        max_vus:+document.getElementById('ltVUs').value,
        duration:+document.getElementById('ltDuration').value,
        ramp_up:+document.getElementById('ltRamp').value,
        pattern:document.getElementById('ltPattern').value,
        think_time_min:+document.getElementById('ltThinkMin').value,
        think_time_max:+document.getElementById('ltThinkMax').value,
        req_timeout:+document.getElementById('ltTimeout').value,
        per_vu_login:document.getElementById('ltPerVuLogin').checked,
        endpoints:eps,
    };
    document.getElementById('ltRunBtn').style.display='none';
    document.getElementById('ltStopBtn').style.display='';
    document.getElementById('ltChartEmpty').style.display='none';
    chartData=[];

    await fetch('/api/load/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
    ltPoll=setInterval(pollLoad,1000);
}
async function stopLoad(){
    await fetch('/api/load/stop',{method:'POST'});
    document.getElementById('ltRunBtn').style.display='';document.getElementById('ltStopBtn').style.display='none';
}

let chartData=[];
async function pollLoad(){
    const d=await(await fetch('/api/load/metrics')).json();
    if(!d)return;

    // Update live stats
    const m=d.metrics;
    const last=m.length?m[m.length-1]:{};
    document.getElementById('ls-vus').textContent=last.active_vus||0;
    document.getElementById('ls-rps').textContent=last.rps||0;
    document.getElementById('ls-avg').textContent=last.avg_rt||0;
    document.getElementById('ls-p95').textContent=last.p95||0;
    document.getElementById('ls-err').textContent=(last.err_rate||0)+'%';
    document.getElementById('ls-total').textContent=last.reqs_total||0;
    document.getElementById('ls-time').textContent=(last.ts||0)+'s';

    // Color VUs based on count
    const vEl=document.getElementById('ls-vus');
    vEl.style.color=(last.active_vus||0)>0?'#ff8f00':'#555';
    // Color errors
    const eEl=document.getElementById('ls-err');
    eEl.style.color=(last.err_rate||0)>5?'#ef5350':(last.err_rate||0)>0?'#ff8f00':'#66bb6a';

    // Draw chart
    chartData=m;
    drawChart();

    // Show summary if done
    if(!d.running&&d.summary){
        clearInterval(ltPoll);ltPoll=null;
        document.getElementById('ltRunBtn').style.display='';document.getElementById('ltStopBtn').style.display='none';
        renderLtSummary(d.summary);
    }
}

function drawChart(){
    const canvas=document.getElementById('ltChart');
    const rect=canvas.parentElement.getBoundingClientRect();
    canvas.width=rect.width;canvas.height=rect.height;
    const ctx=canvas.getContext('2d');
    const W=canvas.width,H=canvas.height;
    const d=chartData;if(!d.length)return;

    ctx.clearRect(0,0,W,H);

    // Grid
    ctx.strokeStyle='#1a1a1a';ctx.lineWidth=1;
    for(let i=0;i<5;i++){const y=H*0.1+i*(H*0.8/4);ctx.beginPath();ctx.moveTo(40,y);ctx.lineTo(W-10,y);ctx.stroke()}

    const pad={l:45,r:10,t:20,b:25};
    const cW=W-pad.l-pad.r,cH=H-pad.t-pad.b;
    const maxT=Math.max(...d.map(m=>m.ts),1);

    function x(ts){return pad.l+(ts/maxT)*cW}

    // Draw lines helper
    function drawLine(data,key,color,maxV){
        if(!maxV)maxV=Math.max(...data.map(m=>m[key]||0),1);
        ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();
        data.forEach((m,i)=>{
            const px=x(m.ts),py=pad.t+cH-(((m[key]||0)/maxV)*cH);
            if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);
        });
        ctx.stroke();
        return maxV;
    }

    // Y-axis labels
    ctx.fillStyle='#444';ctx.font='8px Consolas';

    // RPS (blue)
    const maxRps=drawLine(d,'rps','#42a5f5');
    ctx.fillStyle='#42a5f5';ctx.fillText(Math.round(maxRps)+' rps',2,pad.t+8);

    // Avg RT (green) - scale to chart
    const maxRt=drawLine(d,'avg_rt','#66bb6a');
    ctx.fillStyle='#66bb6a';ctx.fillText(Math.round(maxRt)+'ms',2,pad.t+cH/2);

    // Error rate (red) - 0-100 scale
    drawLine(d,'err_rate','#ef5350',100);

    // VUs (orange) - dashed
    const maxVu=Math.max(...d.map(m=>m.active_vus||0),1);
    ctx.strokeStyle='#ff8f00';ctx.lineWidth=1;ctx.setLineDash([4,3]);ctx.beginPath();
    d.forEach((m,i)=>{
        const px=x(m.ts),py=pad.t+cH-(((m.active_vus||0)/maxVu)*cH);
        if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);
    });
    ctx.stroke();ctx.setLineDash([]);

    // X-axis time labels
    ctx.fillStyle='#444';ctx.font='8px Consolas';
    const step=Math.max(1,Math.floor(d.length/8));
    for(let i=0;i<d.length;i+=step){
        ctx.fillText(d[i].ts+'s',x(d[i].ts)-8,H-5);
    }
}

function renderLtSummary(s){
    let h=`<div style="padding:10px">
    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:4px;margin-bottom:10px">
        <div class="lt-stat" title="Total API calls jo poore test mein bheje gaye">
            <div class="lt-v">${s.total_requests}</div><div class="lt-l">Requests <span class="lc-q" title="Total Requests - poore test mein kitni API calls bheji gayi. Zyada requests = zyada thorough test">?</span></div></div>
        <div class="lt-stat" title="Average Requests Per Second - server ne har second kitni requests handle ki">
            <div class="lt-v" style="color:#66bb6a">${s.avg_rps}</div><div class="lt-l">Avg RPS <span class="lc-q" title="Average Requests/Second - throughput measure. 10 RPS = server har second 10 requests handle kar raha. Zyada = better server capacity">?</span></div></div>
        <div class="lt-stat" title="Average Response Time - ek request ka average jawab dene ka time">
            <div class="lt-v">${s.avg_rt}ms</div><div class="lt-l">Avg RT <span class="lc-q" title="Average Response Time (milliseconds). 500ms = half second. < 1000ms = good. > 3000ms = slow. > 10000ms = very bad">?</span></div></div>
        <div class="lt-stat" title="95% requests ne isse kam time liya - real user experience ka best indicator">
            <div class="lt-v" style="color:#ff8f00">${s.p95}ms</div><div class="lt-l">P95 <span class="lc-q" title="95th Percentile - 100 users mein se 95 ko itna ya kam wait karna pada. Industry standard metric. < 2000ms = acceptable">?</span></div></div>
        <div class="lt-stat" title="99% requests ne isse kam time liya - worst case scenario (extreme slow requests)">
            <div class="lt-v" style="color:#ef5350">${s.p99}ms</div><div class="lt-l">P99 <span class="lc-q" title="99th Percentile - sirf 1% requests se zyada slow. Ye worst case hai. Agar P99 bohot high hai toh kuch requests bohot slow hain">?</span></div></div>
        <div class="lt-stat" title="Kitne % requests fail hui (server errors, timeouts)">
            <div class="lt-v" style="color:${s.error_rate>5?'#ef5350':'#66bb6a'}">${s.error_rate}%</div><div class="lt-l">Error Rate <span class="lc-q" title="Error Rate - 0% = perfect. < 1% = good. 1-5% = concerning. > 5% = server struggle kar raha hai load mein">?</span></div></div>
    </div>
    <div style="display:flex;gap:16px;font-size:10px;color:#999;margin-bottom:10px;flex-wrap:wrap;line-height:1.8">
        <span title="Test kitni der chala">Duration: <b>${s.duration}s</b></span>
        <span title="Maximum kitne virtual users the">Max VUs: <b>${s.max_vus}</b></span>
        <span title="Load pattern kaunsa tha">Pattern: <b>${s.pattern}</b></span>
        <span title="Sabse fast response">Min RT: <b style="color:#66bb6a">${s.min_rt}ms</b></span>
        <span title="Sabse slow response - bottleneck">Max RT: <b style="color:#ef5350">${s.max_rt}ms</b></span>
        <span title="Kitni alag-alag APIs test hui">Endpoints: <b>${s.endpoints_tested}</b></span>
        <span title="Fail hui / Total requests">Errors: <b style="color:${s.total_errors>0?'#ef5350':'#66bb6a'}">${s.total_errors}/${s.total_requests}</b></span>
    </div>`;

    // Status distribution
    if(s.status_dist){
        h+=`<div style="margin-bottom:10px;font-size:10px">
            <b style="color:#aaa">Status Distribution</b>
            <span class="lc-q" title="HTTP status codes ka breakdown. 200=success, 4xx=client error (wrong params), 5xx=server error (server crash)">?</span>
            <span style="color:#888;margin-left:6px">- server ne kaise respond kiya:</span><br>`;
        for(const[code,cnt] of Object.entries(s.status_dist).sort()){
            const c=+code>=500?'#ef5350':+code>=400?'#ff8f00':+code>=200?'#66bb6a':'#888';
            const label=+code==200?'OK':+code==0?'Timeout':+code==401?'Unauthorized':+code==402?'Payment Required':+code==403?'Forbidden':+code==404?'Not Found':+code==405?'Method Not Allowed':+code==429?'Rate Limited':+code>=500?'Server Error':'Other';
            h+=`<span style="background:#111;border:1px solid #222;padding:2px 8px;border-radius:3px;margin:2px 3px;display:inline-block" title="${label}">
                <span style="color:${c};font-weight:700;font-size:12px">${code}</span>
                <span style="color:#999;font-size:10px">${label}</span>
                <span style="color:#ccc;font-weight:600"> x${cnt}</span>
            </span>`;
        }
        h+=`</div>`;
    }

    // Per-endpoint table
    if(s.ep_breakdown&&s.ep_breakdown.length){
        h+=`<div style="margin-bottom:6px"><b style="color:#aaa;font-size:11px">Per-Endpoint Breakdown</b>
            <span style="color:#888;font-size:10px;margin-left:6px">- har API ki individual performance (slowest first)</span></div>`;
        h+=`<table class="lt-tbl"><thead><tr>
            <th>Endpoint (API name)</th>
            <th title="Is API ko total kitni baar call kiya gaya">Reqs</th>
            <th title="Kitni requests fail hui (server error / timeout)">Errs</th>
            <th title="Error percentage - 0% best, 5%+ bad">Err%</th>
            <th title="Average response time - avg kitna time lagta hai">Avg</th>
            <th title="50th Percentile - aadhe requests isse fast the. Median speed">P50 <span class="lc-q" title="Median response time. 50% requests isse fast, 50% isse slow. Best 'typical user' experience measure">?</span></th>
            <th title="95th Percentile - 95% requests isse fast the">P95 <span class="lc-q" title="95% users ko itna ya kam wait karna pada. Industry standard. Agar P95 > 3s toh problem hai">?</span></th>
            <th title="Sabse slow response - worst case">Max</th>
        </tr></thead><tbody>`;
        s.ep_breakdown.forEach(e=>{
            const ec=e.err_rate>10?'#ef5350':e.err_rate>0?'#ff8f00':'#66bb6a';
            const avgC=e.avg>5000?'#ef5350':e.avg>2000?'#ff8f00':'#66bb6a';
            const p95C=e.p95>5000?'#ef5350':e.p95>2000?'#ff8f00':'#42a5f5';
            h+=`<tr>
                <td style="color:#4fc3f7;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(e.name)}</td>
                <td>${e.count}</td>
                <td style="color:${ec}">${e.errors}</td>
                <td style="color:${ec};font-weight:600">${e.err_rate}%</td>
                <td style="color:${avgC}">${e.avg}ms</td>
                <td>${e.p50}ms</td>
                <td style="color:${p95C};font-weight:600">${e.p95}ms</td>
                <td style="color:#ef5350">${e.max}ms</td>
            </tr>`;
        });
        h+=`</tbody></table>`;

        // Performance summary hint
        const slowest=s.ep_breakdown[0];
        const fastest=s.ep_breakdown[s.ep_breakdown.length-1];
        if(slowest&&fastest){
            h+=`<div style="margin-top:8px;padding:8px;background:#111;border-radius:4px;font-size:10px;color:#aaa;border-left:3px solid #42a5f5">
                <b style="color:#ef5350">Slowest:</b> ${esc(slowest.name)} (avg ${slowest.avg}ms, p95 ${slowest.p95}ms) - optimize karo isko pehle<br>
                <b style="color:#66bb6a">Fastest:</b> ${esc(fastest.name)} (avg ${fastest.avg}ms) - ye theek hai
            </div>`;
        }
    }
    h+=`</div>`;
    document.getElementById('ltSummary').innerHTML=h;
}

// Init load test endpoint list - retry until data loaded
function initLtEps(){if(A.length>0)renderLtEps();else setTimeout(initLtEps,500)}
setTimeout(initLtEps,500);

// ═══ ADD API / COLLECTION / MANAGE ═══

function closeAllMdl(){
    document.querySelectorAll('.modal').forEach(m=>m.classList.remove('show'));
    document.getElementById('overlay').classList.remove('show');
}

// ── Add API ──
function showAddApi(){
    let opts='<option value="">-- Select Folder --</option>';
    F.forEach(f=>opts+=`<option value="${esc(f.name)}">${esc(f.name)}</option>`);
    document.getElementById('addApiFolder').innerHTML=opts;
    document.getElementById('addApiName').value='';
    document.getElementById('addApiBase').value='https://testingphp.zeep.live/api';
    document.getElementById('addApiEndpoint').value='';
    document.getElementById('addApiHeaders').value='';
    document.getElementById('addApiFolderNew').value='';
    document.getElementById('addApiBodyType').value='formdata';
    document.getElementById('addApiRawBody').value='';
    document.getElementById('addApiKVFields').innerHTML=`<div style="font-size:10px;color:#888;padding:2px 0;display:flex;gap:6px"><span style="flex:1">Key</span><span style="flex:1">Value</span><span style="width:20px"></span></div>`;
    addApiFieldRow();addApiFieldRow(); // 2 empty rows
    toggleAddApiBody();
    updateAddApiPreview();
    document.getElementById('addApiMdl').classList.add('show');
    document.getElementById('overlay').classList.add('show');
    // Live preview on any input change
    document.querySelectorAll('#addApiMdl input,#addApiMdl select,#addApiMdl textarea').forEach(el=>{
        el.addEventListener('input',updateAddApiPreview);el.addEventListener('change',updateAddApiPreview);
    });
}

function addApiFieldRow(k='',v=''){
    const div=document.getElementById('addApiKVFields');
    div.insertAdjacentHTML('beforeend',`<div style="display:flex;gap:6px;margin-top:3px" class="add-kv-row">
        <input class="lc-inp" style="flex:1" placeholder="key" value="${esc(k)}" oninput="updateAddApiPreview()">
        <input class="lc-inp" style="flex:1" placeholder="value" value="${esc(v)}" oninput="updateAddApiPreview()">
        <button class="x" onclick="this.parentElement.remove();updateAddApiPreview()" style="background:none;border:none;color:#ef5350;cursor:pointer;font-size:14px">&times;</button>
    </div>`);
}

function toggleAddApiBody(){
    const type=document.getElementById('addApiBodyType').value;
    const kvArea=document.getElementById('addApiBodyArea');
    const rawArea=document.getElementById('addApiRawBody');
    const grp=document.getElementById('addApiBodyGrp');
    if(type==='none'){grp.style.display='none'}
    else{grp.style.display=''}
    if(type==='raw'){kvArea.style.display='none';rawArea.style.display=''}
    else{kvArea.style.display='';rawArea.style.display='none'}
}

function updateAddApiPreview(){
    const method=document.getElementById('addApiMethod').value;
    const base=document.getElementById('addApiBase').value.replace(/\/$/,'');
    const ep=document.getElementById('addApiEndpoint').value.replace(/^\//,'');
    const full=base+(ep?'/'+ep:'');
    const bodyType=document.getElementById('addApiBodyType').value;
    const auth=document.getElementById('addApiAuth').value;

    let html=`<span style="color:#66bb6a;font-weight:700">${method}</span> <span style="color:#4fc3f7">${esc(full)}</span>`;
    html+=`<br><span style="color:#888">Body: </span><span style="color:#ffb74d">${bodyType}</span>`;
    html+=` | <span style="color:#888">Auth: </span><span style="color:${auth==='yes'?'#ffb74d':'#66bb6a'}">${auth==='yes'?'Bearer Token':'None'}</span>`;

    // Show fields preview
    if(bodyType!=='none'&&bodyType!=='raw'){
        const rows=document.querySelectorAll('#addApiKVFields .add-kv-row');
        const fields=[];
        rows.forEach(r=>{
            const inputs=r.querySelectorAll('input');
            if(inputs[0].value.trim())fields.push(inputs[0].value.trim()+'='+inputs[1].value.trim());
        });
        if(fields.length)html+=`<br><span style="color:#888">Fields: </span><span style="color:#ccc">${fields.join(' & ')}</span>`;
    }

    document.getElementById('addApiPreview').innerHTML=html;
}

async function submitAddApi(){
    const folder=document.getElementById('addApiFolderNew').value.trim()||document.getElementById('addApiFolder').value;
    const name=document.getElementById('addApiName').value.trim();
    const method=document.getElementById('addApiMethod').value;
    const base=document.getElementById('addApiBase').value.replace(/\/$/,'');
    const endpoint=document.getElementById('addApiEndpoint').value.replace(/^\//,'');
    const url=base+(endpoint?'/'+endpoint:'');
    const auth=document.getElementById('addApiAuth').value==='yes';
    const bodyType=document.getElementById('addApiBodyType').value;
    const headerText=document.getElementById('addApiHeaders').value.trim();

    if(!name)return alert('API name is required');
    if(!endpoint)return alert('Endpoint path is required');

    // Parse body
    let bodyFields=[];
    let rawBody='';
    if(bodyType==='raw'){
        rawBody=document.getElementById('addApiRawBody').value.trim();
    }else if(bodyType!=='none'){
        document.querySelectorAll('#addApiKVFields .add-kv-row').forEach(r=>{
            const inputs=r.querySelectorAll('input');
            if(inputs[0].value.trim())bodyFields.push({key:inputs[0].value.trim(),value:inputs[1].value.trim(),type:'text'});
        });
    }

    // Parse headers
    const headers=[];
    if(auth)headers.push({key:'Authorization',value:'Bearer {{auth_token}}',type:'text'});
    headerText.split('\n').forEach(line=>{
        const eq=line.indexOf('=');
        if(eq>0)headers.push({key:line.substring(0,eq).trim(),value:line.substring(eq+1).trim(),type:'text'});
    });

    const r=await fetch('/api/endpoints/add',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({folder:folder||'Custom APIs',name,method,url,needs_auth:auth,headers,body_fields:bodyFields,body_type:bodyType,raw_body:rawBody})});
    const res=await r.json();
    if(res.ok){
        showToast('API added: '+name);
        closeAllMdl();
        await reloadData();
    }else{
        alert('Error: '+(res.error||'unknown'));
    }
}

// ── Add Collection ──
function showAddCollection(){
    document.getElementById('collJson').value='';
    document.getElementById('collPreview').textContent='';
    document.getElementById('collFile').value='';
    document.getElementById('addCollMdl').classList.add('show');
    document.getElementById('overlay').classList.add('show');
}

function previewColl(input){
    if(!input.files.length)return;
    const reader=new FileReader();
    reader.onload=e=>{
        document.getElementById('collJson').value=e.target.result;
        try{
            const d=JSON.parse(e.target.result);
            let cnt=0;
            const countItems=(items)=>{items.forEach(it=>{if(it.item)countItems(it.item);else if(it.request)cnt++})};
            countItems(d.item||[]);
            document.getElementById('collPreview').innerHTML=`<span style="color:#66bb6a">Collection: <b>${esc(d.info?.name||'Unknown')}</b> | ${cnt} endpoints found</span>`;
        }catch(er){
            document.getElementById('collPreview').innerHTML=`<span style="color:#ef5350">Invalid JSON: ${esc(er.message)}</span>`;
        }
    };
    reader.readAsText(input.files[0]);
}

async function submitCollection(mode){
    const json=document.getElementById('collJson').value.trim();
    if(!json)return alert('Paste or upload a collection JSON first');
    try{JSON.parse(json)}catch(e){return alert('Invalid JSON: '+e.message)}

    const r=await fetch('/api/collection/import',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({json,mode})});
    const res=await r.json();
    if(res.ok){
        showToast(res.message||'Collection imported');
        closeAllMdl();
        await reloadData();
    }else{
        alert('Error: '+(res.error||'unknown'));
    }
}

// ── Manage ──
let manageSel={};
function showManage(){
    manageSel={};
    let h='';
    F.forEach((f,fi)=>{
        h+=`<div style="padding:6px 10px;background:#111;border-bottom:1px solid #222;display:flex;align-items:center;gap:6px;font-weight:600;font-size:11px;color:#aaa" class="mg-folder" data-name="${esc(f.name)}">
            <input type="checkbox" onchange="toggleManageFolder(${fi},this.checked)" id="mf-${fi}">
            <span style="flex:1">${esc(f.name)}</span>
            <span style="color:#999;font-size:10px">${f.endpoints.length} APIs</span>
            <button class="btn-sm" style="background:#c62828;color:#fff;font-size:9px;padding:2px 6px" onclick="event.stopPropagation();deleteFolder(${fi})">Delete Folder</button>
        </div>`;
        f.endpoints.forEach((ep,ei)=>{
            const k=fi+'-'+ei;
            h+=`<div class="mg-ep" style="padding:4px 10px 4px 28px;display:flex;align-items:center;gap:6px;font-size:10px;color:#ccc;border-bottom:1px solid #1a1a1a" data-name="${esc(ep.name.toLowerCase())}">
                <input type="checkbox" id="mg-${k}" onchange="manageSel['${k}']=this.checked;updManageCnt()">
                <span class="bge ${ep.method}">${ep.method}</span>
                <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(ep.name)}</span>
                ${ep.needs_auth?'<span style="color:#ffb74d;font-size:9px">TOKEN</span>':''}
                <button class="btn-sm" style="font-size:9px;padding:1px 5px;background:#c62828;color:#fff" onclick="event.stopPropagation();deleteSingle(${fi},${ei})">x</button>
            </div>`;
        });
    });
    document.getElementById('manageList').innerHTML=h;
    document.getElementById('manageMdl').classList.add('show');
    document.getElementById('overlay').classList.add('show');
    updManageCnt();
}

function toggleManageFolder(fi,checked){
    F[fi].endpoints.forEach((ep,ei)=>{
        const k=fi+'-'+ei;
        manageSel[k]=checked;
        const cb=document.getElementById('mg-'+k);
        if(cb)cb.checked=checked;
    });
    updManageCnt();
}

function updManageCnt(){
    let n=0;for(let k in manageSel)if(manageSel[k])n++;
    document.getElementById('manageSelCnt').textContent=n+' selected';
}

function filterManage(q){
    q=q.toLowerCase();
    document.querySelectorAll('.mg-ep').forEach(el=>{
        el.style.display=(!q||el.dataset.name.includes(q))?'':'none';
    });
    document.querySelectorAll('.mg-folder').forEach(el=>{
        el.style.display=(!q||el.dataset.name.toLowerCase().includes(q))?'':'none';
    });
}

async function deleteSingle(fi,ei){
    const ep=F[fi].endpoints[ei];
    if(!confirm('Delete "'+ep.name+'"?'))return;
    const r=await fetch('/api/endpoints/delete',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({names:[ep.name]})});
    const res=await r.json();
    if(res.ok){showToast('Deleted: '+ep.name);closeAllMdl();await reloadData()}
}

async function deleteFolder(fi){
    const f=F[fi];
    if(!confirm('Delete entire folder "'+f.name+'" with '+f.endpoints.length+' APIs?'))return;
    const names=f.endpoints.map(e=>e.name);
    const r=await fetch('/api/endpoints/delete',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({names,folder:f.name})});
    const res=await r.json();
    if(res.ok){showToast('Deleted folder: '+f.name);closeAllMdl();await reloadData()}
}

async function deleteSelected(){
    const names=[];
    for(let k in manageSel){
        if(!manageSel[k])continue;
        const[fi,ei]=k.split('-').map(Number);
        names.push(F[fi].endpoints[ei].name);
    }
    if(!names.length)return alert('Select APIs to delete first');
    if(!confirm('Delete '+names.length+' selected APIs?'))return;
    const r=await fetch('/api/endpoints/delete',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({names})});
    const res=await r.json();
    if(res.ok){showToast('Deleted '+names.length+' APIs');closeAllMdl();await reloadData()}
}

async function exportCollection(){
    const r=await fetch('/api/collection/export');
    const data=await r.json();
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='ZeepLive_Collection_Export.json';a.click();
    URL.revokeObjectURL(url);
    showToast('Collection exported!');
}

async function reloadData(){
    const d=await(await fetch('/api/data')).json();
    F=d.folders;A=d.all_endpoints;V=d.variables;
    document.getElementById('epCnt').textContent=A.length+' endpoints';
    renderSide();renderSel();renderLtEps();
}

// ── Change Password ──
function showChangePw(){
    const h=`<div style="padding:14px">
        <div class="lc-grp"><label class="lc-l">Current Password</label>
            <input type="password" id="cpCurrent" class="lc-inp" style="width:100%" placeholder="Enter current password"></div>
        <div class="lc-grp"><label class="lc-l">New Password</label>
            <input type="password" id="cpNew" class="lc-inp" style="width:100%" placeholder="Enter new password (min 4 chars)"></div>
        <div class="lc-grp"><label class="lc-l">Confirm New Password</label>
            <input type="password" id="cpConfirm" class="lc-inp" style="width:100%" placeholder="Re-enter new password"></div>
        <div id="cpErr" style="color:#ef5350;font-size:11px;min-height:16px;margin-bottom:6px"></div>
        <button onclick="submitChangePw()" style="width:100%;padding:10px;background:#1565c0;color:#fff;border:none;border-radius:4px;font-weight:700;cursor:pointer;font-size:12px">Change Password</button>
    </div>`;
    document.getElementById('varsB').innerHTML=h;
    document.querySelector('#varsMdl .modal-h h3').textContent='Change Password';
    document.getElementById('varsMdl').classList.add('show');
    document.getElementById('overlay').classList.add('show');
}
async function submitChangePw(){
    const cur=document.getElementById('cpCurrent').value;
    const nw=document.getElementById('cpNew').value;
    const cf=document.getElementById('cpConfirm').value;
    if(!cur){document.getElementById('cpErr').textContent='Enter current password';return}
    if(nw.length<4){document.getElementById('cpErr').textContent='New password min 4 characters';return}
    if(nw!==cf){document.getElementById('cpErr').textContent='Passwords do not match';return}
    const r=await fetch('/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current:cur,new:nw})});
    const res=await r.json();
    if(res.ok){showToast('Password changed!');closeVars()}
    else{document.getElementById('cpErr').textContent=res.error||'Failed'}
}

function synHL(j){j=esc(j);return j.replace(/("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,m=>{let c='jn';if(/^"/.test(m)){c=/:$/.test(m)?'jk':'js'}else if(/true|false/.test(m))c='jb';else if(/null/.test(m))c='jl';return'<span class="'+c+'">'+m+'</span>'})}
function fmtB(b){if(!b)return'0B';if(b<1024)return b+'B';return(b/1024).toFixed(1)+'KB'}
</script></body></html>'''

# ────────────────────── Routes ──────────────────────

@app.before_request
def auth_guard():
    """Protect ALL routes except /login and static."""
    open_paths = ('/login',)
    if request.path in open_paths:
        return None
    if not check_auth():
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
        return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    ip = request.remote_addr
    if request.method == 'GET':
        if check_auth():
            return redirect('/')
        locked = is_locked_out(ip)
        remaining = 0
        if locked:
            remaining = int(LOGIN_LOCKOUT_SEC - (time.time() - _login_attempts[ip]['last_time']))
        return render_template_string(LOGIN_PAGE, error='', locked=locked, lockout_remaining=remaining)

    # POST - login attempt
    if is_locked_out(ip):
        remaining = int(LOGIN_LOCKOUT_SEC - (time.time() - _login_attempts[ip]['last_time']))
        return render_template_string(LOGIN_PAGE, error='', locked=True, lockout_remaining=remaining)

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    pw_hash = hashlib.sha256(password.encode()).hexdigest()

    if username in AUTH_USERS and AUTH_USERS[username] == pw_hash:
        session['logged_in'] = True
        session['user'] = username
        session['login_time'] = datetime.now().isoformat()
        session.permanent = True
        clear_login_attempts(ip)
        return redirect('/')
    else:
        record_failed_login(ip)
        attempts = _login_attempts.get(ip, {}).get('count', 0)
        remaining = MAX_LOGIN_ATTEMPTS - attempts
        err = f'Invalid username or password. {remaining} attempts left.' if remaining > 0 else ''
        locked = is_locked_out(ip)
        lock_remaining = LOGIN_LOCKOUT_SEC if locked else 0
        return render_template_string(LOGIN_PAGE, error=err, locked=locked, lockout_remaining=lock_remaining)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/change-password', methods=['POST'])
def change_password():
    if not check_auth():
        return jsonify({'ok': False, 'error': 'Not logged in'}), 401
    d = request.json
    current = d.get('current', '')
    new_pw = d.get('new', '')
    if len(new_pw) < 4:
        return jsonify({'ok': False, 'error': 'New password too short (min 4)'})
    username = session.get('user', '')
    current_hash = hashlib.sha256(current.encode()).hexdigest()
    if AUTH_USERS.get(username) != current_hash:
        return jsonify({'ok': False, 'error': 'Current password is wrong'})
    new_hash = hashlib.sha256(new_pw.encode()).hexdigest()
    AUTH_USERS[username] = new_hash
    # Save to .env file
    _save_env()
    return jsonify({'ok': True, 'message': 'Password changed!'})

def _save_env():
    """Save current users to .env file."""
    with open(ENV_FILE, 'w') as f:
        f.write("# ZeepLive Test Lab - Auth Credentials\n")
        f.write(f"# Updated: {datetime.now().isoformat()}\n\n")
        f.write(f"SECRET_KEY={app.secret_key}\n\n")
        for username, pw_hash in AUTH_USERS.items():
            f.write(f"USER_{username}={pw_hash}\n")

@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/api/data')
def api_data():
    return jsonify({'folders': STATE['folders'], 'all_endpoints': STATE['all_endpoints'], 'variables': STATE['variables']})

@app.route('/api/send', methods=['POST'])
def api_send():
    d = request.json
    meth, url = d['method'], d['url']
    hd, bd = d.get('headers', {}), d.get('body', {})
    tok = STATE['variables'].get('auth_token', '')
    if d.get('needs_auth', True) and tok:
        if 'Authorization' in hd: hd['Authorization'] = f'Bearer {tok}'
        elif 'device-manual-login' not in url: hd['Authorization'] = f'Bearer {tok}'
    if hd.get('Content-Type') == 'application/json' and isinstance(bd, dict):
        del hd['Content-Type']
    start = time.time(); uv = {}
    try:
        resp = requests.request(meth, url, headers=hd, data=bd, verify=False, timeout=30)
        if resp.status_code == 405 and meth == 'POST':
            resp = requests.get(url, headers=hd, params=bd if isinstance(bd, dict) else {}, verify=False, timeout=30)
        el = int((time.time() - start) * 1000)
        mf = parse_error_fields(resp.text); ae = None
        try:
            rj = resp.json()
            if isinstance(rj, dict) and rj.get('success') == False: ae = rj.get('error', '')
            if isinstance(rj, dict) and rj.get('success') and isinstance(rj.get('result'), dict):
                for k in ('token', 'profile_id', 'name', 'gender', 'mobile'):
                    if k in rj['result'] and rj['result'][k]:
                        vk = 'auth_token' if k == 'token' else k
                        STATE['variables'][vk] = str(rj['result'][k]); uv[vk] = str(rj['result'][k])
        except: pass
        return jsonify({'status_code': resp.status_code, 'body': resp.text, 'response_headers': dict(resp.headers),
                        'time_ms': el, 'size': len(resp.content), 'updated_variables': uv or None,
                        'missing_fields': mf, 'api_error': ae})
    except Exception as e:
        return jsonify({'status_code': 0, 'body': str(e), 'response_headers': {}, 'time_ms': int((time.time()-start)*1000),
                        'size': 0, 'updated_variables': None, 'missing_fields': [], 'api_error': None})

@app.route('/api/variables', methods=['POST'])
def api_vars():
    d = request.json; STATE['variables'][d['key']] = d['value']; return jsonify({'ok': True})

@app.route('/api/history')
def api_hist(): return jsonify(STATE['history'][-50:])

@app.route('/api/preset/<t>')
def api_preset(t):
    presets = {
        'full': ['Login User (Device Manual Login)','Get Profile Data','Get Profile Details',
                 'Get User Account Details','Get App Settings','Get Wallet Balance (Points)',
                 'Get Followers Count 1','Get Gifts','Get Broadcast List New','Party Room List',
                 'Moment List','Get Call Price List','Get Recharge List','Get Country List',
                 'Get Banner List','Get Video Call History','Get Wallet History Latest',
                 'Get Level Data','Check App Status Zeeplive','Search User'],
        'auth': ['Login User (Device Manual Login)','Get Profile Data','Get Profile Details',
                 'Get User Details','Get User Account Details','Check User Ban Status'],
    }
    return jsonify(presets.get(t, []))

@app.route('/api/run-suite', methods=['POST'])
def api_run():
    STATE['suite_progress']['running'] = False; time.sleep(0.3)
    threading.Thread(target=run_suite_bg, args=(request.json,), daemon=True).start()
    return jsonify({'ok': True})

@app.route('/api/stop-suite', methods=['POST'])
def api_stop():
    STATE['suite_progress']['running'] = False; return jsonify({'ok': True})

@app.route('/api/suite-progress')
def api_prog():
    d = dict(STATE['suite_progress']); d['paused'] = STATE['suite_paused']; d['pause_data'] = STATE['pause_data']
    return jsonify(d)

@app.route('/api/suite-resume', methods=['POST'])
def api_resume():
    STATE['extra_fields_response'] = request.json; STATE['suite_paused'] = False; return jsonify({'ok': True})

@app.route('/api/suite-results')
def api_results(): return jsonify(STATE['suite_results'][-20:])

# ── Load Test Routes ──
# ── Add/Delete/Import/Export Endpoints ──

@app.route('/api/endpoints/add', methods=['POST'])
def api_ep_add():
    d = request.json
    name = d.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Name required'})

    # Check duplicate
    if any(e['name'] == name for e in STATE['all_endpoints']):
        return jsonify({'ok': False, 'error': f'API "{name}" already exists'})

    folder = d.get('folder', 'Custom APIs').strip() or 'Custom APIs'
    headers = d.get('headers', [])
    body_fields = d.get('body_fields', [])
    body_type = d.get('body_type', 'formdata')
    raw_body = d.get('raw_body', '')

    # Build body based on type
    if body_type == 'raw':
        body = {'mode': 'raw', 'raw': raw_body}
    elif body_type == 'none':
        body = {}
    elif body_type == 'urlencoded':
        body = {'mode': 'urlencoded', 'urlencoded': body_fields}
    else:  # formdata
        body = {'mode': 'formdata', 'formdata': body_fields} if body_fields else {}

    ep = {
        'name': name, 'folder': folder,
        'method': d.get('method', 'POST'), 'url': d.get('url', ''),
        'headers': headers,
        'body': body,
        'auth': {} if d.get('needs_auth') else {'type': 'noauth'},
        'event': [], 'needs_auth': d.get('needs_auth', True),
    }
    STATE['all_endpoints'].append(ep)

    # Add to folder
    existing_folder = next((f for f in STATE['folders'] if f['name'] == folder), None)
    if existing_folder:
        existing_folder['endpoints'].append(ep)
    else:
        STATE['folders'].append({'name': folder, 'endpoints': [ep]})

    return jsonify({'ok': True, 'message': f'Added: {name}'})

@app.route('/api/endpoints/update', methods=['POST'])
def api_ep_update():
    d = request.json
    name = d.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Name required'})

    # Find the endpoint
    ep = None
    for e in STATE['all_endpoints']:
        if e['name'] == name:
            ep = e; break
    if not ep:
        return jsonify({'ok': False, 'error': f'Endpoint "{name}" not found'})

    # Update fields
    if 'method' in d: ep['method'] = d['method']
    if 'url' in d: ep['url'] = d['url']
    if 'headers' in d: ep['headers'] = d['headers']
    if 'needs_auth' in d: ep['needs_auth'] = d['needs_auth']
    if 'body_fields' in d:
        body_fields = d['body_fields']
        mode = d.get('body_type', 'formdata')
        if mode == 'raw':
            ep['body'] = {'mode': 'raw', 'raw': d.get('raw_body', '')}
        elif mode == 'none':
            ep['body'] = {}
        elif mode == 'urlencoded':
            ep['body'] = {'mode': 'urlencoded', 'urlencoded': body_fields}
        else:
            ep['body'] = {'mode': 'formdata', 'formdata': body_fields}

    # Also update in folders
    for f in STATE['folders']:
        for i, fe in enumerate(f['endpoints']):
            if fe['name'] == name:
                f['endpoints'][i] = ep

    return jsonify({'ok': True, 'message': f'Updated: {name}'})

@app.route('/api/endpoints/delete', methods=['POST'])
def api_ep_delete():
    d = request.json
    names = set(d.get('names', []))
    folder_to_delete = d.get('folder', '')

    if folder_to_delete and not names:
        # Delete entire folder
        STATE['folders'] = [f for f in STATE['folders'] if f['name'] != folder_to_delete]
        STATE['all_endpoints'] = [e for e in STATE['all_endpoints'] if e['folder'] != folder_to_delete]
        return jsonify({'ok': True, 'message': f'Deleted folder: {folder_to_delete}'})

    # Delete by names
    STATE['all_endpoints'] = [e for e in STATE['all_endpoints'] if e['name'] not in names]
    for f in STATE['folders']:
        f['endpoints'] = [e for e in f['endpoints'] if e['name'] not in names]
    # Remove empty folders
    STATE['folders'] = [f for f in STATE['folders'] if f['endpoints']]
    return jsonify({'ok': True, 'message': f'Deleted {len(names)} APIs'})

@app.route('/api/collection/import', methods=['POST'])
def api_coll_import():
    d = request.json
    mode = d.get('mode', 'merge')
    try:
        coll = json.loads(d.get('json', '{}'))
    except:
        return jsonify({'ok': False, 'error': 'Invalid JSON'})

    if 'item' not in coll:
        return jsonify({'ok': False, 'error': 'Not a valid Postman collection (no "item" field)'})

    # Import variables if present
    for v in coll.get('variable', []):
        if v.get('key') and v.get('value'):
            STATE['variables'][v['key']] = v['value']

    if mode == 'replace':
        STATE['folders'] = []
        STATE['all_endpoints'] = []

    # Parse items
    new_folders, new_eps = [], []
    _parse(coll['item'], new_folders, new_eps)

    if mode == 'merge':
        existing_names = {e['name'] for e in STATE['all_endpoints']}
        added = 0
        for ep in new_eps:
            if ep['name'] not in existing_names:
                STATE['all_endpoints'].append(ep)
                existing_names.add(ep['name'])
                added += 1
                # Add to folder
                existing_folder = next((f for f in STATE['folders'] if f['name'] == ep['folder']), None)
                if existing_folder:
                    if not any(e['name'] == ep['name'] for e in existing_folder['endpoints']):
                        existing_folder['endpoints'].append(ep)
                else:
                    STATE['folders'].append({'name': ep['folder'], 'endpoints': [ep]})
        return jsonify({'ok': True, 'message': f'Merged: {added} new APIs added ({len(new_eps) - added} duplicates skipped)'})
    else:
        STATE['folders'] = new_folders
        STATE['all_endpoints'] = new_eps
        return jsonify({'ok': True, 'message': f'Replaced: {len(new_eps)} APIs in {len(new_folders)} folders'})

@app.route('/api/collection/export')
def api_coll_export():
    """Export current endpoints as Postman-compatible collection JSON."""
    items = []
    for f in STATE['folders']:
        folder_item = {'name': f['name'], 'item': []}
        for ep in f['endpoints']:
            req_item = {
                'name': ep['name'],
                'request': {
                    'method': ep['method'],
                    'header': ep.get('headers', []),
                    'url': {'raw': ep['url']},
                    'body': ep.get('body', {}),
                    'auth': ep.get('auth', {}),
                },
                'response': [],
            }
            folder_item['item'].append(req_item)
        items.append(folder_item)

    collection = {
        'info': {
            'name': 'ZeepLive API Collection (Exported)',
            'schema': 'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
        },
        'variable': [{'key': k, 'value': v, 'type': 'string'} for k, v in STATE['variables'].items()],
        'item': items,
    }
    return jsonify(collection)

@app.route('/api/custom-fields', methods=['POST'])
def api_custom_fields():
    """Sync custom fields from frontend to backend."""
    STATE['custom_fields'] = request.json or {}
    return jsonify({'ok': True})

@app.route('/api/load/start', methods=['POST'])
def api_load_start():
    STATE['load']['running'] = False
    time.sleep(0.5)
    cfg = request.json
    threading.Thread(target=_load_test_runner, args=(cfg,), daemon=True).start()
    return jsonify({'ok': True})

@app.route('/api/load/stop', methods=['POST'])
def api_load_stop():
    STATE['load']['running'] = False
    return jsonify({'ok': True})

@app.route('/api/load/metrics')
def api_load_metrics():
    L = STATE['load']
    return jsonify({
        'running': L['running'],
        'metrics': L['metrics'][-300:],
        'summary': L['summary'],
    })

# Initialize on import (needed for gunicorn)
load_collection()
init_auth()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5555))
    host = '0.0.0.0' if os.environ.get('RAILWAY_ENVIRONMENT') else '127.0.0.1'
    print(f"\n  ZeepLive Test Lab | {len(STATE['all_endpoints'])} APIs | http://localhost:{port}")
    print(f"  Login required | Host: {host}:{port}\n")
    app.run(host=host, port=port, debug=False)
