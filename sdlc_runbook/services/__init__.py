"""Clients for the external REST APIs the runbook integrates with.

Each client speaks the real Azure / Azure DevOps wire contract, so pointing its endpoint
at the real service (instead of the local mock server) needs no code change:

  ContentSafetyClient  Azure AI Content Safety  - Prompt Shields (prompt-injection detection)
  PiiClient            Azure AI Language        - PII entity recognition
  KnowledgeBaseClient  Azure AI Search          - engineering-standards knowledge base (RAG)
  DevOpsClient         Azure DevOps REST        - work item creation (the simulated action)
"""
from .content_safety import ContentSafetyClient, ShieldResult
from .devops import DevOpsClient, WorkItem
from .knowledge_base import KnowledgeBaseClient, KnowledgeDoc
from .pii import PiiClient, PiiEntity

__all__ = [
    "ContentSafetyClient", "ShieldResult",
    "DevOpsClient", "WorkItem",
    "KnowledgeBaseClient", "KnowledgeDoc",
    "PiiClient", "PiiEntity",
]
