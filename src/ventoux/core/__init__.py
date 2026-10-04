"""The pure core: schema, expressions, catalog, provenance, validation and the interpreter.

Imports nothing else from Ventoux, and never Temporal or an LLM SDK: this code runs inside a
Temporal workflow, where replay needs the same decisions every time, and in a plain test.
"""
