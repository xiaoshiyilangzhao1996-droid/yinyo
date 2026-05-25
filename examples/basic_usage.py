"""YINYO (隐曜) — An Autonomous Feishu Agent That Learns.

Usage:
    from yinyo import YinyoAgent

    agent = YinyoAgent(workspace="./my_workspace")

    # Handle a Feishu message
    response = agent.handle_message(
        user_id="ou_xxx",
        chat_id="oc_xxx",
        text="帮我查一下最近 3 天的天气"
    )

    # Or run a task directly
    result = agent.run("分析这份数据并生成报告")
    print(result)
"""

from .agent import YinyoAgent

__version__ = "7.0.0"
__all__ = ["YinyoAgent"]
