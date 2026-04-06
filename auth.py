#!/usr/bin/env python3
"""
auth.py
=======
Authentication layer for the Etsy shop management tool.
Handles login, TOTP 2FA, user management, and session tokens.
Runs on port 8000 and proxies authenticated requests to server.py on 8080.
"""

import os, json, time, secrets, bcrypt, pyotp, qrcode, jwt, io, base64
from functools import wraps
from flask import Flask, request, jsonify, redirect, make_response, Response
from flask_cors import CORS
import requests as req

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
JWT_FILE   = os.path.join(BASE_DIR, '.jwt_secret')
APP_NAME   = 'Etsy Shop Manager'
BACKEND    = 'http://127.0.0.1:8080'
JWT_EXPIRY = 60 * 60 * 12  # 12 hours

app = Flask(__name__)
CORS(app)

# Persist JWT secret so sessions survive restarts
def get_jwt_secret():
    if os.path.exists(JWT_FILE):
        return open(JWT_FILE).read().strip()
    secret = secrets.token_hex(32)
    open(JWT_FILE, 'w').write(secret)
    return secret

JWT_SECRET = get_jwt_secret()

# ── User store ────────────────────────────────────────────────────────────────
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE) as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

# ── JWT helpers ───────────────────────────────────────────────────────────────
def make_token(username, role):
    payload = {
        'sub':  username,
        'role': role,
        'exp':  int(time.time()) + JWT_EXPIRY,
        'iat':  int(time.time()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except Exception:
        return None

def get_token():
    token = request.cookies.get('auth_token')
    if not token:
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
    return token

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Allow oauth token exchange without auth
        if request.path.startswith("/api/") or request.path == "/health":
            return f(*args, **kwargs)
        if request.path.startswith("/api/oauth"):
            return f(*args, **kwargs)
        payload = verify_token(get_token())
        if not payload:
            if request.path.startswith('/api') or request.headers.get('X-Requested-With') or request.is_json:
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect('/login')
        request.user = payload
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = verify_token(get_token())
        if not payload:
            return jsonify({'error': 'Unauthorized'}), 401
        if payload.get('role') != 'admin':
            return jsonify({'error': 'Admin only'}), 403
        request.user = payload
        return f(*args, **kwargs)
    return decorated

# ── QR code helper ────────────────────────────────────────────────────────────
def make_qr(username, totp_secret):
    uri = pyotp.TOTP(totp_secret).provisioning_uri(
        name=username, issuer_name=APP_NAME
    )
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()

# ── Login page ────────────────────────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Etsy Shop Manager - Sign In</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f0e8;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#fff;border-radius:16px;padding:40px;width:100%;max-width:400px;box-shadow:0 4px 40px rgba(28,20,16,.12);border:1.5px solid #e8dfd0}
.logo{font-family:Georgia,serif;font-size:22px;font-weight:700;color:#1a3d28;text-align:center;margin-bottom:6px}
.sub{text-align:center;font-size:13px;color:#8a7560;margin-bottom:28px}
.field{margin-bottom:16px}
label{display:block;font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:#8a7560;margin-bottom:6px}
input{width:100%;padding:11px 14px;border:1.5px solid #d4c8b4;border-radius:8px;font-size:14px;font-family:inherit;transition:.15s;background:#fffdf9}
input:focus{outline:none;border-color:#2d5a3d;box-shadow:0 0 0 3px rgba(45,90,61,.1)}
.btn{width:100%;padding:12px;background:#2d5a3d;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;font-family:inherit;transition:.15s;margin-top:4px}
.btn:hover{background:#1a3d28}
.btn:disabled{background:#d4c8b4;cursor:not-allowed}
.error{background:#fef2f2;border:1.5px solid #fca5a5;border-radius:8px;padding:10px 14px;font-size:13px;color:#b91c1c;margin-bottom:16px;display:none}
.step{display:none}
.step.on{display:block}
.hint{font-size:12px;color:#8a7560;text-align:center;margin-top:10px;line-height:1.5}
</style>
</head>
<body>
<div class="card">
  <div class="logo">Etsy Shop Manager</div>
  <div class="sub">Etsy Management Tool</div>
  <div class="error" id="err"></div>
  <div class="step on" id="step1">
    <div class="field"><label>Username</label><input id="un" type="text" autocomplete="username" placeholder="Enter username"></div>
    <div class="field"><label>Password</label><input id="pw" type="password" autocomplete="current-password" placeholder="Enter password"></div>
    <button class="btn" id="btn1" onclick="doLogin()">Continue</button>
  </div>
  <div class="step" id="step2">
    <div class="field">
      <label>Authenticator Code</label>
      <input id="totp" type="text" inputmode="numeric" maxlength="6" placeholder="6-digit code" autocomplete="one-time-code">
    </div>
    <button class="btn" id="btn2" onclick="doTotp()">Sign In</button>
    <div class="hint">Open Google Authenticator and enter the 6-digit code for Etsy Shop Manager</div>
  </div>
</div>
<script>
let _u='',_p='';
document.addEventListener('keydown',e=>{if(e.key==='Enter'){if(document.getElementById('step1').classList.contains('on'))doLogin();else doTotp();}});
async function doLogin(){
  const u=document.getElementById('un').value.trim(),p=document.getElementById('pw').value;
  if(!u||!p){err('Please enter username and password');return;}
  const btn=document.getElementById('btn1');btn.disabled=true;btn.textContent='Checking...';clearErr();
  try{
    const r=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
    const d=await r.json();
    if(r.ok&&d.next==='totp'){_u=u;_p=p;document.getElementById('step1').classList.remove('on');document.getElementById('step2').classList.add('on');setTimeout(()=>document.getElementById('totp').focus(),100);}
    else err(d.error||'Invalid credentials');
  }catch(e){err('Connection error');}
  finally{btn.disabled=false;btn.textContent='Continue';}
}
async function doTotp(){
  const code=document.getElementById('totp').value.trim();
  if(code.length!==6){err('Enter the 6-digit code');return;}
  const btn=document.getElementById('btn2');btn.disabled=true;btn.textContent='Verifying...';clearErr();
  try{
    const r=await fetch('/auth/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:_u,password:_p,totp:code})});
    const d=await r.json();
    if(r.ok&&d.ok){window.location.href='/';}
    else{err(d.error||'Invalid code');document.getElementById('totp').value='';document.getElementById('totp').focus();}
  }catch(e){err('Connection error');}
  finally{btn.disabled=false;btn.textContent='Sign In';}
}
function err(msg){const e=document.getElementById('err');e.textContent=msg;e.style.display='block';}
function clearErr(){document.getElementById('err').style.display='none';}
</script>
</body>
</html>"""

# ── Admin page ────────────────────────────────────────────────────────────────
ADMIN_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Etsy Shop Manager - User Management</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f0e8;min-height:100vh;padding:30px 20px}
.wrap{max-width:600px;margin:0 auto}
h1{font-family:Georgia,serif;color:#1a3d28;font-size:24px;margin-bottom:4px}
.sub{color:#8a7560;font-size:13px;margin-bottom:24px}
.card{background:#fff;border-radius:12px;padding:24px;margin-bottom:16px;border:1.5px solid #e8dfd0}
h2{font-size:14px;font-weight:700;margin-bottom:14px;color:#1c1410;text-transform:uppercase;letter-spacing:.5px}
.field{margin-bottom:12px}
label{display:block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#8a7560;margin-bottom:5px}
input,select{width:100%;padding:9px 12px;border:1.5px solid #d4c8b4;border-radius:7px;font-size:13px;font-family:inherit;background:#fffdf9}
input:focus,select:focus{outline:none;border-color:#2d5a3d}
.btn{padding:9px 18px;background:#2d5a3d;color:#fff;border:none;border-radius:7px;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit}
.btn-sm{padding:5px 11px;font-size:11px}
.btn-red{background:#b02020}
.btn-amber{background:#c8860a}
.user-row{display:flex;align-items:center;justify-content:space-between;padding:11px 0;border-bottom:1px solid #f0ebe1;gap:8px}
.user-row:last-child{border:none}
.badge{padding:2px 8px;border-radius:20px;font-size:10px;font-weight:700}
.badge-admin{background:#e8f0ea;color:#2d5a3d}
.badge-user{background:#f0ebe1;color:#8a7560}
.qr-wrap{text-align:center;padding:16px 0}
.qr-wrap img{border-radius:8px;border:1.5px solid #e8dfd0;max-width:220px}
.secret{font-family:monospace;font-size:12px;background:#f5f0e8;padding:8px 12px;border-radius:6px;margin-top:8px;word-break:break-all;text-align:center;color:#1c1410}
.msg{padding:9px 13px;border-radius:7px;font-size:13px;margin-bottom:12px;display:none}
.msg.ok{background:#f0faf4;border:1.5px solid #b2d8c0;color:#1a4a2a}
.msg.err{background:#fef2f2;border:1.5px solid #fca5a5;color:#b91c1c}
.back{display:inline-block;margin-bottom:20px;color:#2d5a3d;font-size:13px;font-weight:700;text-decoration:none}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">Back to Tool</a>
  <h1>User Management</h1>
  <div class="sub">Add users, manage access, reset 2FA</div>

  <div class="card">
    <h2>Add New User</h2>
    <div class="msg" id="addMsg"></div>
    <div class="field"><label>Username</label><input id="newUser" placeholder="e.g. aatif"></div>
    <div class="field"><label>Password</label><input id="newPass" type="password" placeholder="Strong password"></div>
    <div class="field"><label>Role</label>
      <select id="newRole"><option value="user">User</option><option value="admin">Admin</option></select>
    </div>
    <button class="btn" onclick="addUser()">Add User</button>
  </div>

  <div class="card">
    <h2>Current Users</h2>
    <div id="userList">Loading...</div>
  </div>

  <div class="card" id="qrCard" style="display:none">
    <h2>Scan QR Code</h2>
    <p style="font-size:13px;color:#8a7560;margin-bottom:12px">Have the user scan this with Google Authenticator. This code is shown only once.</p>
    <div class="qr-wrap"><img id="qrImg" src="" alt="QR Code"></div>
    <div class="secret" id="qrSecret"></div>
    <p style="font-size:11px;color:#8a7560;text-align:center;margin-top:8px">Or enter the secret key manually in the authenticator app</p>
  </div>
</div>
<script>
loadUsers();
async function loadUsers(){
  const r=await fetch('/auth/admin/users',{credentials:'include'});
  const d=await r.json();
  const el=document.getElementById('userList');
  if(!d.users||!d.users.length){el.innerHTML='<div style="color:#8a7560;font-size:13px;padding:8px 0">No users yet</div>';return;}
  el.innerHTML=d.users.map(u=>`<div class="user-row">
    <div><strong>${u.username}</strong><span class="badge badge-${u.role}" style="margin-left:7px">${u.role}</span><span style="color:#8a7560;font-size:11px;margin-left:7px">${u.has_totp?'2FA enabled':'No 2FA'}</span></div>
    <div style="display:flex;gap:6px">
      <button class="btn btn-sm btn-amber" onclick="resetTotp('${u.username}')">Reset 2FA</button>
      <button class="btn btn-sm btn-red" onclick="delUser('${u.username}')">Delete</button>
    </div></div>`).join('');
}
async function addUser(){
  const u=document.getElementById('newUser').value.trim(),p=document.getElementById('newPass').value,role=document.getElementById('newRole').value;
  if(!u||!p){showMsg('addMsg','Please fill all fields','err');return;}
  const r=await fetch('/auth/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'include',body:JSON.stringify({username:u,password:p,role})});
  const d=await r.json();
  if(r.ok){showMsg('addMsg','User created successfully','ok');document.getElementById('newUser').value='';document.getElementById('newPass').value='';showQr(d.qr_image,d.totp_secret);loadUsers();}
  else showMsg('addMsg',d.error||'Failed','err');
}
async function resetTotp(username){
  if(!confirm('Reset 2FA for '+username+'? They will need to re-scan the QR code.'))return;
  const r=await fetch('/auth/admin/reset-totp',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'include',body:JSON.stringify({username})});
  const d=await r.json();
  if(r.ok){showQr(d.qr_image,d.totp_secret);loadUsers();}
  else alert(d.error||'Failed');
}
async function delUser(username){
  if(!confirm('Delete user '+username+'? This cannot be undone.'))return;
  const r=await fetch('/auth/admin/users/'+username,{method:'DELETE',credentials:'include'});
  if(r.ok)loadUsers();
  else alert('Failed to delete user');
}
function showQr(img,secret){
  document.getElementById('qrImg').src='data:image/png;base64,'+img;
  document.getElementById('qrSecret').textContent='Secret: '+secret;
  document.getElementById('qrCard').style.display='block';
  document.getElementById('qrCard').scrollIntoView({behavior:'smooth'});
}
function showMsg(id,msg,type){const el=document.getElementById(id);el.textContent=msg;el.className='msg '+type;el.style.display='block';setTimeout(()=>el.style.display='none',4000);}
</script>
</body>
</html>"""

# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route('/login')
def login_page():
    return LOGIN_HTML

@app.route('/admin')
def admin_page():
    payload = verify_token(get_token())
    if not payload:
        return redirect('/login')
    if payload.get('role') != 'admin':
        return redirect('/')
    return ADMIN_HTML

@app.route('/auth/login', methods=['POST'])
def auth_login():
    data     = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    users    = load_users()
    user     = users.get(username)
    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401
    if not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        return jsonify({'error': 'Invalid username or password'}), 401
    return jsonify({'next': 'totp'})

@app.route('/auth/verify', methods=['POST'])
def auth_verify():
    data      = request.json or {}
    username  = data.get('username', '').strip().lower()
    password  = data.get('password', '')
    totp_code = data.get('totp', '').strip()
    users     = load_users()
    user      = users.get(username)
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    if not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        return jsonify({'error': 'Invalid credentials'}), 401
    totp = pyotp.TOTP(user['totp_secret'])
    if not totp.verify(totp_code, valid_window=1):
        return jsonify({'error': 'Invalid authenticator code'}), 401
    token = make_token(username, user['role'])
    resp  = make_response(jsonify({'ok': True, 'role': user['role']}))
    resp.set_cookie('auth_token', token, httponly=True, secure=True,
                    samesite='Lax', max_age=JWT_EXPIRY)
    return resp

@app.route('/auth/logout', methods=['GET', 'POST'])
def auth_logout():
    resp = make_response(redirect('/login'))
    resp.delete_cookie('auth_token', path='/')
    return resp

# ── Admin API ─────────────────────────────────────────────────────────────────
@app.route('/auth/admin/users', methods=['GET'])
@require_admin
def admin_list_users():
    users = load_users()
    return jsonify({'users': [
        {'username': u, 'role': d['role'], 'has_totp': bool(d.get('totp_secret'))}
        for u, d in users.items()
    ]})

@app.route('/auth/admin/users', methods=['POST'])
@require_admin
def admin_create_user():
    data     = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    role     = data.get('role', 'user')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    users = load_users()
    if username in users:
        return jsonify({'error': 'User already exists'}), 400
    pw_hash     = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    totp_secret = pyotp.random_base32()
    users[username] = {'password_hash': pw_hash, 'totp_secret': totp_secret, 'role': role}
    save_users(users)
    return jsonify({'ok': True, 'totp_secret': totp_secret, 'qr_image': make_qr(username, totp_secret)})

@app.route('/auth/admin/reset-totp', methods=['POST'])
@require_admin
def admin_reset_totp():
    username = (request.json or {}).get('username', '').strip().lower()
    users    = load_users()
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    totp_secret = pyotp.random_base32()
    users[username]['totp_secret'] = totp_secret
    save_users(users)
    return jsonify({'ok': True, 'totp_secret': totp_secret, 'qr_image': make_qr(username, totp_secret)})

@app.route('/auth/admin/users/<username>', methods=['DELETE'])
@require_admin
def admin_delete_user(username):
    users = load_users()
    if username not in users:
        return jsonify({'error': 'User not found'}), 404
    del users[username]
    save_users(users)
    return jsonify({'ok': True})

# ── Proxy all authenticated requests to server.py ────────────────────────────
@app.route('/', defaults={'path': ''}, methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'])
@app.route('/<path:path>', methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'])
def proxy(path):
    # Allow oauth token exchange without authentication
    if not path.startswith('auth/') and not path.startswith('login') and not path.startswith('admin'):
        if path == 'health' or path.startswith('api/'):
            # Pass through directly without auth check
            url = f"{BACKEND}/{path}"
            if request.query_string:
                url += '?' + request.query_string.decode()
            try:
                excluded = {'host', 'content-length', 'transfer-encoding', 'connection'}
                headers  = {k: v for k, v in request.headers if k.lower() not in excluded}
                resp = req.request(method=request.method, url=url, headers=headers, data=request.get_data(), allow_redirects=False, timeout=120)
                excluded_resp = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
                resp_headers  = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded_resp]
                return Response(resp.content, status=resp.status_code, headers=resp_headers)
            except Exception as e:
                return jsonify({'error': str(e)}), 502
    # All other routes require auth
    payload = verify_token(get_token())
    if not payload:
        if path.startswith("api/") or path == "health" or request.is_json:
            return jsonify({'error': 'Unauthorized'}), 401
        return redirect('/login')
    request.user = payload
    url = f'{BACKEND}/{path}'
    if request.query_string:
        url += '?' + request.query_string.decode()
    try:
        excluded = {'host', 'content-length', 'transfer-encoding', 'connection'}
        headers  = {k: v for k, v in request.headers if k.lower() not in excluded}
        resp = req.request(
            method          = request.method,
            url             = url,
            headers         = headers,
            data            = request.get_data(),
            allow_redirects = False,
            timeout         = 120,
        )
        excluded_resp = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
        resp_headers  = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded_resp]
        return Response(resp.content, status=resp.status_code, headers=resp_headers)
    except Exception as e:
        return jsonify({'error': str(e)}), 502

if __name__ == '__main__':
    print('=' * 55)
    print('  Auth layer running on port 8000')
    print('  Proxying to server.py on port 8080')
    print('=' * 55)
    app.run(host='127.0.0.1', port=8000, debug=False)
