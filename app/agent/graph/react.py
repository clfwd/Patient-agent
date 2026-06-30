"""Adapters between task-board state and bounded ReAct worker execution."""

import json

from app.agent.tools import build_agent_tools

try:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import StructuredTool
except ImportError:  # pragma: no cover
    AIMessage = None
    HumanMessage = None
    SystemMessage = None
    ToolMessage = None
    StructuredTool = None

try:
    from langgraph.prebuilt import create_react_agent
except ImportError:  # pragma: no cover
    create_react_agent = None


def _stringify_content(content):
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content).strip()


def _safe_json(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def build_react_messages(state, task, system_prompt):
    conversation_summary = state.get("conversation_context_summary") or {}
    evidence = state.get("evidence_items") or []
    user_prompt = (
        "User question:\n{message}\n\n"
        "Task goal:\n{goal}\n\n"
        "Expected evidence:\n{expected}\n\n"
        "Conversation context summary:\n{summary}\n\n"
        "Existing evidence summary:\n{evidence}\n"
    ).format(
        message=state.get("message") or "",
        goal=task.get("goal") or "",
        expected=task.get("expected_evidence") or [],
        summary=_safe_json(conversation_summary),
        evidence=_safe_json(evidence[-8:]),
    )
    if SystemMessage is not None and HumanMessage is not None:
        return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]


def extract_react_messages(result):
    if isinstance(result, dict):
        return result.get("messages") or []
    return []


def summarize_react_result(messages):
    tool_calls = []
    tool_results = []
    final_text = ""
    for message in messages or []:
        calls = getattr(message, "tool_calls", None) or []
        for call in calls:
            tool_calls.append(call)
        if ToolMessage is not None and isinstance(message, ToolMessage):
            tool_results.append(
                {
                    "tool_call_id": getattr(message, "tool_call_id", None),
                    "name": getattr(message, "name", None),
                    "content": _stringify_content(getattr(message, "content", "")),
                }
            )
        content = _stringify_content(getattr(message, "content", ""))
        if content and (AIMessage is None or isinstance(message, AIMessage)):
            final_text = content
    return {"final_text": final_text, "tool_calls": tool_calls, "tool_results": tool_results}


class ToolCallBudget(object):
    def __init__(self, max_tool_steps):
        try:
            max_steps = int(max_tool_steps or 1)
        except (TypeError, ValueError):
            max_steps = 1
        self.max_tool_steps = max(1, max_steps)
        self.used_tool_steps = 0

    def check(self, tool_name):
        if self.used_tool_steps >= self.max_tool_steps:
            raise ValueError(
                "ReAct tool call limit exceeded for {0}: effective_max_tool_steps={1}".format(
                    tool_name,
                    self.max_tool_steps,
                )
            )
        self.used_tool_steps += 1

    def remaining(self):
        return max(0, self.max_tool_steps - self.used_tool_steps)


def wrap_tools_with_budget(tools, budget):
    if StructuredTool is None:
        return list(tools or [])
    wrapped = []
    for tool in tools or []:
        args_schema = getattr(tool, "args_schema", None)

        def invoke_tool(_tool=tool, **kwargs):
            budget.check(_tool.name)
            return _tool.invoke(kwargs)

        wrapped.append(
            StructuredTool.from_function(
                func=invoke_tool,
                name=tool.name,
                description=getattr(tool, "description", "") or "",
                args_schema=args_schema,
            )
        )
    return wrapped


def _invoke_bound_loop(llm, tools, messages, budget):
    bound = llm.bind_tools(tools)
    output_messages = list(messages)
    tool_by_name = {tool.name: tool for tool in tools}
    while budget.remaining() > 0:
        ai_message = bound.invoke(output_messages)
        output_messages.append(ai_message)
        calls = getattr(ai_message, "tool_calls", None) or []
        if not calls:
            return {"messages": output_messages}
        for call in calls:
            name = call.get("name")
            tool = tool_by_name.get(name)
            if tool is None:
                raise ValueError("Tool is not allowed for this worker: {0}".format(name))
            result = tool.invoke(call.get("args") or {})
            if ToolMessage is not None:
                output_messages.append(
                    ToolMessage(
                        content=_safe_json(result),
                        tool_call_id=call.get("id") or "tool_call",
                        name=name,
                    )
                )
            else:
                output_messages.append({"role": "tool", "content": _safe_json(result), "name": name})
    return {"messages": output_messages}


