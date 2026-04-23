#!/bin/bash

echo "=== Flow-Pilot 快速修复脚本 ==="
echo ""

# 1. 重启容器
echo "1. 重启 Docker 容器..."
docker-compose down
docker-compose up -d

echo ""
echo "2. 等待服务启动（30 秒）..."
sleep 30

# 2. 检查容器状态
echo ""
echo "3. 检查容器状态..."
docker-compose ps

# 3. 测试后端
echo ""
echo "4. 测试后端健康检查..."
curl -s http://localhost:8000/health | python3 -m json.tool || echo "后端未就绪"

# 4. 获取虚拟机 IP
echo ""
echo "5. 网络信息..."
echo "本地 IP 地址："
hostname -I | awk '{print $1}'

# 5. 启动前端
echo ""
echo "6. 启动前端服务器..."
echo "请在另一个终端运行："
echo "  cd frontend"
echo "  python3 -m http.server 8080 --bind 0.0.0.0"
echo ""
echo "然后访问："
echo "  http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "=== 完成 ==="
