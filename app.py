# FREE FIRE LIKE API - VERCEL SERVERLESS
import json
import asyncio
import requests
import time
import random
from datetime import datetime
from collections import defaultdict
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
import like_pb2
import like_count_pb2
import uid_generator_pb2

# In-memory storage (Vercel এ কাজ করবে কিন্তু রিস্টার্ট হলে রিসেট হবে)
tracker = {}
liked_cache = {}
KEY_LIMIT = 90

def get_today_midnight_timestamp():
    now = datetime.now()
    midnight = datetime(now.year, now.month, now.day)
    return midnight.timestamp()

def load_tokens():
    """Load tokens from JSON file"""
    try:
        with open("tokens_bd.json", "r", encoding="utf-8") as f:
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
            return tokens
    except:
        return []

def encrypt_message(plaintext):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded_message = pad(plaintext, AES.block_size)
    return cipher.encrypt(padded_message).hex()

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

def get_player_info(encrypted_uid, token):
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

def send_like(encrypted_uid, token):
    url = "https://clientbp.ggpolarbear.com/LikeProfile"
    edata = bytes.fromhex(encrypted_uid)
    headers = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'Authorization': f"Bearer {token}",
        'Content-Type': "application/x-www-form-urlencoded",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB53"
    }
    try:
        response = requests.post(url, data=edata, headers=headers, timeout=10)
        return response.status_code
    except:
        return 500

def handler(request):
    """Vercel Serverless Function handler"""
    
    # Get query parameters
    path = request.path
    method = request.method
    
    # CORS headers
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': ''
        }
    
    # Home route
    if path == '/' or path == '/api':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                "status": "active",
                "service": "Free Fire Like API",
                "server": "BD Only",
                "endpoints": {
                    "/api/like": "Send likes (uid, key required)",
                    "/api/stats": "Get stats (key required)"
                }
            })
        }
    
    # Like route
    if path == '/api/like':
        uid = request.args.get('uid')
        key = request.args.get('key')
        client_ip = request.headers.get('x-forwarded-for', 'unknown')
        
        if key != "RS":
            return {
                'statusCode': 403,
                'headers': headers,
                'body': json.dumps({"success": False, "error": "Invalid API key"})
            }
        
        if not uid:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({"success": False, "error": "UID required"})
            }
        
        # Check daily limit
        today_midnight = get_today_midnight_timestamp()
        if client_ip not in tracker:
            tracker[client_ip] = [0, time.time()]
        
        count, last_reset = tracker[client_ip]
        if last_reset < today_midnight:
            tracker[client_ip] = [0, time.time()]
            count = 0
        
        if count >= KEY_LIMIT:
            return {
                'statusCode': 429,
                'headers': headers,
                'body': json.dumps({"success": False, "error": f"Daily limit reached (0/{KEY_LIMIT})"})
            }
        
        # Load tokens
        tokens = load_tokens()
        if not tokens:
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({"success": False, "error": "No tokens available"})
            }
        
        check_token = tokens[0]
        encrypted_uid = enc(uid)
        
        # Get before likes
        before = get_player_info(encrypted_uid, check_token)
        if before is None:
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({"success": False, "error": "Invalid UID"})
            }
        
        try:
            before_data = json.loads(MessageToJson(before))
            before_like = int(before_data['AccountInfo'].get('Likes', 0))
            player_name = before_data['AccountInfo'].get('PlayerNickname', 'Unknown')
            player_id = before_data['AccountInfo'].get('UID', uid)
        except:
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({"success": False, "error": "Parse error"})
            }
        
        # Send likes
        region = "BD"
        protobuf_message = create_protobuf_message(int(uid), region)
        encrypted_uid_like = encrypt_message(protobuf_message)
        
        successful = 0
        failed = 0
        
        # Track already liked
        if uid not in liked_cache:
            liked_cache[uid] = set()
        
        for token in tokens[:100]:  # Limit to 100 per request
            if token in liked_cache[uid]:
                continue
            
            status = send_like(encrypted_uid_like, token)
            if status == 200:
                successful += 1
                liked_cache[uid].add(token)
            else:
                failed += 1
            
            await asyncio.sleep(0.1)  # Rate limit
        
        # Get after likes
        after = get_player_info(encrypted_uid, check_token)
        after_like = before_like
        
        if after:
            try:
                after_data = json.loads(MessageToJson(after))
                after_like = int(after_data['AccountInfo'].get('Likes', before_like))
            except:
                pass
        
        like_given = after_like - before_like
        
        if like_given > 0:
            tracker[client_ip] = [tracker[client_ip][0] + 1, tracker[client_ip][1]]
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                "success": True,
                "uid": int(player_id),
                "name": player_name,
                "likes_before": before_like,
                "likes_after": after_like,
                "likes_given": like_given,
                "tokens_used": successful,
                "tokens_failed": failed,
                "server": "BD"
            })
        }
    
    # Stats route
    if path == '/api/stats':
        key = request.args.get('key')
        if key != "RS":
            return {
                'statusCode': 403,
                'headers': headers,
                'body': json.dumps({"success": False, "error": "Invalid key"})
            }
        
        tokens = load_tokens()
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                "success": True,
                "total_tokens": len(tokens),
                "cached_entries": len(liked_cache),
                "server": "BD"
            })
        }
    
    # 404
    return {
        'statusCode': 404,
        'headers': headers,
        'body': json.dumps({"error": "Not found"})
    }
