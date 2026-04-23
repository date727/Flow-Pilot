#!/bin/bash

set -e  # 遇到错误立即退出

echo "=========================================="
echo "  Flow-Pilot MCP 网络问题修复脚本"
echo "=========================================="
echo ""

# 1. 停止现有容器
echo "步骤 1/7: 停止现有容器..."
docker-compose down
echo "✅ 容器已停止"
echo ""

# 2. 清理旧镜像（可选）
echo "步骤 2/7: 清理旧镜像..."
docker rmi flow-pilot-app 2>/dev/null || echo "没有旧镜像需要清理"
echo "✅ 清理完成"
echo ""

# 3. 重新构建镜像
echo "步骤 3/7: 重新构建镜像（使用国内镜像源）..."
echo "这可能需要 3-5 分钟，请耐心等待..."
docker-compose build --no-cache app
echo "✅ 镜像构建完成"
echo ""

# 4. 验证 uv 配置
echo "步骤 4/7: 验证 uv 配置..."
echo "检查 uv.toml 配置文件："
docker run --rm flow-pilot-app cat /home/flowpilot/.config/uv/uv.toml || echo "⚠️  配置文件读取失败"
echo ""

# 5. 启动所有服务
echo "步骤 5/7: 启动所有服务..."
docker-compose up -d
echo "✅ 服务已启动"
echo ""

# 6. 等待服务就绪
echo "步骤 6/7: 等待服务启动（45 秒）..."
for i in {1..45}; do
    echo -n "."
    sleep 1
done
echo ""
echo "✅ 等待完成"
echo ""

# 7. 检查状态
echo "步骤 7/7: 检查服务状态..."
echo ""
echo "--- 容器状态 ---"
docker-compose ps
echo ""

echo "--- 应用日志（最后 30 行）---"
docker logs flow_pilot_app --tail 30
echo ""

echo "--- 健康检查 ---"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ 后端健康检查通过"
    curl -s http://localhost:8000/health | python3 -m json.tool
else
    echo "⚠️  后端尚未就绪，请稍等片刻后运行："
    echo "   docker logs flow_pilot_app -f"
fi
echo ""

echo "--- MCP 工具列表 ---"
if curl -s http://localhost:8000/api/v1/tools/ > /dev/null 2>&1; then
    TOOL_COUNT=$(curl -s http://localhost:8000/api/v1/tools/ | python3 -c "import sys, json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "0")
    echo "✅ 发现 $TOOL_COUNT 个 MCP 工具"
    curl -s http://localhost:8000/api/v1/tools/ | python3 -m json.tool
else
    echo "⚠️  MCP 工具列表尚未就绪"
fi
echo ""

# 8. 网络信息
VM_IP=$(hostname -I | awk '{print $1}')
echo "=========================================="
echo "  修复完成！"
echo "=========================================="
echo ""
echo "虚拟机 IP: $VM_IP"
echo ""
echo "下一步："
echo "  1. 在另一个终端启动前端："
echo "     cd ~/Flow-Pilot/frontend"
echo "     python3 -m http.server 8080 --bind 0.0.0.0"
echo ""
echo "  2. 在宿主机浏览器访问："
echo "     http://$VM_IP:8080"
echo ""
echo "  3. 查看实时日志："
echo "     docker logs flow_pilot_app -f"
echo ""
echo "  4. 测试 MCP 工具："
echo "     curl http://localhost:8000/api/v1/tools/"
echo ""
echo "=========================================="
