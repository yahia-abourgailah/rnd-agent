"""Graph nodes for the chatbot agent.

Nothing is re-exported here on purpose: the `chatbot` node lives in a module of
the same name, so `from .chatbot import chatbot` would bind the function to
`chatbot_agent.nodes.chatbot` and shadow the module itself. Import from the
full path instead.
"""
