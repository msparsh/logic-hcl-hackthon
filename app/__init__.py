"""Team Logic - Autonomous Customer Support Agent.

Modules:
    config      settings loaded from environment variables / .env
    db          PostgreSQL connection and repository (all SQL lives here)
    llm_client  LLM providers with automatic failover
    intent      intent parsing (LLM structured output + regex fallback) and replies
"""
