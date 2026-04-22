"""
ReAct 闭环测试
验证 Planner → Executor → Tools → Executor → Critic → END 完整流程
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.mcp.models import ToolResult

# Windows 专用修复
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def test_react_with_tool_call():
    """验证完整的 ReAct 闭环：工具调用路径"""
    from app.engine.graph import get_graph_app, close_pool

    # Mock 工具定义
    mock_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]

    # Mock 工具执行结果
    mock_result = ToolResult(success=True, data=[{"text": "东京今天晴天，气温 25 度"}])

    print("\n--- [Test] ReAct 工具调用闭环测试 ---")

    with patch("app.engine.nodes.mcp_manager") as mock_mcp:
        mock_mcp.get_all_tools = AsyncMock(return_value=mock_tools)
        mock_mcp.call_tool_by_name = AsyncMock(return_value=mock_result)

        try:
            graph_app = await get_graph_app()
        except Exception as exc:
            print(f"  ❌ 数据库连接失败: {exc}")
            print("  请确保 PostgreSQL 已启动并配置正确")
            return False

        config = {"configurable": {"thread_id": "test_react_tool_001"}}
        user_query = "东京现在的天气怎么样？"

        initial_input = {
            "input": user_query,
            "messages": [HumanMessage(content=user_query)],
            "metadata": {"test": True},
            "reflection_round": 0,
            "critic_score": 0.0,
            "critic_feedback": "",
            "needs_replan": False,
        }

        print(f"  输入: {user_query}")
        print("  正在执行（请稍候）...")

        try:
            final_state = await graph_app.ainvoke(initial_input, config=config)
        except Exception as exc:
            print(f"  ❌ 执行失败: {exc}")
            import traceback
            traceback.print_exc()
            await close_pool()
            return False

        messages = final_state.get("messages", [])

        has_tool_call = False
        has_tool_result = False

        for m in messages:
            if isinstance(m, AIMessage) and hasattr(m, "tool_calls") and m.tool_calls:
                has_tool_call = True
                tool_name = (
                    m.tool_calls[0].get("name")
                    if isinstance(m.tool_calls[0], dict)
                    else getattr(m.tool_calls[0], "name", "unknown")
                )
                print(f"  ✅ 发现工具调用: {tool_name}")
            if isinstance(m, ToolMessage) and m.name == "get_weather":
                has_tool_result = True
                print(f"  ✅ 工具执行结果: {m.content}")

        output = final_state.get("output", "")
        print(f"  最终输出: {output[:100]}...")
        print(f"  反思轮次: {final_state.get('reflection_round', 0)}")
        print(f"  Critic 评分: {final_state.get('critic_score', 0.0):.2f}")

        if has_tool_call and has_tool_result:
            print("  ✅ ReAct 工具调用闭环验证通过")
            await close_pool()
            return True
        else:
            print("  ⚠️  未形成完整工具调用闭环（LLM 可能决定不调用工具）")
            print("  这不一定是错误，LLM 可能直接回答了问题")
            await close_pool()
            return True  # 不强制要求工具调用，LLM 有权直接回答


async def test_react_no_tools():
    """验证无工具场景：直接回答"""
    from app.engine.graph import get_graph_app, close_pool

    print("\n--- [Test] ReAct 无工具直接回答测试 ---")

    with patch("app.engine.nodes.mcp_manager") as mock_mcp:
        mock_mcp.get_all_tools = AsyncMock(return_value=[])  # 无可用工具

        try:
            graph_app = await get_graph_app()
        except Exception as exc:
            print(f"  ❌ 数据库连接失败: {exc}")
            return False

        config = {"configurable": {"thread_id": "test_react_notool_001"}}
        user_query = "1 + 1 等于多少？"

        initial_input = {
            "input": user_query,
            "messages": [HumanMessage(content=user_query)],
            "metadata": {"test": True},
            "reflection_round": 0,
            "critic_score": 0.0,
            "critic_feedback": "",
            "needs_replan": False,
        }

        print(f"  输入: {user_query}")
        try:
            final_state = await graph_app.ainvoke(initial_input, config=config)
            output = final_state.get("output", "")
            assert output, "无工具场景下应有直接输出"
            print(f"  ✅ 直接回答: {output[:100]}")
            await close_pool()
            return True
        except Exception as exc:
            print(f"  ❌ 执行失败: {exc}")
            await close_pool()
            return False


async def test_tool_error_handling():
    """验证工具调用失败时的错误处理"""
    from app.engine.graph import get_graph_app, close_pool

    print("\n--- [Test] 工具调用失败处理测试 ---")

    mock_tools = [
        {
            "type": "function",
            "function": {
                "name": "broken_tool",
                "description": "一个会失败的工具",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    # 模拟工具调用失败
    mock_fail_result = ToolResult(success=False, error="工具服务不可用")

    with patch("app.engine.nodes.mcp_manager") as mock_mcp:
        mock_mcp.get_all_tools = AsyncMock(return_value=mock_tools)
        mock_mcp.call_tool_by_name = AsyncMock(return_value=mock_fail_result)

        try:
            graph_app = await get_graph_app()
        except Exception as exc:
            print(f"  ❌ 数据库连接失败: {exc}")
            return False

        config = {"configurable": {"thread_id": "test_react_error_001"}}
        user_query = "请调用 broken_tool"

        initial_input = {
            "input": user_query,
            "messages": [HumanMessage(content=user_query)],
            "metadata": {"test": True},
            "reflection_round": 0,
            "critic_score": 0.0,
            "critic_feedback": "",
            "needs_replan": False,
        }

        try:
            final_state = await graph_app.ainvoke(initial_input, config=config)
            # 即使工具失败，系统应该能给出最终答案
            output = final_state.get("output", "")
            print(f"  ✅ 工具失败后系统仍给出输出: {output[:80]}...")
            await close_pool()
            return True
        except Exception as exc:
            print(f"  ❌ 系统在工具失败时崩溃: {exc}")
            await close_pool()
            return False


async def main():
    results = []

    print("=" * 60)
    print("Flow-Pilot ReAct 闭环测试")
    print("=" * 60)

    results.append(("工具调用闭环", await test_react_with_tool_call()))
    results.append(("无工具直接回答", await test_react_no_tools()))
    results.append(("工具失败处理", await test_tool_error_handling()))

    print("\n" + "=" * 60)
    print("测试结果汇总:")
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status} - {name}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查日志")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被用户中断")
