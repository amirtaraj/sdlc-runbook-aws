"""Custom, zero-cost implementations of the external APIs the runbook integrates with.

Each route speaks the real service's wire contract, so the runbook's clients work
unchanged against either this server or the real Azure service:

  POST /contentsafety/text:shieldPrompt          Azure AI Content Safety - Prompt Shields
  POST /language/:analyze-text                    Azure AI Language - PII entity recognition
  POST /indexes/{index}/docs/search               Azure AI Search - document search
  POST /devops/{org}/{project}/_apis/wit/workitems/{type}   Azure DevOps - create work item

Run: python -m uvicorn local_services.app:app --port 8001
"""
