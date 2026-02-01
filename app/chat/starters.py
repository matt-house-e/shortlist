"""Chat starter prompts for the welcome screen."""

import chainlit as cl

# Direct responses for starter prompts (skip LLM for faster feedback)
STARTER_DIRECT_RESPONSES = {
    "Help me find a product to buy": "Great! What type of product are you looking for?",
    "I want to compare different options for something I'm buying": "I can help you compare options. What product category are you researching?",
    "I have a budget and need recommendations": "Happy to help you find options within your budget. What are you shopping for, and what's your budget range?",
    "I need help deciding what to buy": "I'll help you make a decision. What kind of product are you considering?",
}


@cl.set_starters
async def set_starters():
    """Define starter prompts for the welcome screen."""
    return [
        cl.Starter(label="Find a Product", message="Help me find a product to buy"),
        cl.Starter(
            label="Compare Options",
            message="I want to compare different options for something I'm buying",
        ),
        cl.Starter(label="Budget Shopping", message="I have a budget and need recommendations"),
        cl.Starter(label="Quick Research", message="I need help deciding what to buy"),
    ]
