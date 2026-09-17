import json
import asyncio
import aiohttp
import os
import zlib
import time
import threading
from datetime import datetime, timedelta
import jwt
from flask import Flask, request, jsonify
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import my_pb2
import output_pb2
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# ==================== CONSTANTS ====================
LIKE_ENDPOINT = "https://client.ind.freefiremobile.com/LikeProfile"
PLAYER_INFO_ENDPOINT = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"

SPY_UID = os.environ.get("SPY_UID", "4620008082")
SPY_PASSWORD = os.environ.get("SPY_PASSWORD", "RAGHAVLIKEBOT_RAGHAV_IXLO1")

CACHE_REFRESH_INTERVAL = 7200  # 2 hours
SCHEDULED_REFRESH_HOUR = 3  # 3 AM daily

AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV = b'6oyZDr22E3ychjM%'

HEADERS = {
    "User-Agent": "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
    "X-GA": "v1 1",
    "ReleaseVersion": "OB55",
    "Content-Type": "application/octet-stream",
    "X-Unity-Version": "2022.3.47f1"
}

# Token storage file
TOKEN_STORE_FILE = os.path.join(os.path.dirname(__file__), "tokens_cache.json")

# ==================== CREDIT ====================
CREDIT = "@ShadowXSlayer"

# ==================== BEAUTIFUL LOGGER ====================
class Logger:
    @staticmethod
    def _ts():
        return datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def banner():
        print("\n" + "=" * 60)
        print("  🔥  FREE FIRE LIKE BOT  🔥  ")
        print("  ⚡  Auto Token Generator + Likes  ⚡  ")
        print(f"  👑  Credit: {CREDIT}  👑  ")
        print("=" * 60 + "\n")

    @staticmethod
    def info(msg): print(f"[{Logger._ts()}] ℹ️  {msg}")
    @staticmethod
    def success(msg): print(f"[{Logger._ts()}] ✅ {msg}")
    @staticmethod
    def fail(msg): print(f"[{Logger._ts()}] ❌ {msg}")
    @staticmethod
    def warn(msg): print(f"[{Logger._ts()}] ⚠️  {msg}")
    @staticmethod
    def token(msg): print(f"[{Logger._ts()}] 🔑 {msg}")
    @staticmethod
    def like(msg): print(f"[{Logger._ts()}] 💖 {msg}")
    @staticmethod
    def api(msg): print(f"[{Logger._ts()}] 🌐 {msg}")
    @staticmethod
    def save(msg): print(f"[{Logger._ts()}] 💾 {msg}")
    @staticmethod
    def clock(msg): print(f"[{Logger._ts()}] ⏰ {msg}")
    @staticmethod
    def user(msg): print(f"[{Logger._ts()}] 👤 {msg}")
    @staticmethod
    def rocket(msg): print(f"[{Logger._ts()}] 🚀 {msg}")
    @staticmethod
    def progress(msg): print(f"[{Logger._ts()}] 📊 {msg}")

# ==================== EXTERNAL TOKEN APIs ====================
EXTERNAL_TOKEN_APIS = [
    {
        "name": "KAWSAR",
        "url": "https://kawsarxjwt.lovable.app/api/public/token",
        "params": lambda uid, pw: {"uid": uid, "password": pw},
        "token_path": ["token"],
        "success_check": lambda data: data.get("success") is True
    },
    {
        "name": "NIROB",
        "url": "https://nirobxjwt.vercel.app/token",
        "params": lambda uid, pw: {"uid": uid, "password": pw},
        "token_path": ["token"],
        "success_check": lambda data: data.get("status") == "success"
    },
    {
        "name": "RAGHAV",
        "url": "http://148.113.25.200:6293/Tok",
        "params": lambda uid, pw: {"uid": uid, "pw": pw},
        "token_path": ["token"],
        "success_check": lambda data: bool(data.get("token"))
    }
]

# ==================== JWT CACHE ====================
jwt_cache = {}
cache_lock = threading.Lock()

def get_jwt_expiry(token: str) -> int:
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded.get("exp", 0)
    except:
        return 0

def is_jwt_valid(token: str) -> bool:
    if not token:
        return False
    exp = get_jwt_expiry(token)
    return exp > time.time() + 300

