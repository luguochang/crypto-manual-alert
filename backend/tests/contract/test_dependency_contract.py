from importlib.metadata import version


def test_framework_compatibility_group() -> None:
    expected_versions = {
        "langchain": "1.3.13",
        "langgraph": "1.2.9",
        "langchain-openai": "1.3.5",
        "langchain-tavily": "0.2.18",
        "langgraph-checkpoint-postgres": "3.1.0",
        "langgraph-cli": "0.4.31",
        "langgraph-api": "0.11.1",
        "langgraph-sdk": "0.4.2",
        "langchain-protocol": "0.0.18",
        "langsmith": "0.10.2",
        "langfuse": "4.14.0",
        "deepagents": "0.6.12",
        "SQLAlchemy": "2.0.51",
        "alembic": "1.18.5",
        "asyncpg": "0.31.0",
        "fastapi": "0.139.0",
        "greenlet": "3.5.3",
        "httpx": "0.28.1",
        "pydantic": "2.13.4",
        "pydantic-settings": "2.14.2",
        "PyJWT": "2.13.0",
        "uvicorn": "0.51.0",
        "ddgs": "9.14.3",
    }

    installed_versions = {package: version(package) for package in expected_versions}

    assert installed_versions == expected_versions
