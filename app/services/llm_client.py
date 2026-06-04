"""
大模型客户端（OpenAI / 华为云兼容 Chat Completions）

职责：
- 给定一个药物/食物名称，调用大模型生成别名列表（中文通用名、英文名、
  化学名、常见缩写），供 safety-check 接口扩大 DDInter / 过敏史的命中面。

设计要点：
- 配置全部走环境变量（app.core.config.settings），API Key 不硬编码。
- 未配置（LLM_BASE_URL / LLM_API_KEY 留空）或任何网络/解析异常时一律降级：
  返回仅含原始输入名的列表，绝不抛异常打断业务接口。
- 仅依赖 httpx（已在依赖中），不引入额外 SDK。
"""

from __future__ import annotations

import json

import httpx

from app.core.config import settings

# 要求模型只返回 JSON 数组，覆盖四类写法；并显式要求包含原始输入。
_ALIAS_PROMPT = (
    "你是药物与食物名称归一化助手。给定一个名称，请列出它的常见别名，"
    "包括：中文通用名、英文名、化学名、常见缩写。"
    "必须包含输入的原始名称本身。"
    "只输出一个 JSON 字符串数组，不要任何解释、不要 Markdown 代码块。"
    '例如输入「阿司匹林」，输出：["阿司匹林","Aspirin","Acetylsalicylic acid","ASA"]。'
)


def is_configured() -> bool:
    """LLM 是否已配置（决定是否走真实调用还是降级）。"""
    return bool(settings.LLM_BASE_URL and settings.LLM_API_KEY)


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if not it.strip() or key in seen:
            continue
        seen.add(key)
        out.append(it.strip())
    return out


def _parse_aliases(content: str) -> list[str]:
    """从模型返回文本中解析 JSON 数组；容忍 ```json 包裹。"""
    text = content.strip()
    if text.startswith("```"):
        # 去掉 ```json ... ``` 包裹
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("alias response is not a JSON array")
    return [str(x) for x in data if str(x).strip()]


def expand_aliases(name: str) -> tuple[list[str], bool]:
    """
    生成 name 的别名列表。

    返回 (aliases, llm_used)：
      - aliases 一定包含原始输入名（去重、保序）
      - llm_used 表示是否真正用到了大模型（False 即降级）
    任何失败都不抛异常，降级为 [name]。
    """
    base = [name] if name and name.strip() else []
    if not name or not name.strip():
        return [], False

    if not is_configured():
        return _dedupe_keep_order(base), False

    try:
        resp = httpx.post(
            f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": _ALIAS_PROMPT},
                    {"role": "user", "content": name},
                ],
                "temperature": 0,
            },
            timeout=settings.LLM_TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        aliases = _parse_aliases(content)
    except Exception:
        # 网络错误 / 超时 / 鉴权失败 / 返回结构异常 / JSON 解析失败：统一降级
        return _dedupe_keep_order(base), False

    # 强制包含原始输入
    return _dedupe_keep_order(base + aliases), True
