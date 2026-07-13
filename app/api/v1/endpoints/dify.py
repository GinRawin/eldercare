from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.services.dify_service import build_dify_prompt, chat_with_dify

router = APIRouter(prefix="/dify", tags=["dify"])


@router.post("/chat")
async def dify_chat(
    agent: str = Form("diet"),
    elder_id: str = Form(...),
    query: str = Form(...),
    conversation_id: str = Form(""),
    input_mode: str = Form("text"),
    file: UploadFile | None = File(default=None),
):
    # 这个接口是前端唯一需要调用的 Dify 入口。
    # 作用：
    # - 统一接收文字 / 语音转文字 / 图片。
    # - 后端补充提示词约束，避免前端散落规则。
    # - 返回已经压缩好的老人友好短句。
    # input_mode 由前端传入：text / voice / photo。
    mode = "photo" if file else ("voice" if input_mode == "voice" else "chat")
    prompt = build_dify_prompt(agent=agent, text=query, mode=mode)
    return await chat_with_dify(
        agent=agent,
        elder_id=elder_id,
        query=prompt,
        conversation_id=conversation_id,
        file=file,
    )
