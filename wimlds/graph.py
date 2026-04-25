"""
LangGraph workflow for social caption generation and Meta posting.
"""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from wimlds.agents.publishing.caption_agent import generate_caption
from wimlds.agents.publishing.facebook_node import post_facebook
from wimlds.agents.publishing.instagram_node import post_instagram


class SocialPostState(TypedDict, total=False):
    event: str
    description: str
    poster: str
    caption: str
    instagram_posted: bool
    facebook_posted: bool
    instagram_result: dict
    facebook_result: dict
    instagram_post_url: str
    facebook_post_url: str


def build_graph():
    workflow = StateGraph(SocialPostState)

    workflow.add_node("generate_caption", generate_caption)
    workflow.add_node("post_instagram", post_instagram)
    workflow.add_node("post_facebook", post_facebook)

    workflow.set_entry_point("generate_caption")
    workflow.add_edge("generate_caption", "post_instagram")
    workflow.add_edge("post_instagram", "post_facebook")
    workflow.add_edge("post_facebook", END)

    return workflow.compile()




