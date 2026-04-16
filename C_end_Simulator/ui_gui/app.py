# app.py
from flask import Flask, request, jsonify
from Mongo_Storage import MongoStorage
import hashlib
import time

app = Flask(__name__)
db = MongoStorage()

SECRET_TOKEN = "petnode_super_secret_2026"

def verify_signature(data, client_timestamp, client_signature):
    print("   -> [校验中] 开始比对签名...")
    current_time = int(time.time())
    
    if abs(current_time - int(client_timestamp)) > 60:
        print(f"   -> [错误] 时间戳相差太大！服务器时间:{current_time}, 客户端时间:{client_timestamp}")
        return False
    
    # 尝试提取 ID
    dog_id = data.get("device_id", data.get("dog_id", "unknown_dog"))
    raw_string = f"{dog_id}{client_timestamp}{SECRET_TOKEN}"
    server_signature = hashlib.md5(raw_string.encode('utf-8')).hexdigest()
    
    print(f"   -> 提取的狗ID: {dog_id}")
    print(f"   -> 拼接的明文: {raw_string}")
    print(f"   -> 算出的暗号: {server_signature}")
    print(f"   -> 收到的暗号: {client_signature}")
    
    if server_signature != client_signature:
        print("   -> [结论] ❌ 签名不匹配！")
        return False
        
    print("   -> [结论] ✅ 签名完美匹配！")
    return True

@app.route('/api/v1/health-data', methods=['POST'])
def receive_data():
    print("\n" + "▼" * 50)
    print("🚨 [哨兵站] 警报：有人敲门！")
    
    try:
        client_token = request.headers.get('X-Token')
        client_timestamp = request.headers.get('X-Timestamp')
        client_signature = request.headers.get('X-Signature')
        
        print(f"📦 [包裹检查] Token: {client_token}")

        if client_token != "PETNODE_DEVICE_V1":
            print("❌ [拦截] Token 不对，直接轰走！")
            return jsonify({"status": "error", "message": "Unauthorized"}), 401

        data = request.get_json()
        print(f"📄 [拆解内容] 收到的数据: {data}")

        if not client_timestamp or not client_signature:
            print("❌ [拦截] 没带时间戳或签名钢印！")
            return jsonify({"status": "error", "message": "Forbidden"}), 403
            
        if not verify_signature(data, client_timestamp, client_signature):
            print("❌ [拦截] 签名验证失败，数据丢弃！")
            return jsonify({"status": "error", "message": "Forbidden"}), 403

        db.save_data(data)
        print("✅ [放行] 数据合法，已安全存入 MongoDB！")
        print("▲" * 50 + "\n")
        
        return jsonify({"status": "success", "message": "Data saved securely"}), 201
        
    except Exception as e:
        print(f"💥 [崩溃] 服务器发生内部错误: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005)