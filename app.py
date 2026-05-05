# FREE FIRE LIKE API - BD SERVER ONLY (TOKEN BASED)
from flask import Flask, request, jsonify
import asyncio
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import binascii
import aiohttp
import requests
import json
import like_pb2
import like_count_pb2
import uid_generator_pb2
import time
from collections import defaultdict
from datetime import datetime
import random
import os

app = Flask(__name__)

KEY_LIMIT = 90
tracker = defaultdict(lambda: [0, time.time()])
liked_cache = defaultdict(set)

def get_today_midnight_timestamp():
    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day)
    return midnight.timestamp()

def load_tokens():
    """Load tokens from tokens_bd.json - Format: [{"token": "..."}]"""
    filename = "tokens_bd.json"
    
    if not os.path.exists(filename):
        print(f"❌ {filename} not found")
        return []
    
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            tokens = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "token" in item:
                        token = item["token"].strip()
                        if token:
                            tokens.append(token)
                    elif isinstance(item, str):
                        tokens.append(item.strip())
            
            print(f"✅ Loaded {len(tokens)} tokens from {filename}")
            return tokens
            
    except Exception as e:
        print(f"❌ Error loading tokens: {e}")
        return []

def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_message = pad(plaintext, AES.block_size)
    return binascii.hexlify(cipher.encrypt(padded_message)).decode('utf-8')

def create_protobuf_message(user_id, region):
    message = like_pb2.like()
    message.uid = int(user_id)
    message.region = region
    return message.SerializeToString()

async def send_like(encrypted_uid, token, url):
    try:
        edata = bytes.fromhex(encrypted_uid)
        headers = {
            'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
            'Authorization': f"Bearer {token}",
            'Content-Type': "application/x-www-form-urlencoded",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB53"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=edata, headers=headers, timeout=5) as response:
                return response.status
    except:
        return 500

async def process_token(target_uid, encrypted_uid, token, url, semaphore):
    async with semaphore:
        status = await send_like(encrypted_uid, token, url)
        if status == 200:
            liked_cache[target_uid].add(token)
        return status

async def send_all_likes(target_uid, server_name, url):
    region = server_name
    protobuf_message = create_protobuf_message(target_uid, region)
    encrypted_uid = encrypt_message(protobuf_message)
    
    tokens = load_tokens()
    if not tokens:
        return {'success': 0, 'failed': 0, 'total': 0}
    
    already_liked = liked_cache.get(target_uid, set())
    fresh_tokens = [t for t in tokens if t not in already_liked]
    
    print(f"📊 Total tokens: {len(tokens)}")
    print(f"✅ Fresh tokens: {len(fresh_tokens)}")
    print(f"⏭️ Already liked: {len(already_liked)}")
    
    if not fresh_tokens:
        return {
            'success': 0,
            'failed': 0,
            'total': len(tokens),
            'already_liked': len(already_liked)
        }
    
    random.shuffle(fresh_tokens)
    semaphore = asyncio.Semaphore(25)
    tasks = []
    
    for token in fresh_tokens[:500]:
        tasks.append(process_token(target_uid, encrypted_uid, token, url, semaphore))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful = sum(1 for r in results if r == 200)
    failed = sum(1 for r in results if isinstance(r, int) and r != 200)
    
    return {
        'success': successful,
        'failed': failed,
        'total': len(tokens),
        'already_liked': len(already_liked),
        'fresh_used': len(fresh_tokens[:500])
    }

def enc(uid):
    message = uid_generator_pb2.uid_generator()
    message.krishna_ = int(uid)
    message.teamXdarks = 1
    return encrypt_message(message.SerializeToString())

def decode_protobuf(binary):
    try:
        items = like_count_pb2.Info()
        items.ParseFromString(binary)
        return items
    except:
        return None

def get_player_info(encrypted_uid, server_name, token):
    if server_name == "IND":
        url = "https://client.ind.freefiremobile.com/GetPlayerPersonalShow"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        url = "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
    else:
        url = "https://clientbp.ggpolarbear.com/GetPlayerPersonalShow"

    edata = bytes.fromhex(encrypted_uid)
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB53"
    }

    try:
        response = requests.post(url, data=edata, headers=headers, verify=False, timeout=10)
        return decode_protobuf(response.content)
    except:
        return None

@app.route('/like', methods=['GET'])
def handle_requests():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "").upper()
    key = request.args.get("key")
    client_ip = request.remote_addr

    if key != "RS":
        return jsonify({"error": "Invalid API key"}), 403

    if not uid or not server_name:
        return jsonify({"error": "UID and server_name required"}), 400

    valid_servers = ["IND", "BR", "US", "SAC", "NA", "BD", "RU"]
    if server_name not in valid_servers:
        return jsonify({"error": f"Invalid server. Use: {valid_servers}"}), 400

    tokens = load_tokens()
    if not tokens:
        return jsonify({"error": "No tokens found"}), 500

    check_token = tokens[0]

    today_midnight = get_today_midnight_timestamp()
    count, last_reset = tracker[client_ip]

    if last_reset < today_midnight:
        tracker[client_ip] = [0, time.time()]
        count = 0

    if count >= KEY_LIMIT:
        return jsonify({"error": "Daily limit reached", "remains": f"(0/{KEY_LIMIT})"}), 429

    encrypted_uid = enc(uid)

    before = get_player_info(encrypted_uid, server_name, check_token)
    if before is None:
        return jsonify({"error": "Invalid UID or server", "status": 0}), 200

    try:
        before_data = json.loads(MessageToJson(before))
        before_like = int(before_data['AccountInfo'].get('Likes', 0))
    except:
        return jsonify({"error": "Data parsing failed", "status": 0}), 200

    if server_name == "IND":
        like_url = "https://client.ind.freefiremobile.com/LikeProfile"
    elif server_name in {"BR", "US", "SAC", "NA"}:
        like_url = "https://client.us.freefiremobile.com/LikeProfile"
    else:
        like_url = "https://clientbp.ggpolarbear.com/LikeProfile"

    result = asyncio.run(send_all_likes(uid, server_name, like_url))

    after = get_player_info(encrypted_uid, server_name, check_token)
    if after is None:
        return jsonify({"error": "Could not verify likes", "status": 0}), 200

    try:
        after_data = json.loads(MessageToJson(after))
        after_like = int(after_data['AccountInfo']['Likes'])
        player_id = int(after_data['AccountInfo']['UID'])
        player_name = str(after_data['AccountInfo']['PlayerNickname'])
        
        like_given = after_like - before_like
        status = 1 if like_given != 0 else 2
        
        if like_given > 0:
            tracker[client_ip][0] += 1
        
        remains = KEY_LIMIT - tracker[client_ip][0]

        return jsonify({
            "LikesGivenByAPI": like_given,
            "LikesafterCommand": after_like,
            "LikesbeforeCommand": before_like,
            "PlayerNickname": player_name,
            "UID": player_id,
            "status": status,
            "remains": f"({remains}/{KEY_LIMIT})"
        })
    except Exception as e:
        return jsonify({"error": str(e), "status": 0}), 500

@app.route('/reset-cache', methods=['GET'])
def reset_cache():
    key = request.args.get("key")
    if key != "STAR":
        return jsonify({"error": "Invalid key"}), 403
    
    global liked_cache
    liked_cache.clear()
    return jsonify({"message": "Cache cleared"})

if __name__ == '__main__':
    print("="*50)
    print("TOKEN BASED LIKE API")
    print("="*50)
    print("Token file: tokens_bd.json")
    print("Format: [{\"token\": \"...\"}]")
    app.run(host='0.0.0.0', port=5001, debug=True)
