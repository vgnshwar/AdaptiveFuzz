import json
import uuid
from langgraph.types import interrupt
from langchain_core.tools import BaseTool
from typing import Any, Callable, Dict, List
from langchain_core.messages import HumanMessage, SystemMessage

from state import AdaptiveState
from tools import call_tools
from utils import get_llm, h_response, load_yaml_file
from paths import PROMPTS_CONFIG_PATH
from schemata import (
    conversational_handler_schema, 
    result_interpreter_schema,
    strategy_advisor_schema,
)
from consts import (
    TASKS,
    FINDINGS,
    STRATEGIES,
    TO_LOOP,
    IS_INAPPROPRIATE,
    TARGET_IP,
    USER_QUERY,
)


def make_ch_node(llm_model: str, prompt: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    llm = get_llm(llm_model)

    def conversational_handler_node(state: AdaptiveState) -> Dict[str, Any]:
        """Plan reconnaissance tasks from the user query."""
        
        target_ip = interrupt("📌  AdaptiveFuzz: Target IP")
        user_query = interrupt("Your assistant is coming online... \n Ask Anything!")
        
        # target_ip = "45.33.32.156"
        # user_query = "Check the open ports in the target ip and find vulnerabilities"
        
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content= "\n"
                "Here is the target IP Address: " + target_ip + "\n"
                + "Here is the user query: " + user_query 
            )
        ]

        ai_response = llm.with_structured_output(conversational_handler_schema).invoke(messages)
        response = ai_response.model_dump()
        
        tasks = response.get(TASKS, [])
        is_inappropriate = response.get(IS_INAPPROPRIATE, True)
        for task in tasks: task["task_id"] = str(uuid.uuid4())
        
        return {
            TO_LOOP: False,
            TASKS: tasks,
            TARGET_IP: target_ip,
            USER_QUERY: list(user_query),
            IS_INAPPROPRIATE: is_inappropriate
        }

    return conversational_handler_node


def make_re_node(llm_model: str, prompt: str, tools: List[BaseTool]) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    llm = get_llm(llm_model)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {tool.name: tool for tool in tools}

    async def recon_executor_node(state: AdaptiveState) -> Dict[str, Any]:
        """Execute tasks using MCP tools and record results (stub)."""
        tasks = state.get(TASKS, [])
        
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content= "\n"
                "Here are the pending tasks:" + json.dumps(tasks) + "\n"
                + "Solve this by executing the necessary tools." + "\n"
            ),
        ]

        ai_tool_call = await llm_with_tools.ainvoke(messages)
        tool_results = await call_tools(ai_tool_call, tool_map)
        
        by_task_id = {result.get("task_id"): result for result in tool_results}
        for task in tasks:
            result = by_task_id.get(task.get("task_id"))
            if result:
                task["status"] = "Completed"
                task["results"] = result.get("output")
        
        return {
            TASKS: tasks
        }

    return recon_executor_node


def make_wa_node(llm_mode: str, prompt: str, tools: List[BaseTool]) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    llm = get_llm(llm_mode)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {tool.name: tool for tool in tools}
    
    async def web_analyzer_node(state: AdaptiveState) -> Dict[str, Any]:
        """Analyze web-related findings (stub)."""
        tasks = state.get(TASKS, [])
        
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=prompt+ "\n"
                + "Now here are the tasks we already completed: " + json.dumps([task for task in tasks if task["status"] == "Completed"]) + "\n"
                + "Here are the tasks we couldn't complete: " + json.dumps([task for task in tasks if task["status"] != "Completed"]) + "\n"
            )
        ]
        
        ai_tool_call = await llm_with_tools.ainvoke(messages)
        tool_results = await call_tools(ai_tool_call, tool_map)
        
        by_task_id = {result.get("task_id"): result for result in tool_results}
        for task in tasks:
            result = by_task_id.get(task.get("task_id"))
            if result:
                task["web_info"] = result.get("output")
        
        return {
            TASKS: tasks
        }

    return web_analyzer_node


def make_ri_node(llm_model: str, prompt: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    llm = get_llm(llm_model)
    
    def result_interpreter_node(state: AdaptiveState) -> Dict[str, Any]:
        """Interpret tool results and extract findings (stub)."""
        tasks = state.get(TASKS, [])
        
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content= "\n"
                + "Here are the executed tasks with their results:" + json.dumps(tasks) + "\n"
                + "Based on the tool outputs, extract and list the most relevant security findings." + "\n"
            ),
        ]
        
        ai_response = llm.with_structured_output(result_interpreter_schema).invoke(messages)
        response = ai_response.model_dump()
        findings = response.get(FINDINGS, [])
        
        return {
            FINDINGS: findings
        }

    return result_interpreter_node


def make_sa_node(llm_model: str, prompt: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    llm = get_llm(llm_model)
    
    def strategy_advisor_node(state: AdaptiveState) -> Dict[str, Any]:
        """Advise on strategic next steps (stub)."""
        
        messages = [
            SystemMessage(content=prompt 
                + "Next strategies should be in the same format as the tasks here: " + json.dumps(state.get(TASKS, [])) + "\n"
            ),
            HumanMessage(content= "\n"
                + "Here are the current findings:" + json.dumps(state.get(FINDINGS, [])) + "\n"
                + "Based on these findings, suggest three strategic next steps for the penetration test." + "\n"
            )
        ]
        
        ai_response = llm.with_structured_output(strategy_advisor_schema).invoke(messages)
        response = ai_response.model_dump()
        strategies = response.get(STRATEGIES, [])
         
        return {
            STRATEGIES: strategies
        }

    return strategy_advisor_node


def make_hr_node() -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    def human_in_loop_node(state: AdaptiveState) -> Dict[str, Any]:
        """Engage human operator for decisions based on current state."""
        strategies = state.get(STRATEGIES, [])
        
        summary = h_response(
            completed_tasks=state.get(TASKS, []),
            findings=state.get(FINDINGS, []),
            strategies=strategies,
        )
        
        from_human = interrupt(summary)
        while from_human is None or from_human.strip() == "":
            from_human = interrupt("`Choices are numbered 1, 2, 3, etc. Type 'stop' to end the penetration test.`")
            
        to_loop = False if from_human.tolower() == "stop" else True
        user_query = strategies[int(from_human) - 1] if to_loop else ""

        return {
            TO_LOOP: to_loop,
            USER_QUERY: user_query
        }

    return human_in_loop_node
