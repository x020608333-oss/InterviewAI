"""LLM 客户端封装（OpenAI 兼容协议）。

结构化输出策略：
1. 优先 Function Calling：把 Pydantic Schema 注册为工具并用 tool_choice 强制调用；
2. 失败时降级为「JSON 提示词 + 文本解析」，兼容不支持工具调用的服务。

未配置 API Key 或 openai 包不可用时 available=False，上层 Agent 自动切换离线演示模式。
"""
import json
import logging
import re
from copy import deepcopy

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_ENABLED, LLM_MODEL

logger = logging.getLogger("interviewai.llm")

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - 未安装 openai 时仍可离线运行
    OpenAI = None

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def extract_json(text: str) -> dict:
    """从模型输出中提取 JSON 对象（容忍代码块围栏与前后缀文本）。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"模型未返回合法 JSON: {text[:200]}")


def resolve_refs(schema: dict) -> dict:
    """内联展开 Pydantic 生成的 $defs/$ref，兼容不支持 JSON 引用的服务。"""
    defs = schema.get("$defs", {})

    def _walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                name = ref.split("/")[-1]
                if name in defs:
                    return _walk(deepcopy(defs[name]))
                return node
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        return node

    out = _walk(deepcopy(schema))
    out.pop("$defs", None)
    return out


class LLMClient:
    def __init__(self) -> None:
        self.client = None
        if LLM_ENABLED and OpenAI is not None:
            try:
                self.client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
                logger.info("LLM 已启用: %s @ %s", LLM_MODEL, LLM_BASE_URL)
            except Exception as exc:  # pragma: no cover
                logger.warning("LLM 初始化失败，进入离线演示模式: %s", exc)

    @property
    def available(self) -> bool:
        return self.client is not None

    def chat(self, messages: list[dict], temperature: float = 0.3) -> str:
        resp = self.client.chat.completions.create(
            model=LLM_MODEL, messages=messages, temperature=temperature
        )
        return resp.choices[0].message.content or ""

    def chat_json(
        self,
        messages: list[dict],
        schema: dict,
        tool_name: str,
        tool_desc: str,
        temperature: float = 0.2,
    ) -> dict:
        """通过 Function Calling（或降级提示词）获取符合 Schema 的结构化输出。"""
        if self.client is None:
            raise RuntimeError("LLM 未配置")
        params = resolve_refs(schema)

        # 1) Function Calling：tool_choice 强制模型按 Schema 传参
        try:
            resp = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=temperature,
                tools=[{
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "description": tool_desc,
                        "parameters": params,
                    },
                }],
                tool_choice={"type": "function", "function": {"name": tool_name}},
            )
            message = resp.choices[0].message
            if message.tool_calls:
                return json.loads(message.tool_calls[0].function.arguments)
            if message.content:
                return extract_json(message.content)
        except Exception as exc:
            logger.warning("Function Calling 失败，降级为 JSON 提示词: %s", exc)

        # 2) 降级：提示词强制 JSON 输出
        instruction = (
            "你必须只输出一个 JSON 对象，不要输出解释文字，不要使用代码块围栏。\n"
            "JSON 必须符合以下 Schema：\n"
            f"{json.dumps(params, ensure_ascii=False)}"
        )
        last_error: Exception | None = None
        for _ in range(2):
            try:
                text = self.chat(
                    [{"role": "system", "content": instruction}, *messages],
                    temperature=temperature,
                )
                return extract_json(text)
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"结构化输出失败: {last_error}")


llm = LLMClient()
