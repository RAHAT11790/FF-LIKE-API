# FREE FIRE LIKE BOT API - BD SERVER ONLY
# ═══════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

KEY_LIMIT = 90
tracker = defaultdict(lambda: [0, time.time()])
liked_cache = defaultdict(set)

# ═══════════════════════════════════════════════════════════
# TOKEN LOADER (JSON FORMAT)
# ═══════════════════════════════════════════════════════════

def get_today_midnight_timestamp():
    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day)
    return midnight.timestamp()

def load_tokens():
    """Load tokens from tokens_bd.json file"""
    filename = "tokens_bd.json"
    
    if not os.path.exists(filename):
        print(f"❌ {filename} not found")
        return []
    
    try:
        tokens = []
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            
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

# ═══════════════════════════════════════════════════════════
# ENCRYPTION & PROTOBUF
# ═══════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════
# PLAYER INFO & LIKE SENDER
# ═══════════════════════════════════════════════════════════

def get_player_info(encrypted_uid, token):
    """Get player info from BD server"""
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

async def send_like(encrypted_uid, token):
    """Send like to BD server"""
    url = "https://clientbp.ggpolarbear.com/LikeProfile"
    
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

async def process_token(target_uid, encrypted_uid, token, semaphore):
    async with semaphore:
        status = await send_like(encrypted_uid, token)
        if status == 200:
            liked_cache[target_uid].add(token)
        return status

async def send_all_likes(target_uid):
    """Send likes using all tokens from JSON"""
    region = "BD"
    protobuf_message = create_protobuf_message(target_uid, region)
    encrypted_uid = encrypt_message(protobuf_message)
    
    all_tokens = load_tokens()
    if not all_tokens:
        return {'success': 0, 'failed': 0, 'total': 0}
    
    already_liked = liked_cache.get(target_uid, set())
    fresh_tokens = [t for t in all_tokens if t not in already_liked]
    
    if not fresh_tokens:
        return {
            'success': 0, 
            'failed': 0, 
            'total': len(all_tokens),
            'already_liked': len(already_liked)
        }
    
    random.shuffle(fresh_tokens)
    semaphore = asyncio.Semaphore(25)
    tasks = []
    
    for token in fresh_tokens[:500]:
        tasks.append(process_token(target_uid, encrypted_uid, token, semaphore))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful = sum(1 for r in results if r == 200)
    failed = sum(1 for r in results if isinstance(r, int) and r != 200)
    
    return {
        'success': successful,
        'failed': failed,
        'total': len(all_tokens),
        'already_liked': len(already_liked),
        'fresh_used': len(fresh_tokens[:500])
    }

# ═══════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "active",
        "service": "Free Fire Like API",
        "server": "BD Only",
        "endpoints": {
            "/like": "Send likes to a player (uid required)",
            "/reset": "Reset liked cache (key required)"
        },
        "example": "/like?uid=123456789&key=RS"
    })

@app.route('/like', methods=['GET'])
def handle_like():
    uid = request.args.get("uid")
    key = request.args.get("key")
    client_ip = request.remote_addr
    
    # API Key check
    if key != "RS":
        return jsonify({
            "success": False,
            "error": "Invalid API key"
        }), 403
    
    # UID check
    if not uid:
        return jsonify({
            "success": False,
            "error": "UID is required"
        }), 400
    
    # Check daily limit
    today_midnight = get_today_midnight_timestamp()
    count, last_reset = tracker[client_ip]
    
    if last_reset < today_midnight:
        tracker[client_ip] = [0, time.time()]
        count = 0
    
    if count >= KEY_LIMIT:
        return jsonify({
            "success": False,
            "error": f"Daily limit reached (0/{KEY_LIMIT})"
        }), 429
    
    # Load tokens and get one for checking
    tokens = load_tokens()
    if not tokens:
        return jsonify({
            "success": False,
            "error": "No tokens available"
        }), 500
    
    check_token = tokens[0]
    encrypted_uid = enc(uid)
    
    # Get before like count
    before = get_player_info(encrypted_uid, check_token)
    if before is None:
        return jsonify({
            "success": False,
            "error": "Invalid UID or server error"
        }), 200
    
    try:
        before_data = json.loads(MessageToJson(before))
        before_like = int(before_data['AccountInfo'].get('Likes', 0))
        player_name = before_data['AccountInfo'].get('PlayerNickname', 'Unknown')
        player_id = before_data['AccountInfo'].get('UID', uid)
    except:
        return jsonify({
            "success": False,
            "error": "Failed to parse player data"
        }), 200
    
    # Send likes
    result = asyncio.run(send_all_likes(uid))
    
    # Get after like count
    after = get_player_info(encrypted_uid, check_token)
    if after is None:
        return jsonify({
            "success": False,
            "error": "Could not verify likes"
        }), 200
    
    try:
        after_data = json.loads(MessageToJson(after))
        after_like = int(after_data['AccountInfo'].get('Likes', 0))
        
        like_given = after_like - before_like
        
        if like_given > 0:
            tracker[client_ip][0] += 1
            count = tracker[client_ip][0]
        
        remains = KEY_LIMIT - count
        
        return jsonify({
            "success": True,
            "uid": int(player_id),
            "name": player_name,
            "likes_before": before_like,
            "likes_after": after_like,
            "likes_given": like_given,
            "tokens_used": result['success'],
            "tokens_failed": result['failed'],
            "tokens_total": result['total'],
            "daily_used": count,
            "daily_remaining": remains,
            "server": "BD"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/reset', methods=['GET'])
def reset_cache():
    key = request.args.get("key")
    
    if key != "RS":
        return jsonify({
            "success": False,
            "error": "Invalid key"
        }), 403
    
    global liked_cache
    liked_cache.clear()
    
    return jsonify({
        "success": True,
        "message": "Cache reset successfully"
    })

@app.route('/stats', methods=['GET'])
def get_stats():
    key = request.args.get("key")
    
    if key != "RS":
        return jsonify({
            "success": False,
            "error": "Invalid key"
        }), 403
    
    tokens = load_tokens()
    
    return jsonify({
        "success": True,
        "total_tokens": len(tokens),
        "cached_likes": len(liked_cache),
        "server": "BD"
    })

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("═" * 50)
    print("   FREE FIRE LIKE API - BD SERVER")
    print("═" * 50)
    print("📁 Token file: tokens_bd.json")
    print("📝 Format: [{\"token\": \"your_token_here\"}]")
    print("🔑 API Key: RS")
    print("🌐 Server: BD Only")
    print("⚡ Daily Limit: 90 per IP")
    print("═" * 50)
    print("🚀 Server running on http://0.0.0.0:5001")
    print("═" * 50)
    
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
