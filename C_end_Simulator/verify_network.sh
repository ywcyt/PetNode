#!/bin/bash

echo "=== 1. 测试提取宿主机 IP ==="
# 尝试多种获取 IP 的方式
if command -v ip >/dev/null 2>&1; then
    HOST_IP=$(ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n 1)
    if [ -z "$HOST_IP" ]; then
        HOST_IP=$(ip -4 addr show | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -n 1)
    fi
elif command -v hostname >/dev/null 2>&1 && hostname -I >/dev/null 2>&1; then
    HOST_IP=$(hostname -I | awk '{print $1}')
else
    # Mac/Windows(Git Bash) 兼容方案
    HOST_IP=$(ifconfig | grep -E "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n 1)
fi

echo "📍 检测到的宿主机 IP 为: [${HOST_IP}]"

if [ -z "$HOST_IP" ]; then
    echo "❌ 无法自动获取宿主机 IP，请手动指定 HOST_IP。"
    exit 1
fi

echo -e "\n=== 2. 测试启动 Flask 容器并监听端口 ==="
docker rm -f test_flask_cloud > /dev/null 2>&1
docker run -d --name test_flask_cloud -p 5000:5000 petnode-flask:latest
sleep 3
if curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "✅ Flask 容器在本机跑通，http://localhost:5000 可以访问"
else
    echo "❌ 无法访问 Flask 容器的 localhost:5000，请检查端口是否被占用"
    docker rm -f test_flask_cloud > /dev/null 2>&1
    exit 1
fi

echo -e "\n=== 3. 测试 Engine 通过指定 IP 访问 Flask 容器 ==="
docker rm -f test_engine_conn > /dev/null 2>&1
docker run --rm \
    --name test_engine_conn \
    --add-host="pppetnode.com:${HOST_IP}" \
    curlimages/curl:latest http://pppetnode.com:5000/api/health

if [ $? -eq 0 ]; then
    echo -e "\n✅ Engine 成功通过公网域名(绑定的真实 IP $HOST_IP) 请求到云端！网络打通成功！"
else
    echo -e "\n❌ Engine 请求失败！可能是因为宿主机 IP 不正确或防火墙拦截了来自 Docker 的重定向请求。"
    echo "💡 提示：在 Windows/Mac 上，你可以尝试将 HOST_IP 改为 host.docker.internal 并在 Docker 网络中允许。"
fi

echo -e "\n=== 4. 清理测试容器 ==="
docker rm -f test_flask_cloud > /dev/null 2>&1
echo "✨ 清理完成。"

