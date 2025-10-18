import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ----------------------------------------------------------------

import asyncio
from typing import Any, Dict, List
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode

from state import AdaptiveState
from paths import PROMPTS_CONFIG_PATH
from tools import get_mcp_tools, filter_tools
from utils import wait_yaml_file, save_graph_visualization
from routes import route_from_human, route_from_conversational_handler
from nodes import (
    make_ch_node,
    make_re_node,
    make_wa_node,
    make_ri_node,
    make_sa_node,
    make_hr_node,
)
from consts import (
    CONVERSATIONAL_HANDLER,
    RECON_EXECUTOR,
    WEB_ANALYZER,
    RESULT_INTERPRETER,
    STRATEGY_ADVISOR,
    HUMAN_IN_LOOP,
    ADAPTIVE_SYSTEM,
    PROMPT_CONFIG,
    AGENTS,
    LLM,
)


async def build_adaptive_graph() -> StateGraph:
    """
    Build the AdaptiveFuzz graph.
    """
    graph = StateGraph(AdaptiveState)
    mcp_tools = await get_mcp_tools()
    adaptive_config = await wait_yaml_file(PROMPTS_CONFIG_PATH)
    config = adaptive_config[ADAPTIVE_SYSTEM]

    graph.add_node(CONVERSATIONAL_HANDLER, make_ch_node(
        llm_model=config[AGENTS][CONVERSATIONAL_HANDLER][LLM],
        prompt=config[AGENTS][CONVERSATIONAL_HANDLER][PROMPT_CONFIG],
    ))
    
    graph.add_node(RECON_EXECUTOR, make_re_node(
        llm_model=config[AGENTS][RECON_EXECUTOR][LLM], 
        prompt=config[AGENTS][RECON_EXECUTOR][PROMPT_CONFIG],
        tools=filter_tools(mcp_tools, 'recon')
    ))
    
    graph.add_node(WEB_ANALYZER, make_wa_node(
        llm_mode=config[AGENTS][WEB_ANALYZER][LLM],
        prompt=config[AGENTS][WEB_ANALYZER][PROMPT_CONFIG],
        tools=filter_tools(mcp_tools, 'web')
    ))
    
    graph.add_node(RESULT_INTERPRETER, make_ri_node(
        llm_model=config[AGENTS][RESULT_INTERPRETER][LLM], 
        prompt=config[AGENTS][RESULT_INTERPRETER][PROMPT_CONFIG]
    ))
    
    graph.add_node(STRATEGY_ADVISOR, make_sa_node(
        llm_model=config[AGENTS][STRATEGY_ADVISOR][LLM],
        prompt=config[AGENTS][STRATEGY_ADVISOR][PROMPT_CONFIG]
    ))
    
    graph.add_node(HUMAN_IN_LOOP, make_hr_node())
    
    graph.add_edge(START, CONVERSATIONAL_HANDLER)
    graph.add_conditional_edges(
        CONVERSATIONAL_HANDLER,
        route_from_conversational_handler,
        {
            "review": HUMAN_IN_LOOP,
            "proceed": RECON_EXECUTOR,
        }
    )
    
    graph.add_edge(RECON_EXECUTOR, WEB_ANALYZER)
    graph.add_edge(WEB_ANALYZER, RESULT_INTERPRETER)
    graph.add_edge(RESULT_INTERPRETER, STRATEGY_ADVISOR)
    graph.add_edge(STRATEGY_ADVISOR, HUMAN_IN_LOOP)    
    
    graph.add_conditional_edges(
        HUMAN_IN_LOOP,
        route_from_human,
        {
            "continue": RECON_EXECUTOR,
            "stop": END,
        },
    )
    
    ### Checkpointer for human loop
    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)


# graph = asyncio.run(build_adaptive_graph())
# saved_path = save_graph_visualization(graph)    
# print(f"➡️  Graph visualisation saved to: {saved_path}")