"""The Veritas assistant: answers visitors' questions about how Veritas works.

An OpenAI model writes the answers from a fixed description of Veritas (knowledge.py) and
nothing else. It has no tools, no accounts and no live data, so a prompt injection has
nothing to reach. guard.py refuses the obvious attempts before the model sees them and
checks the answers after; limits.py keeps each visitor, and the bill, within bounds.
"""