def run_bounded_react(service, state, task, tools, system_prompt):
    if service.llm is None or not tools:
        return None
    max_steps = task.get("effective_max_tool_steps") or task.get("max_tool_steps") or 1
    budget = ToolCallBudget(max_steps)
    bounded_tools = wrap_tools_with_budget(tools, budget)
    messages = build_react_messages(state, task, system_prompt)
    if create_react_agent is not None and hasattr(service.llm, "invoke"):
        graph = create_react_agent(service.llm, tools=bounded_tools, state_modifier=system_prompt)
        return graph.invoke({"messages": messages[1:]}, {"recursion_limit": max(3, int(max_steps) * 2 + 2)})
    if hasattr(service.llm, "bind_tools"):
        return _invoke_bound_loop(service.llm, bounded_tools, messages, budget)
    return None


def build_patient_react_tools(service, state, allowed_tools):
    toolset = build_agent_tools(service.mcp_registry, service.session_factory, state)
    return [tool for name, tool in toolset["tool_by_name"].items() if name in set(allowed_tools or [])]


class KnowledgeSearchArgs(object):
    pass


def build_knowledge_react_tools(service, state):
    knowledge_service = getattr(service, "medical_knowledge_service", None)
    if StructuredTool is None or knowledge_service is None:
        return []

    call_counts = {"medical_knowledge.search": 0, "medical_knowledge.deep_retrieve": 0}

    def search(query, limit=3):
        call_counts["medical_knowledge.search"] += 1
        if call_counts["medical_knowledge.search"] > 1:
            raise ValueError("medical_knowledge.search can only be called once in one task")
        hits = knowledge_service.search(query, limit=min(int(limit or 3), 5))
        _append_knowledge_tool_call(state, "medical_knowledge.search", {"query": query, "limit": limit}, hits)
        return hits

    def deep_retrieve(query, limit=5):
        call_counts["medical_knowledge.deep_retrieve"] += 1
        if call_counts["medical_knowledge.deep_retrieve"] > 1:
            raise ValueError("medical_knowledge.deep_retrieve can only be called once in one task")
        result = knowledge_service.deep_retrieve(query, limit=min(int(limit or 5), 5))
        _append_knowledge_tool_call(state, "medical_knowledge.deep_retrieve", {"query": query, "limit": limit}, result)
        return result

    from pydantic import BaseModel, Field, conint

    class SearchArgs(BaseModel):
        query: str = Field(..., description="Medical knowledge query.")
        limit: conint(ge=1, le=5) = Field(3, description="Maximum local chunks to return.")

    class DeepRetrieveArgs(BaseModel):
        query: str = Field(..., description="Complex medical knowledge query.")
        limit: conint(ge=1, le=5) = Field(5, description="Maximum reranked chunks to compress.")

    return [
        StructuredTool.from_function(
            func=search,
            name="medical_knowledge.search",
            description="Simple local medical knowledge search for straightforward concept questions.",
            args_schema=SearchArgs,
        ),
        StructuredTool.from_function(
            func=deep_retrieve,
            name="medical_knowledge.deep_retrieve",
            description="Complex local medical knowledge retrieval with query rewrite, multi-query RRF, reranking, and compression.",
            args_schema=DeepRetrieveArgs,
        ),
    ]


def _append_knowledge_tool_call(state, tool_name, arguments, result):
    payload = result if isinstance(result, dict) else {"hits": result}
    tool_calls = list(state.get("tool_calls") or [])
    tool_calls.append({"tool_name": tool_name, "arguments": arguments, "ok": True, "result": payload, "error": None})
    state["tool_calls"] = tool_calls