def get_cached_jwt(uid: str) -> str:
    with cache_lock:
        cached = jwt_cache.get(uid)
        if cached and is_jwt_valid(cached["token"]):
            return cached["token"]
    return None

def cache_jwt(uid: str, token: str):
    exp = get_jwt_expiry(token)
    if exp:
        with cache_lock:
            jwt_cache[uid] = {"token": token, "expires_at": exp, "cached_at": time.time()}

# ==================== TOKEN PERSISTENCE ====================
def save_tokens_to_json():
    try:
        with cache_lock:
            data = {
                "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total": len(jwt_cache),
                "credit": CREDIT,
                "tokens": jwt_cache
            }
        with open(TOKEN_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        Logger.save(f"Tokens saved to JSON ({len(data['tokens'])} accounts)")
    except Exception as e:
        Logger.fail(f"Failed to save tokens: {e}")

def load_tokens_from_json():
    if not os.path.exists(TOKEN_STORE_FILE):
        return 0
    try:
        with open(TOKEN_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        tokens = data.get("tokens", {})
        count = 0
        with cache_lock:
            for uid, entry in tokens.items():
                if isinstance(entry, dict) and is_jwt_valid(entry.get("token", "")):
                    jwt_cache[uid] = entry
                    count += 1
        if count:
            Logger.success(f"Loaded {count} valid tokens from JSON cache")
        return count
    except Exception as e:
        Logger.fail(f"Failed to load tokens: {e}")
        return 0

# ==================== CRYPTO & PROTOBUF HELPERS ====================
def encrypt_data(data: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(data, AES.block_size))

def decrypt_data(data: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return unpad(cipher.decrypt(data), AES.block_size)

def write_varint(value: int) -> bytes:
    result = []
    while value > 0x7f:
        result.append((value & 0x7f) | 0x80)
        value >>= 7
    result.append(value)
    return bytes(result) if result else b'\x00'

def write_field(field_num: int, field_type: int, value: int) -> bytes:
    key = (field_num << 3) | field_type
    return write_varint(key) + write_varint(value)

def build_request_payload(target_uid: int) -> bytes:
    payload = write_field(1, 0, target_uid)
    payload += write_field(2, 0, 9)
    payload += write_field(3, 0, 1)
    payload += write_field(4, 0, 1)
    return payload

def build_like_protobuf(account_id: int) -> bytes:
    data = bytearray()
    data.extend(write_varint(8))
    data.extend(write_varint(account_id))
    submsg = bytearray()
    submsg.extend(write_varint(80))
    submsg.extend(write_varint(75))
    data.extend(write_varint(18))
    data.extend(write_varint(len(submsg)))
    data.extend(submsg)
    return bytes(data)

# ==================== RESPONSE DECODER ====================
def decode_response(data: bytes) -> dict:
    try:
        decrypted = decrypt_data(data)
    except Exception:
        decrypted = data
    if decrypted.startswith(b'\x1f\x8b'):
        try:
            decrypted = zlib.decompress(decrypted, 16 + zlib.MAX_WBITS)
        except:
            pass

    def read_varint(buf: bytes, pos: int):
        val = 0
        shift = 0
        while pos < len(buf):
            b = buf[pos]
            val |= (b & 0x7F) << shift
            pos += 1
            if (b & 0x80) == 0:
                break
            shift += 7
        return val, pos

    def read_bytes(buf: bytes, pos: int):
        length, pos = read_varint(buf, pos)
        return buf[pos:pos+length], pos+length

    pos = 0
    name = ""
    level = 0
    likes = 0
    uid = 0

    while pos < len(decrypted):
        tag, pos = read_varint(decrypted, pos)
        field_num = tag >> 3
        wire_type = tag & 0x07
        if field_num == 1 and wire_type == 2:
            sub_len, pos = read_varint(decrypted, pos)
            sub_end = pos + sub_len
            sub_pos = pos
            while sub_pos < sub_end:
                sub_tag, sub_pos = read_varint(decrypted, sub_pos)
                sub_field = sub_tag >> 3
                sub_wire = sub_tag & 0x07
                if sub_field == 3 and sub_wire == 2:
                    name_bytes, sub_pos = read_bytes(decrypted, sub_pos)
                    name = name_bytes.decode('utf-8', errors='ignore')
                elif sub_field == 6 and sub_wire == 0:
                    level, sub_pos = read_varint(decrypted, sub_pos)
                elif sub_field == 21 and sub_wire == 0:
                    likes, sub_pos = read_varint(decrypted, sub_pos)
                elif sub_field == 1 and sub_wire == 0:
                    uid, sub_pos = read_varint(decrypted, sub_pos)
                else:
                    if sub_wire == 0:
                        _, sub_pos = read_varint(decrypted, sub_pos)
                    elif sub_wire == 2:
                        length, sub_pos = read_varint(decrypted, sub_pos)
                        sub_pos += length
                    else:
                        sub_pos = sub_end
            pos = sub_end
        else:
            if wire_type == 0:
                _, pos = read_varint(decrypted, pos)
            elif wire_type == 2:
                length, pos = read_varint(decrypted, pos)
                pos += length
            else:
                break
    return {"name": name, "level": level, "likes": likes, "uid": uid}

# ==================== EXTERNAL TOKEN FETCHER ====================
async def get_token_from_external_api(session: aiohttp.ClientSession, uid: str, password: str) -> str:
    for api in EXTERNAL_TOKEN_APIS:
        try:
            params = api["params"](uid, password)
            async with session.get(api["url"], params=params, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                if not api["success_check"](data):
                    continue
                token = data
                for key in api["token_path"]:
                    if isinstance(token, dict) and key in token:
                        token = token[key]
                    else:
                        token = None
                        break
                if token and isinstance(token, str) and token.count('.') >= 2:
                    return token
        except Exception:
            continue
    return None

# ==================== JWT GENERATION ====================
async def get_jwt_from_guest(session: aiohttp.ClientSession, uid: str, password: str, max_retries: int = 3, verbose: bool = True) -> str:
    cached = get_cached_jwt(uid)
    if cached:
        return cached

    base_delay = 1.0
    for attempt in range(max_retries):
        try:
            oauth_url = "https://100067.connect.garena.com/oauth/guest/token/grant"
            payload = {
                'uid': uid,
                'password': password,
                'response_type': "token",
                'client_type': "2",
                'client_secret': "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
                'client_id': "100067"
            }
            oauth_headers = {
                'User-Agent': "GarenaMSDK/4.0.19P9(SM-M526B ;Android 13;pt;BR;)",
                'Connection': "Keep-Alive",
                'Accept-Encoding': "gzip"
            }
            async with session.post(oauth_url, data=payload, headers=oauth_headers, timeout=5) as resp:
                if resp.status != 200:
                    raise Exception(f"OAuth HTTP {resp.status}")
                data = await resp.json()
                access_token = data.get('access_token')
                open_id = data.get('open_id')
                if not access_token or not open_id:
                    raise Exception("Missing access_token or open_id")

            login_url = "https://loginbp.ppmainecoonghj.com/MajorLogin"
            login_headers = {
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
                "Connection": "Keep-Alive",
                "Content-Type": "application/octet-stream",
                "X-Unity-Version": "2018.4.11f1",
                "X-GA": "v1 1",
                "ReleaseVersion": "OB55"
            }
            platforms = [8, 3, 4, 6]
            for platform in platforms:
                game_data = my_pb2.GameData()
                game_data.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                game_data.game_name = "free fire"
                game_data.game_version = 1
                game_data.version_code = "1.111.1"
                game_data.os_info = "Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)"
                game_data.device_type = "Handheld"
                game_data.network_provider = "Verizon Wireless"
                game_data.connection_type = "WIFI"
                game_data.screen_width = 1280
                game_data.screen_height = 960
                game_data.dpi = "240"
                game_data.cpu_info = "ARMv7 VFPv3 NEON VMH | 2400 | 4"
                game_data.total_ram = 5951
                game_data.gpu_name = "Adreno (TM) 640"
                game_data.gpu_version = "OpenGL ES 3.0"
                game_data.user_id = "Google|74b585a9-0268-4ad3-8f36-ef41d2e53610"
                game_data.ip_address = "172.190.111.97"
                game_data.language = "en"
                game_data.open_id = open_id
                game_data.access_token = access_token
                game_data.platform_type = platform
                game_data.field_99 = str(platform)
                game_data.field_100 = str(platform)

                encrypted_body = encrypt_data(game_data.SerializeToString())
                async with session.post(login_url, data=encrypted_body, headers=login_headers, ssl=False, timeout=6) as r:
                    if r.status == 200:
                        resp_data = await r.read()
                        try:
                            response_proto = output_pb2.Garena_420()
                            response_proto.ParseFromString(resp_data)
                            if response_proto.token:
                                token = response_proto.token
                                cache_jwt(uid, token)
                                return token
                        except:
                            text = resp_data.decode('utf-8', errors='ignore')
                            start = text.find("eyJ")
                            if start != -1:
                                end = start
                                while end < len(text) and text[end] not in ['"', ' ', '\n', '\r', '\t', '\x00']:
                                    end += 1
                                token = text[start:end]
                                if token.count('.') >= 2:
                                    cache_jwt(uid, token)
                                    return token
            raise Exception("MajorLogin failed for all platforms")
        except Exception as e:
            if attempt == max_retries - 1:
                if verbose:
                    Logger.api(f"Direct gen failed for {uid}, trying external APIs...")
                ext_token = await get_token_from_external_api(session, uid, password)
                if ext_token:
                    cache_jwt(uid, ext_token)
                    return ext_token
                return None
            await asyncio.sleep(base_delay * (2 ** attempt))
    return None

# ==================== FETCH PLAYER INFO ====================
async def fetch_player_info(jwt_token: str, target_uid: int) -> dict:
    request_body = build_request_payload(target_uid)
    encrypted = encrypt_data(request_body)
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt_token}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(PLAYER_INFO_ENDPOINT, headers=headers, data=encrypted,
                                    timeout=aiohttp.ClientTimeout(total=15), ssl=False) as resp:
                if resp.status != 200:
                    return None
                content = await resp.read()
                return decode_response(content)
        except Exception:
            return None

# ==================== SEND LIKE ====================
async def send_like_once(session: aiohttp.ClientSession, jwt_token: str, target_uid: int) -> bool:
    plain = build_like_protobuf(target_uid)
    encrypted = encrypt_data(plain)
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt_token}"
    try:
        async with session.post(LIKE_ENDPOINT, headers=headers, data=encrypted,
                                timeout=aiohttp.ClientTimeout(total=10), ssl=False) as resp:
            return resp.status == 200
    except:
        return False

async def send_like_with_retry(session: aiohttp.ClientSession, jwt_token: str, target_uid: int, retries: int = 3) -> bool:
    for attempt in range(retries):
        if await send_like_once(session, jwt_token, target_uid):
            return True
        if attempt < retries - 1:
            await asyncio.sleep(0.5 * (attempt + 1))
    return False

# ==================== LOAD ACCOUNTS ====================
def load_accounts():
    accounts_json = os.environ.get("ACCOUNTS_JSON")
    if accounts_json:
        try:
            data = json.loads(accounts_json)
            return _extract_accounts(data)
        except:
            pass
    accounts_file = os.path.join(os.path.dirname(__file__), "accounts.json")
    if os.path.exists(accounts_file):
        with open(accounts_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return _extract_accounts(data)
            except:
                pass
    return []

def _extract_accounts(data):
    accounts = []
    uid_keys = ['uid', 'id', 'account_id', 'guestUid', 'user_id']
    pwd_keys = ['password', 'pass', 'guestPass']
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            uid = None
            pwd = None
            for k in uid_keys:
                if k in item:
                    uid = str(item[k])
                    break
            for k in pwd_keys:
                if k in item:
                    pwd = str(item[k])
                    break
            if uid and pwd:
                accounts.append({"uid": uid, "password": pwd})
    elif isinstance(data, dict):
        uid = None
        pwd = None
        for k in uid_keys:
            if k in data:
                uid = str(data[k])
                break
        for k in pwd_keys:
            if k in data:
                pwd = str(data[k])
                break
        if uid and pwd:
            accounts.append({"uid": uid, "password": pwd})
    return accounts

# ==================== BACKGROUND TOKEN GENERATOR ====================
def generate_all_tokens_background(reason: str = "startup"):
    try:
        if reason == "startup":
            Logger.rocket("Background token generation started (startup)")
        elif reason == "2hour":
            Logger.clock("Background token generation started (2-hour refresh)")
        elif reason == "3am":
            Logger.clock("Background token generation started (3 AM daily refresh)")
        else:
            Logger.rocket(f"Background token generation started ({reason})")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run():
            accounts = load_accounts()
            total = len(accounts) + 1
            success = 0
            failed = 0

            async with aiohttp.ClientSession() as session:
                Logger.token(f"Generating spy token for {SPY_UID}...")
                spy_token = await get_jwt_from_guest(session, SPY_UID, SPY_PASSWORD, 3, verbose=False)
                if spy_token:
                    success += 1
                    Logger.success(f"Spy token OK ({SPY_UID})")
                else:
                    failed += 1
                    Logger.fail(f"Spy token FAILED ({SPY_UID})")

                if not accounts:
                    Logger.warn("No accounts found for token generation")
                    return success, failed

                MAX_CONCURRENT = 50
                semaphore = asyncio.Semaphore(MAX_CONCURRENT)

                async def gen_one(acc):
                    async with semaphore:
                        uid = str(acc.get('uid', ''))
                        pwd = str(acc.get('password', ''))
                        if not uid or not pwd:
                            return False
                        tok = await get_jwt_from_guest(session, uid, pwd, 2, verbose=False)
                        return bool(tok)

                tasks = [gen_one(acc) for acc in accounts]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for r in results:
                    if r is True:
                        success += 1
                    else:
                        failed += 1

                Logger.progress(f"Token generation complete: ✅ {success} passed | ❌ {failed} failed | 📦 Total {total}")
                return success, failed

        loop.run_until_complete(run())
        loop.close()

        save_tokens_to_json()
        Logger.save(f"All tokens persisted to {os.path.basename(TOKEN_STORE_FILE)}")

    except Exception as e:
        Logger.fail(f"Background token generation error: {e}")

def start_background_generation(reason: str = "startup"):
    t = threading.Thread(target=generate_all_tokens_background, args=(reason,), daemon=True)
    t.start()
    return t

# ==================== AUTO REFRESH SCHEDULER ====================
def scheduler_loop():
    last_2h_refresh = time.time()
    last_3am_date = None

    while True:
        try:
            now = time.time()
            dt = datetime.now()

            if now - last_2h_refresh >= CACHE_REFRESH_INTERVAL:
                Logger.clock("⏰ 2-hour cache refresh triggered")
                with cache_lock:
                    jwt_cache.clear()
                start_background_generation("2hour")
                last_2h_refresh = now

            if dt.hour == SCHEDULED_REFRESH_HOUR and dt.minute < 5:
                today = dt.strftime("%Y-%m-%d")
                if last_3am_date != today:
                    Logger.clock(f"⏰ 3 AM daily refresh triggered ({today})")
                    with cache_lock:
                        jwt_cache.clear()
                    start_background_generation("3am")
                    last_3am_date = today

            time.sleep(60)
        except Exception as e:
            Logger.fail(f"Scheduler error: {e}")
            time.sleep(60)

def start_scheduler():
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()
    Logger.clock("Scheduler started (2h refresh + 3 AM daily refresh)")
    return t

# ==================== FLASK ENDPOINT ====================
@app.route('/sepnix', methods=['GET'])
def send_likes_endpoint():
    uid = request.args.get('uid')
    if not uid:
        return jsonify({"error": "Missing 'uid' parameter"}), 400
    try:
        target_uid = int(uid)
    except ValueError:
        return jsonify({"error": "Invalid UID (must be a number)"}), 400

    Logger.user(f"Like request received for UID: {target_uid}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def get_spy_jwt():
        async with aiohttp.ClientSession() as session:
            return await get_jwt_from_guest(session, SPY_UID, SPY_PASSWORD, 3, verbose=False)
    spy_jwt = loop.run_until_complete(get_spy_jwt())
    if not spy_jwt:
        loop.close()
        Logger.fail("Failed to get spy JWT")
        return jsonify({"error": "Failed to generate JWT from spy account"}), 500

    async def fetch_before():
        return await fetch_player_info(spy_jwt, target_uid)
    before = loop.run_until_complete(fetch_before())
    if not before:
        loop.close()
        Logger.fail(f"Failed to fetch player info for {target_uid}")
        return jsonify({"error": "Failed to fetch player info before sending likes"}), 500

    Logger.info(f"Player: {before['name']} | Level: {before['level']} | Likes: {before['likes']}")

    accounts = load_accounts()
    if not accounts:
        loop.close()
        Logger.fail("No accounts found")
        return jsonify({"error": "No accounts found"}), 500

    Logger.like(f"Sending likes from {len(accounts)} accounts...")

    MAX_CONCURRENT = 100
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    like_retries = 3

    async def process_account(session, account):
        async with semaphore:
            a_uid = account.get('uid')
            pwd = account.get('password')
            if not a_uid or not pwd:
                return False
            jwt_token = await get_jwt_from_guest(session, str(a_uid), pwd, 2, verbose=False)
            if not jwt_token:
                return False
            return await send_like_with_retry(session, jwt_token, target_uid, retries=like_retries)

    async def run_all():
        async with aiohttp.ClientSession() as session:
            tasks = [process_account(session, acc) for acc in accounts]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success = sum(1 for r in results if r is True)
            failed = len(accounts) - success
            return success, failed

    success, failed = loop.run_until_complete(run_all())
    Logger.like(f"Likes sent: ✅ {success} passed | ❌ {failed} failed")

    async def fetch_after():
        return await fetch_player_info(spy_jwt, target_uid)
    after = loop.run_until_complete(fetch_after())
    loop.close()
    if not after:
        Logger.fail("Failed to fetch player info after likes")
        return jsonify({"error": "Failed To Fetch Player Info"}), 500

    like_given = int(after["likes"]) - int(before["likes"])
    Logger.success(f"Done! Total likes given: {like_given} | New total: {after['likes']}")

    save_tokens_to_json()

    # ==================== FINAL RESPONSE ====================
    return jsonify({
        "LikesGivenByAPI": like_given,
        "LikesafterCommand": int(after["likes"]),
        "LikesbeforeCommand": int(before["likes"]),
        "PlayerNickname": str(after["name"]),
        "UID": int(target_uid),
        "Credit": CREDIT,
        "Status": "Success ✅" if like_given > 0 else "No Likes Added ⚠️",
        "TotalAccounts": len(accounts),
        "PassedRequests": success,
        "FailedRequests": failed
    })

# ==================== HEALTH CHECK ====================
@app.route('/health', methods=['GET'])
def health_check():
    with cache_lock:
        cached_count = len(jwt_cache)
    return jsonify({
        "status": "ok",
        "cached_tokens": cached_count,
        "external_apis": [api["name"] for api in EXTERNAL_TOKEN_APIS],
        "scheduler": "active (2h + 3 AM)",
        "token_store": os.path.basename(TOKEN_STORE_FILE) if os.path.exists(TOKEN_STORE_FILE) else "not created yet",
        "Credit": CREDIT
    })

@app.route('/tokens', methods=['GET'])
def list_tokens():
    with cache_lock:
        out = {}
        for uid, entry in jwt_cache.items():
            tok = entry.get("token", "")
            out[uid] = {
                "token_preview": tok[:20] + "..." + tok[-10:] if len(tok) > 30 else tok,
                "expires_at": entry.get("expires_at"),
                "expires_in_seconds": int(entry.get("expires_at", 0) - time.time())
            }
    return jsonify({"total": len(out), "tokens": out, "Credit": CREDIT})

# ==================== STARTUP ====================
def startup():
    Logger.banner()
    Logger.rocket("Server starting up...")
    Logger.info("Loading cached tokens from JSON...")
    loaded = load_tokens_from_json()
    Logger.rocket(f"Starting background token generation ({loaded} tokens already cached)...")
    start_background_generation("startup")
    start_scheduler()
    Logger.success("All systems ready! Server is live 🚀")
    Logger.info(f"Credit: {CREDIT}")

_startup_done = False
@app.before_request
def _ensure_startup():
    global _startup_done
    if not _startup_done:
        _startup_done = True
        startup()

# ==================== RUN ====================
if __name__ == '__main__':
    startup()
    app.run(host='0.0.0.0', port=5000, debug=False)