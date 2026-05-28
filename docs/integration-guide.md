# 接入指南

本文档面向调用当前后端模块的开发者，说明基础接口、MCP 工具接口、Agent 接口、聊天工作台接口与长期记忆接口的接入方式。

## 1. 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

在线文档：

- Swagger: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`

## 2. 基础数据接口

- `POST /api/v1/patients`
- `GET /api/v1/patients`
- `GET /api/v1/patients/{patient_id}`
- `GET /api/v1/patients/by-patient-no/{patient_no}`
- `PATCH /api/v1/patients/{patient_id}`
- `POST /api/v1/patients/{patient_id}/medical-records`
- `GET /api/v1/patients/{patient_id}/medical-records`
- `GET /api/v1/medical-records/{record_id}`
- `PATCH /api/v1/medical-records/{record_id}`
- `POST /api/v1/patients/{patient_id}/visits`
- `GET /api/v1/patients/{patient_id}/visits`
- `GET /api/v1/visits/{visit_id}`
- `PATCH /api/v1/visits/{visit_id}`

## 3. 图片上传与 `image_id`

上传接口：

- `POST /api/v1/images/upload`

请求体示例：

```json
{
  "file_name": "ankle.png",
  "content_base64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "mime_type": "image/png",
  "patient_id": "optional-patient-id",
  "record_id": "optional-record-id",
  "visit_id": "optional-visit-id",
  "image_type": "followup",
  "source": "patient_upload",
  "notes": "可选备注"
}
```

上传成功后，通过返回的 `id` 作为 `image_id` 使用。

## 4. MCP 接口

- `GET /api/v1/mcp/servers`
- `GET /api/v1/mcp/tools`
- `POST /api/v1/mcp/tools/{tool_name}/invoke`
- `POST /api/v1/mcp/agent/invoke`
- `POST /api/v1/mcp/case-image/search-query`
- `POST /api/v1/mcp/case-image/analyze`

推荐工具：

- `patient.get_patient_profile`
- `medical_record.search_records`
- `visit.search_visits`
- `identity.verify_patient_identity`
- `image.analyze_uploaded_image`
- `speech.generate_audio_file`

直接调用工具示例：

```json
POST /api/v1/mcp/tools/visit.search_visits/invoke
{
  "arguments": {
    "patient_no": "P40001",
    "date_from": "2026-04-27",
    "date_to": "2026-04-27",
    "limit": 1,
    "sort_by": "visit_time",
    "sort_order": "desc"
  },
  "verify_name": "刘洋",
  "verify_phone": "13900000005"
}
```

## 5. Agent 入口

### 5.1 同步调用

- `POST /api/v1/agent/invoke`

文本问答示例：

```json
{
  "message": "请帮我总结最近一次就诊情况",
  "verify_name": "刘洋",
  "verify_phone": "13900000005",
  "with_audio": true
}
```

带会话恢复示例：

```json
{
  "session_id": "existing-session-id",
  "message": "基于上一次结论再简短一点",
  "patient_id": "optional-patient-id",
  "verify_phone": "13900000005",
  "with_audio": false
}
```

图片问答示例：

```json
{
  "message": "请结合这张图判断是否与当前病情相关",
  "verify_name": "刘洋",
  "verify_phone": "13900000005",
  "image_id": "your-image-id",
  "with_audio": false
}
```

关键字段：

- `message`：必填
- `session_id`：可选，会话恢复
- `patient_id` / `patient_no` / `visit_no`：可选辅助定位
- `verify_name` / `verify_phone` / `verify_id_card`：身份核验字段
- `image_id`：旧的单图字段
- `attachments`：工作台附件引用列表
- `with_audio`：是否自动生成音频

### 5.2 流式调用

- `POST /api/v1/agent/stream`

返回格式为 SSE，当前事件类型包括：

- `session.created`
- `agent.phase`
- `answer.delta`
- `answer.done`
- `audio.ready`
- `agent.error`

工作台应优先使用 `agent/stream`，不可用时再回退到 `agent/invoke`。

## 6. 聊天工作台接口

会话：

- `POST /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{session_id}`
- `PATCH /api/v1/chat/sessions/{session_id}`
- `GET /api/v1/chat/sessions/{session_id}/messages`
- `GET /api/v1/chat/sessions/{session_id}/context`

附件：

- `POST /api/v1/chat/attachments/upload`
- `GET /api/v1/chat/attachments/{attachment_id}/preview`
- `GET /api/v1/chat/attachments/{attachment_id}/file`
- `DELETE /api/v1/chat/attachments/{attachment_id}`

附件上传当前使用 `multipart/form-data`，更适合前端直接上传文件。

## 7. 长期记忆接口

- `GET /api/v1/memory/patients/{patient_id}/events`
- `GET /api/v1/memory/patients/{patient_id}/profiles`
- `POST /api/v1/memory/patients/{patient_id}/recall`
- `GET /api/v1/memory/jobs/{job_id}`

当前规则：

- 同一 `session_id` 每累计 5 条 `user_input` 自动创建一个 `memory_extraction_job`
- 后台 worker 异步执行抽取
- `recall` 会返回：
  - `profiles`
  - `dense_hits`
  - `keyword_hits`
  - `fused_hits`

## 8. 环境变量

常用变量：

```env
AGENT_LLM_PROVIDER=qwen
AGENT_LLM_MODEL=qwen-plus
QWEN_API_KEY=your_qwen_api_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
QWEN_VISION_MODEL=qwen-vl-max-latest
QWEN_OMNI_TTS_MODEL=qwen3-omni-flash
QWEN_OMNI_TTS_VOICE=Cherry

DATABASE_URL=sqlite:///./patient_agent.db
MEMORY_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/patient_agent_memory
MEMORY_EXTRACTION_ENABLED=true
MEMORY_EXTRACTION_POLL_INTERVAL_SECONDS=5
MEMORY_EXTRACTION_BATCH_SIZE=1
MEMORY_EXTRACTION_MAX_RETRIES=3
MEMORY_EMBEDDING_ENABLED=true
MEMORY_EMBEDDING_MODEL=text-embedding-v4
MEMORY_EMBEDDING_DIMENSIONS=1024
MEMORY_RETRIEVAL_ENABLED=true
MEMORY_RETRIEVAL_TOPK=8
MEMORY_RETRIEVAL_DENSE_TOPN=10
MEMORY_RETRIEVAL_KEYWORD_TOPN=10
MEMORY_RRF_K=60
```

## 9. 错误码

- `400`：参数错误
- `403`：身份核验失败或患者归属不一致
- `404`：资源不存在
- `409`：唯一键冲突
- `422`：请求体验证失败
- `502`：下游工具执行失败
