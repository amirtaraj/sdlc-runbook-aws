# Data

All data in this folder is **synthetic**, written for this project. It contains no customer,
production, confidential or personal data.

| Path | What it is | Used by |
|---|---|---|
| `knowledge_base/standards.json` | Fictional engineering standards (architecture, security, data, operations, delivery) | Knowledge base (RAG) for the Design and Tasks agents, served by Azure AI Search (or the mock server locally) |
| `datasets/historical_tasks.csv` | Fictional past tasks with estimated vs actual days, by category | Estimation baseline given to the Tasks agent |

Locally, the knowledge base is served by `local_services` (keyword search over
`standards.json`). To use Azure AI Search instead, create an index named as in `SEARCH_INDEX`
with the fields `id` (key), `title`, `category` and `content` (all searchable strings), upload
the documents from `standards.json`, then set `SEARCH_ENDPOINT` and `SEARCH_KEY`.
