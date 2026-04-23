#!/bin/bash

echo "=== Flow-Pilot 快速修复脚本 ==="
echo ""

# 1. 停止容器
echo "1. 停止现有容器..."
docker-compose down

# 2. 重新构建（应用 Dockerfile 更改）
echo ""
echo "2. 重新构建镜像（使用国内镜像源）..."
docker-compose build --no-cache app

# 3. 启动所有服务
echo ""
echo "3. 启动所有服务..."
docker-compose up -d

echo ""
echo "4. 等待服务启动（30 秒）..."
sleep 30

# 4. 检查容器状态
echo ""
echo "5. 检查容器状态..."
docker-compose ps

# 5. 查看应用日志
echo ""
echo "6. 应用日志（最后 20 行）..."
docker logs flow_pilot_app --tail 20

# 6. 测试后端
echo ""
echo "7. 测试后端健康检查..."
curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "后端未就绪，请稍等片刻"

# 7. 获取虚拟机 IP
echo ""
echo "8. 网络信息..."
VM_IP=$(hostname -I | awk '{print $1}')
echo "虚拟机 IP: $VM_IP"

# 8. 前端启动说明
echo ""
echo "=== 下一步 ==="
echo "在另一个终端运行："
echo "  cd ~/Flow-Pilot/frontend"
echo "  python3 -m http.server 8080 --bind 0.0.0.0"
echo ""
echo "然后在宿主机浏览器访问："
echo "  http://$VM_IP:8080"
echo ""
echo "=== 完成 ==="
