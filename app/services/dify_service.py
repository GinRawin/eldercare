"""
Dify 代理服务

职责：
1. 统一承接前端请求，后端再去调用 Dify，避免浏览器直连 Dify 导致的 CORS / 密钥暴露问题。
2. 统一管理提示词模板，把“短句、风险标签、免责声明、老人友好输出”写成后端约束。
3. 支持图片上传后的多模态识别，供前端的“拍照查风险”与“语音问一问”共用。

说明：
- 这里的“语音输入”不直接做语音识别，而是接收前端 Web Speech API 转写后的文本；
  前端会把语音转成文字，再交给这个服务。
- 如果后续要接入真正的后端 STT，也可以在这里扩展。
"""

from __future__ import annotations

import json

import httpx
from fastapi import HTTPException, UploadFile

from app.core.config import settings


def _agent_config(agent: str) -> tuple[str, str]:
    """返回 (agent_key, agent_label)。"""
    if agent == "med":
        return settings.DIFY_MED_API_KEY, "用药提醒助手"
    return settings.DIFY_DIET_API_KEY, "老年饮食健康助手"


def build_dify_prompt(agent: str, text: str, mode: str = "chat") -> str:
    """
    生成 Dify 系统/用户混合约束。

    设计目标：
    - 控制输出长度，避免老人读长文。
    - 强制带风险标签与免责声明。
    - 不返回 workflow 节点、调试日志、JSON。
    - 图片识别必须先给候选项，减少误识别风险。
    """
    diet_prompt = [
        "你是老年饮食健康助手。",
        "任务：识别药物、食物、饮食风险。",
        "输出必须极短，适合老人阅读。",
        "最多3条。每条不超过20字。",
        "必须包含风险标签：高风险/中风险/低风险。",
        "必须包含免责声明：仅供参考，请咨询医生。",
        "不要输出工作流节点、调试信息、JSON、Markdown表格。",
        "不要给出诊断、处方、剂量修改。",
        "若信息不足，先给确认问题，再给保守提醒。",
    ]

    med_prompt = [
        "你是用药提醒助手。",
        "任务：提醒用药、解释用法、提示相互作用。",
        "输出必须极短，适合老人阅读。",
        "最多3条。每条不超过20字。",
        "必须包含风险标签：高风险/中风险/低风险。",
        "必须包含免责声明：仅供参考，请咨询医生。",
        "不要输出工作流节点、调试信息、JSON、Markdown表格。",
        "不要给出诊断、处方、剂量修改。",
        "若老人有多药并用，优先提示核对药名与时间。",
    ]

    photo_rule = [
        "图片识别时先给候选项，再让用户确认。",
        "若识别不确定，必须说明“请再确认”。",
    ]

    voice_rule = [
        # 语音输入经过前端转写后再到后端，这里提醒 Dify 处理口语化、同音字和断句问题。
        "用户可能来自语音输入，请容忍口语化表达。",
        "必要时先做简单复述确认，再给结论。",
    ]

    core = med_prompt if agent == "med" else diet_prompt
    if mode == "photo":
        core.extend(photo_rule)
    if mode == "voice":
        core.extend(voice_rule)

    # 这里把用户原始输入原样传下去，避免前端把关键信息裁掉。
    core.append(f"用户输入：{text}")
    return "\n".join(core)


def compress_answer(text: str) -> str:
    """把 Dify 返回值压缩成短句，给老人直接看。"""
    raw = (text or "").replace("\r", "")
    lines = []
    for part in raw.split("\n"):
        s = part.strip().lstrip("•-*0123456789.、 ")
        if not s:
            continue
        if len(s) > 24:
            s = s[:24] + "…"
        lines.append(s)
        if len(lines) >= 3:
            break
    if not lines:
        return "仅供参考，请咨询医生。"
    if not any("免责声明" in x or "仅供参考" in x for x in lines):
        lines.append("仅供参考，请咨询医生。")
    return "\n".join(lines[:3])


async def _upload_file_to_dify(api_key: str, file: UploadFile) -> str:
    """先把图片上传到 Dify，拿到 upload_file_id。"""
    content = await file.read()
    async with httpx.AsyncClient(timeout=settings.DIFY_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.DIFY_BASE_URL.rstrip('/')}/v1/files/upload",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (file.filename or "upload.jpg", content, file.content_type or "application/octet-stream")},
            data={"user": "eldercare"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"]


async def chat_with_dify(
    agent: str,
    elder_id: str,
    query: str,
    conversation_id: str = "",
    file: UploadFile | None = None,
) -> dict:
    """统一调用 Dify Chat API。"""
    if not settings.DIFY_BASE_URL:
        raise HTTPException(status_code=400, detail="Dify base url is not configured")

    api_key, _label = _agent_config(agent)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"Dify api key for agent '{agent}' is not configured")

    payload: dict = {
        "inputs": {},
        "query": query,
        "response_mode": "blocking",
        "conversation_id": conversation_id or "",
        "user": elder_id,
    }

    if file is not None:
        upload_file_id = await _upload_file_to_dify(api_key, file)
        payload["files"] = [
            {
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": upload_file_id,
            }
        ]

    async with httpx.AsyncClient(timeout=settings.DIFY_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.DIFY_BASE_URL.rstrip('/')}/v1/chat-messages",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            content=json.dumps(payload),
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "answer": compress_answer(data.get("answer", "")),
            "conversation_id": data.get("conversation_id", ""),
            "raw": data,
        }
