from typing import List, Optional, Dict, Any, Union
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
import time
import json
from starlette.responses import StreamingResponse, JSONResponse
import asyncio

app = FastAPI(title="OpenAI-compatible API")

class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, str]], Dict[str, str]]

    def get_content_text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, list):
            return " ".join(item["text"] for item in self.content if item.get("type") == "text")
        elif isinstance(self.content, dict):
            return self.content.get("text", "")
        return ""

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "gpt-3.5-turbo"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0
    stream: Optional[bool] = False
    stream_options: Optional[Dict] = None

@app.post("/chat/completions")
async def chat_completions(request: Request):
    try:
        json_data = await request.json()
        req = ChatCompletionRequest(**json_data)
        last_message = req.messages[-1].get_content_text() if req.messages else "No message"
        response_text = f"Echo: {last_message}"

        if req.stream:
            async def generate():
                response_id = f"chatcmpl-{int(time.time())}"
                
                # First chunk with role
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": req.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "finish_reason": None
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.1)

                # Stream each word
                words = response_text.split()
                for word in words:
                    chunk = {
                        "id": response_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": req.model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": word + " "},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    await asyncio.sleep(0.1)

                # Final chunk
                chunk = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": req.model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }]
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")

        response = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

        return JSONResponse(content=response)
        
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return JSONResponse(
            status_code=422,
            content={"error": {"message": str(e)}}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)hi