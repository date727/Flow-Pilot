"""
全链路测试：验证 LangGraph 状态机的完整工作流
包含 Reflexion 闭环的端到端测试
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from langchain_core.messages import HumanMessage, AIMessage

# Windows 专用修复
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def test_graph_basic():
    """基础测试：验证图初始化和基本执行流程"""
    from app.engine.graph import get_graph_app, close_pool

    print("\n--- [Test] 基础图执行测试 ---")
    try:
        graph_app = await get_graph_app()
        print("  ✅ 图初始化成功")

        config = {"configurable": {"thread_id": "test_basic_001"}}
        user_query = "请简单介绍一下 Python 的优势"

        initial_input = {
            "input": user_query,
            "messages": [HumanMessage(content=user_query)],
            "metadata": {"source": "test"},
            "reflection_round": 0,
            "critic_score": 0.0,
            "critic_feedback": "",
            "needs_replan": False,
        }

        print("  正在执行图（请稍候）...")
        result = await graph_app.ainvoke(initial_input, config=config)

        # 验证输出
        assert result.get("plan"), "规划结果不应为空"
        assert result.get("output"), "最终输出不应为空"
        assert len(result.get("messages", [])) > 0, "消息列表不应为空"

        print(f"  ✅ 规划结果: {result.get('plan', '')[:80]}...")
        print(f"  ✅ 最终输出: {result.get('output', '')[:80]}...")
        print(f"  ✅ 消息总数: {len(result.get('messages', []))}")
        print(f"  ✅ 反思轮次: {result.get('reflection_round', 0)}")
        print(f"  ✅ Critic 评分: {result.get('critic_score', 0.0):.2f}")

        # 验证持久化
        final_state = await graph_app.aget_state(config)
        assert final_state.values, "持久化状态不应为空"
        print(f"  ✅ 状态持久化验证通过，消息数: {len(final_state.values.get('messages', []))}")

        return True

    except Exception as exc:
        print(f"  ❌ 测试失败: {exc}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await close_pool()


async def test_graph_reflexion():
    """反思机制测试：验证 Critic 节点触发重新规划"""
    from app.engine.graph import get_graph_app, close_pool
    from app.mcp.models import ToolResult

    print("\n--- [Test] Reflexion 闭环测试 ---")

    # Mock Critic 使其第一次返回低分（触发重新规划），第二次返回高分
    call_count = 0

    async def mock_evaluate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        from app.agents.critic import CriticResult
        if call_count == 1:
            # 第一次评估：低分，触发重新规划
            return CriticResult(
                score=0.4,
                passed=False,
                issues=["回答不够详细"],
                suggestions=["请提供更多具体示例"],
                summary="回答质量不足，需要改进",
            )
        else:
            # 第二次评估：高分，通过
            return CriticResult(
                score=0.9,
                passed=True,
                issues=[],
                suggestions=[],
                summary="回答质量良好",
            )

    try:
        with patch("app.agents.critic.CriticAgent.evaluate", mock_evaluate):
            graph_app = await get_graph_app()
            config = {"configurable": {"thread_id": "test_reflexion_001"}}
            user_query = "解释什么是机器学习"

            initial_input = {
                "input": user_query,
                "messages": [HumanMessage(content=user_query)],
                "metadata": {"source": "test"},
                "reflection_round": 0,
                "critic_score": 0.0,
                "critic_feedback": "",
                "needs_replan": False,
            }

            print("  正在执行 Reflexion 闭环（请稍候）...")
            result = await graph_app.ainvoke(initial_input, config=config)

            reflection_round = result.get("reflection_round", 0)
            print(f"  ✅ 反思轮次: {reflection_round}")
            print(f"  ✅ 最终 Critic 评分: {result.get('critic_score', 0.0):.2f}")

            # 验证至少经历了一次反思
            assert reflection_round >= 1, f"应至少经历 1 次反思，实际: {reflection_round}"
            print("  ✅ Reflexion 闭环验证通过")
            return True

    except Exception as exc:
        print(f"  ❌ 测试失败: {exc}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await close_pool()


async def main():
    results = []

    print("=" * 60)
    print("Flow-Pilot 全链路测试")
    print("=" * 60)

    results.append(("基础图执行", await test_graph_basic()))
    results.append(("Reflexion 闭环", await test_graph_reflexion()))

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
    asyncio.run(main())
