# Deploying the SDLC Runbook to AWS: Step-by-Step Guide

This guide takes you from a laptop with nothing installed to the SDLC Runbook running on one
AWS server, reachable only by your team, using Amazon Bedrock for the AI model. Follow the
steps in order; each one says how to check it worked.

```
Your team's browsers / scripts
        │  http://<SERVER_IP>:8000   (only from your team's IP addresses)
        ▼
┌──────────────── AWS EC2 server (Amazon Linux 2023) ────────────────┐
│  sdlc-api             web UI + API, port 8000                       │
│  sdlc-local-services  guardrails, search, work items, port 8001     │
│  /opt/sdlc-runbook/.env   settings                                  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ AWS SDK, signed with the server's IAM role (no API keys)
                    ┌──────────┴──────────┐
                    ▼                     ▼
   Amazon Bedrock (Nova Lite)     Amazon DynamoDB table
   the AI model                   saved runs (conversations)
```

**Time:** about 1–2 hours the first time. **Cost:** every resource uses its smallest
(cheapest) option: about **$12 a month** for the server and its address if left running
(**~$0 for the server itself** if your account is in the EC2 free tier; stop it when idle to
save most of the rest), plus about **$0.01–0.02 per run** on Bedrock. Saving runs in DynamoDB is
effectively free at this scale. The cost tables in step 5 show where these numbers come from. Prices are approximate
list prices for US regions; check the AWS pricing pages for your region.

> This is a buildathon POC: one server, plain HTTP, mock sign-in, access limited by IP address.

---

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Install software on your laptop](#2-install-software-on-your-laptop)
3. [Run it locally first (in VS Code)](#3-run-it-locally-first-in-vs-code)
4. [Build the deployment package](#4-build-the-deployment-package)
5. [Set up AWS](#5-set-up-aws)
6. [Copy the package to the server and connect](#6-copy-the-package-to-the-server-and-connect)
7. [Install the app on the server](#7-install-the-app-on-the-server)
8. [Set the environment variables](#8-set-the-environment-variables)
9. [Start, check and open the app](#9-start-check-and-open-the-app)
10. [Call the API](#10-call-the-api)
11. [Deploy changes](#11-deploy-changes)
12. [Day-to-day operations and clean-up](#12-day-to-day-operations-and-clean-up)
13. [Troubleshooting](#13-troubleshooting)
14. [Glossary](#14-glossary)

---

## 1. Prerequisites

### Access you need

| What | Why | Who can give it |
|---|---|---|
| An **AWS account** with permission to use **EC2**, **IAM** (create a role), **Amazon Bedrock**, **DynamoDB** and **AWS Budgets** | To create the server, the model access and the database | Your cloud / platform team |
| An **AWS region** where Amazon Nova Lite is available (e.g. `us-east-1`) | Everything goes in one region | Your cloud team |
| Your team's **public IP addresses or VPN range** (e.g. `203.0.113.0/24`) | Only these may reach the app | Network team, or search "what is my IP" for one laptop |
| The project code (`sdlc_in_AWS.zip` or the repository) | What you deploy | Your team |

Use synthetic or anonymised data only.

### Software on your laptop (Windows)

| Software | Version | Used for |
|---|---|---|
| **VS Code** | latest | Editor and terminals; connecting to the server |
| **Python** | 3.12 | Running the app locally, building the package, the API example |
| **Node.js** (LTS, includes npm) | 20 or newer | Building the web UI |
| **AWS CLI v2** | latest | Signing in to AWS from your laptop |
| **OpenSSH client** (`ssh`, `scp`) | built into Windows 10/11 | Copying files to and logging in to the server |

Download links, installer options and PATH entries are in [step 2](#2-install-software-on-your-laptop);
send that section to your IT team if they install software for you.

The AWS SDK for Python (`boto3`) is installed automatically with the app's packages.
Nothing is installed on the server by hand: the setup script does it.

---

## 2. Install software on your laptop

### 2.1 Install the tools (or ask IT to)

Download and run each installer. If your IT team installs software, send them this table.

| Software | Download | Installer choice | Add to **Path** (if not added automatically) |
|---|---|---|---|
| **VS Code** | https://code.visualstudio.com/download → **Windows x64**, *User* or *System Installer* | Keep **"Add to PATH"** ticked | `C:\Users\<you>\AppData\Local\Programs\Microsoft VS Code\bin` (User Installer) or `C:\Program Files\Microsoft VS Code\bin` (System Installer) |
| **Python 3.12** | https://www.python.org/downloads/windows/ → latest **Python 3.12.x** → **Windows installer (64-bit)** | Tick **"Add python.exe to PATH"** on the first screen | `C:\Users\<you>\AppData\Local\Programs\Python\Python312\` **and** its `Scripts\` subfolder (per-user install), or `C:\Program Files\Python312\` and `C:\Program Files\Python312\Scripts\` (all-users install) |
| **Node.js LTS** | https://nodejs.org/en/download → **LTS** → **Windows Installer (.msi), x64** | Defaults (includes npm and "Add to PATH") | `C:\Program Files\nodejs\` |
| **AWS CLI v2** | https://awscli.amazonaws.com/AWSCLIV2.msi (instructions: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) | Defaults | `C:\Program Files\Amazon\AWSCLIV2\` |
| **OpenSSH client** | Built into Windows 10/11. If missing: **Settings → System → Optional features → Add a feature → OpenSSH Client** | — | `C:\Windows\System32\OpenSSH\` |

**VS Code extensions** (open VS Code → Extensions view, `Ctrl+Shift+X`, search and **Install**):
- **Python** by Microsoft: https://marketplace.visualstudio.com/items?itemName=ms-python.python
- **Remote - SSH** by Microsoft: https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh

If the marketplace is blocked, IT can download each extension's `.vsix` from those pages and
install it with **Extensions view → `...` menu → Install from VSIX…**.

**How to add a folder to Path** (only if a check below fails):

1. Start menu → type **environment variables** → open
   - **Edit environment variables for your account** (just you, no admin rights needed), or
   - **Edit the system environment variables → Environment Variables…** (all users; IT/admin).
2. Select **Path** → **Edit…** → **New** → paste the folder from the table → **OK** → **OK**.
3. **Close and reopen** every Command Prompt and VS Code window (Path is read only at start-up).

**Use Command Prompt in VS Code** (all laptop commands in this guide are written for it):
`Ctrl+Shift+P` → **Terminal: Select Default Profile** → **Command Prompt**. New terminals
(**Terminal → New Terminal**) now open Command Prompt.

**Check** in a new terminal (each prints a version):

```bat
code --version
python --version
node --version
npm --version
aws --version
ssh -V
```

Expected: Python `3.12.x`, Node `v20` or newer, `aws-cli/2.x`. If a command says *"is not
recognized as an internal or external command"*, add that program's folder to Path (above).
If `python` opens the Microsoft Store instead: **Settings → Apps → Advanced app settings → App
execution aliases** → turn off **python.exe** and **python3.exe**.

### 2.2 Sign in to AWS from your laptop

Ask your cloud team which method you use, then run one of (in the VS Code terminal):

```bat
aws configure sso          # if your organisation uses AWS SSO (IAM Identity Center)
aws configure              # if you were given an access key ID and secret
```

Enter your region (e.g. `us-east-1`) and output format `json`.

**Check:** `aws sts get-caller-identity` prints your account number. Your AWS user needs
permission to call Bedrock for the local run (step 3); ask your cloud team if it's denied.

---

## 3. Run it locally first (in VS Code)

Proves the code and your Bedrock access work before the server is involved.
Do [step 5.1](#51-turn-on-the-model-in-bedrock) (turn on the model) first.

### 3.1 Open the project

1. Unzip the project, e.g. to `C:\work\sdlc-runbook`.
2. VS Code → **File → Open Folder…** → choose that folder → **Yes, I trust the authors**.

### 3.2 Create a Python environment

1. `Ctrl+Shift+P` → **Python: Create Environment** → **Venv** → **Python 3.12** → tick
   `requirements.txt`. VS Code creates a `.venv` folder and installs the packages.
2. **Terminal → New Terminal** (Command Prompt). The prompt should start with `(.venv)`. If it
   doesn't, run `.venv\Scripts\activate.bat`.

### 3.3 Add your settings

```bat
copy .env.example .env
code .env
```

Set these lines (your region and model ID from step 5.1), then save (`Ctrl+S`):

```
LLM_PROVIDER=bedrock
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
MOCK_AUTH=yes
RUN_STORE=memory
```

`RUN_STORE=memory` keeps runs only while the app is running, which is fine locally. (To use the
DynamoDB table from your laptop too, set `RUN_STORE=dynamodb` after step 5.2.)

If you use AWS SSO, run `aws sso login` in the terminal before starting the servers.

### 3.4 Build the web UI

```bat
cd frontend
npm install
npm run build
cd ..
```

### 3.5 Start the two servers

Split the terminal (the **split** icon in the terminal panel, or `Ctrl+Shift+5`) and run one
command in each half:

```bat
python -m uvicorn local_services.app:app --host 127.0.0.1 --port 8001
```

```bat
python -m uvicorn sdlc_runbook.interfaces.api:create_app --factory --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**, sign in with any email as **Approver**, and run one of the
documents in `samples/`. Stop each server with `Ctrl+C`.

**Check:** a run reaches the final "Runbook pack" card and **Download spec pack** works.

---

## 4. Build the deployment package

In the VS Code terminal (project folder, `.venv` active):

```bat
cd frontend
npm run build
cd ..
python deploy\make_package.py
```

**Check:** it prints `... files -> ...\deploy\sdlc-runbook.zip ... .env not included.`

The package contains the code, the built UI and the server scripts. It **never contains
`.env`**: settings are added on the server in step 8.

---

## 5. Set up AWS

Use the **AWS console** (https://console.aws.amazon.com). Pick your region in the top-right
corner and keep it the same for every step.

### AWS resources you will create

| # | Resource | Name in this guide | SKU / option to pick (cheapest that works) | Purpose | Approx. cost |
|---|---|---|---|---|---|
| 5.1 | **Bedrock model access** | Amazon Nova Lite | Model `amazon.nova-lite-v1:0`, **On-Demand** (never Provisioned Throughput) | The AI model the agents call | ~$0.01–0.02 per run, nothing when idle |
| 5.1 | **Budget** | `sdlc-runbook-budget` | Monthly cost budget, **$20** | Email alert before costs surprise anyone | Free |
| 5.2 | **DynamoDB table** | `sdlc-runbook-runs` | **On-demand** capacity, **DynamoDB Standard** table class | Saves every run (the conversation) so it survives restarts | ~$0 (free tier: 25 GB storage) |
| 5.3 | **Key pair** | `sdlc-runbook-key` | RSA, .pem | Lets you log in to the server | Free |
| 5.4 | **Security group** | `sdlc-runbook-sg` | 2 inbound rules | Firewall: only your team's IPs reach the app | Free |
| 5.5 | **IAM role** | `sdlc-runbook-ec2-role` | One inline policy | Lets the server call Bedrock and DynamoDB without keys | Free |
| 5.6 | **EC2 instance** | `sdlc-runbook-poc` | **`t3.micro`**, **8 GiB gp3** disk | The server that runs the app | ~$8/month running (free tier: $0), ~$0.65/month stopped |
| 5.7 | **Elastic IP** | — | 1 address | A fixed address for the server | ~$3.60/month |

### 5.1 Turn on the model in Bedrock

Bedrock models are **serverless**: there is nothing to deploy or host, you pay only per use,
and there is no cost when idle. Use **On-Demand** pricing (the default). **Never buy
"Provisioned Throughput"**: it is billed by the hour and costs hundreds of dollars a month
even when idle.

**Model prices** (approximate On-Demand list prices, US regions, per **1 million** tokens):

| Model | Model ID | Input | Output | Fit |
|---|---|---|---|---|
| Amazon Nova Micro | `amazon.nova-micro-v1:0` | ~$0.035 | ~$0.14 | Cheapest; may give thin designs and specs |
| **Amazon Nova Lite** (use this) | `amazon.nova-lite-v1:0` | ~$0.06 | ~$0.24 | Best cost-to-quality balance for the whole pipeline |
| Amazon Nova Pro | `amazon.nova-pro-v1:0` | ~$0.80 | ~$3.20 | Richer output, more than 10× the cost |
| Anthropic Claude Haiku | see the Bedrock model catalog | ~$0.80–1.00 | ~$4–5 | High quality, highest cost here |

**What a run costs.** A full run (five stages, about 10–15 task specifications) uses very
roughly 60,000–120,000 tokens:

| Model | Approx. cost per run | 100 runs |
|---|---|---|
| Nova Micro | < $0.01 | < $1 |
| **Nova Lite** | ~$0.01–0.02 | ~$1–2 |
| Nova Pro | ~$0.10–0.25 | ~$10–25 |
| Claude Haiku | ~$0.15–0.35 | ~$15–35 |

The app's **Operations** panel shows the actual tokens and estimated cost of every run.

**Turn on the model:**

1. Console → search **Amazon Bedrock** (check the region in the top-right).
2. Left menu → **Model access** (or **Model catalog**) → find **Nova Lite** → **Request access**
   / **Enable** → wait for **Access granted** (usually immediate).
3. Note the model ID `amazon.nova-lite-v1:0`. If the model page only offers an *inference
   profile* ID such as `us.amazon.nova-lite-v1:0`, use that instead.
4. Optional test: Bedrock → **Playgrounds → Chat** → Nova Lite → send "Hello".

**Budget alert (do this now):** console → **Billing and Cost Management → Budgets → Create
budget** → **Use a template** → *Monthly cost budget* → name `sdlc-runbook-budget` → **$20** →
your email → **Create budget** (it alerts at 85% and 100%). You'll get an email before
costs surprise anyone.

### 5.2 Create the database table (saves the runs)

Every run (the requirement, each stage's output, your approvals and edits, the gate results)
is saved in one DynamoDB table after every action, so runs survive restarts and updates.

1. Console → search **DynamoDB** → **Tables** → **Create table**.
2. **Table name:** `sdlc-runbook-runs`.
3. **Partition key:** `run_id`, type **String**. Leave *Sort key* empty.
4. **Table settings:** **Customize settings** →
   - **Table class:** **DynamoDB Standard** (Standard-IA only saves money on large, rarely read tables).
   - **Capacity mode:** **On-demand** (pay per request, nothing when idle; cheaper than
     provisioned capacity for occasional use).
   - Leave everything else (encryption, no secondary indexes) as it is.
5. **Create table**. Wait until the status is **Active** (a few seconds).

There is nothing to install and no password: the server reaches the table with its IAM role.

### 5.3 Create a key pair (lets you log in to the server)

1. Search **EC2** → left menu **Key Pairs** → **Create key pair**.
2. Name `sdlc-runbook-key` · Type **RSA** · Format **.pem** → **Create**.
3. Move the downloaded `sdlc-runbook-key.pem` to `C:\Users\<you>\.ssh\` (create the `.ssh`
   folder if needed), then restrict it so SSH accepts it (Command Prompt):

   ```bat
   icacls "%USERPROFILE%\.ssh\sdlc-runbook-key.pem" /inheritance:r
   icacls "%USERPROFILE%\.ssh\sdlc-runbook-key.pem" /grant:r "%USERNAME%:(R)"
   ```

Keep this file private: anyone with it can log in to the server.

### 5.4 Create a security group (the IP restriction)

1. EC2 → **Security Groups** → **Create security group**.
2. Name `sdlc-runbook-sg` · Description `SDLC Runbook POC` · VPC: the default.
3. **Inbound rules** → **Add rule** twice:

   | Type | Port | Source | Purpose |
   |---|---|---|---|
   | SSH | 22 | **My IP** | You logging in |
   | Custom TCP | 8000 | Your team's IP range (e.g. `203.0.113.0/24`) | The app |

4. Leave outbound rules as they are → **Create security group**.

Only the listed IPs can reach the server. Never use `0.0.0.0/0` (the whole internet).
To give someone else access later, add their IP to the port-8000 rule.

### 5.5 Create an IAM role (lets the server call Bedrock and DynamoDB)

1. Search **IAM** → **Roles** → **Create role**.
2. Trusted entity **AWS service** → Use case **EC2** → **Next** → **Next**.
3. Role name `sdlc-runbook-ec2-role` → **Create role**.
4. Open the role → **Add permissions → Create inline policy** → **JSON** → paste (replace
   `<REGION>` and `<ACCOUNT_ID>`, the 12-digit number in the top-right account menu):

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
         "Resource": [
           "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
           "arn:aws:bedrock:<REGION>:<ACCOUNT_ID>:inference-profile/*"
         ]
       },
       {
         "Effect": "Allow",
         "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Scan"],
         "Resource": "arn:aws:dynamodb:<REGION>:<ACCOUNT_ID>:table/sdlc-runbook-runs"
       }
     ]
   }
   ```

5. Name it `sdlc-runbook-permissions` → **Create policy**.

The role allows only Nova Lite and only this one table, so the POC can't be switched to an
expensive model, or touch other data, by mistake.

### 5.6 Launch the server

**Server prices** (approximate On-Demand, US regions, running 24×7). The app needs little
CPU because the model runs in Bedrock, so the smallest size is enough:

| Instance type | CPU / memory | Approx. per month | Notes |
|---|---|---|---|
| **`t3.micro`** (use this) | 2 vCPU / 1 GB | ~$8, **$0 on the free tier** | Smallest size that runs the app; `setup.sh` adds swap so the install fits in 1 GB |
| `t3.small` | 2 vCPU / 2 GB | ~$15 | Only if the server feels slow with several people on it (change type while stopped) |

Add about $0.65/month for the 8 GiB disk (gp3 is the cheapest SSD type) and about
$3.60/month for the public IP address. A **stopped** server pays only for disk and the IP.

1. EC2 → **Instances** → **Launch instances**.
2. **Name:** `sdlc-runbook-poc`.
3. **Image:** **Amazon Linux 2023 AMI**, **64-bit (x86)**.
4. **Instance type:** `t3.micro` (marked *Free tier eligible* if your account qualifies).
5. **Key pair:** `sdlc-runbook-key`.
6. **Network settings → Edit:** Auto-assign public IP **Enable** · **Select existing security
   group** → `sdlc-runbook-sg`.
7. **Storage:** keep the default **8 GiB gp3** (enough: the app and its packages use about 1 GB).
8. **Advanced details → IAM instance profile:** `sdlc-runbook-ec2-role` (**required**).
9. **Launch instance** → **View all instances**. Wait for **Running** and **2/2 checks passed**.

### 5.7 Give the server a fixed address (Elastic IP)

Without this, the address changes every time the server is stopped and started.

1. EC2 → **Elastic IPs** → **Allocate Elastic IP address** → **Allocate**.
2. Select it → **Actions → Associate Elastic IP address** → Instance `sdlc-runbook-poc` → **Associate**.
3. Note the address, e.g. `54.12.34.56`. This guide calls it **`<SERVER_IP>`**.

---

## 6. Copy the package to the server and connect

In the VS Code terminal on your laptop (project folder):

```bat
scp -i "%USERPROFILE%\.ssh\sdlc-runbook-key.pem" deploy\sdlc-runbook.zip ec2-user@<SERVER_IP>:~/
scp -i "%USERPROFILE%\.ssh\sdlc-runbook-key.pem" deploy\ec2\setup.sh ec2-user@<SERVER_IP>:~/
ssh -i "%USERPROFILE%\.ssh\sdlc-runbook-key.pem" ec2-user@<SERVER_IP>
```

The first time, type `yes` to "continue connecting". The prompt changes to
`[ec2-user@ip-... ~]$`: you are on the server.

**Check:** `ls ~` shows `sdlc-runbook.zip` and `setup.sh`.

**Optional, work on the server inside VS Code:** `Ctrl+Shift+P` → **Remote-SSH: Open SSH
Configuration File…** → add the block below → `Ctrl+Shift+P` → **Remote-SSH: Connect to Host…**
→ `sdlc-runbook-poc` → **Linux**. You get a server terminal, and after step 7 you can open
`/opt/sdlc-runbook` as a folder.

```
Host sdlc-runbook-poc
    HostName <SERVER_IP>
    User ec2-user
    IdentityFile ~/.ssh/sdlc-runbook-key.pem
```

---

## 7. Install the app on the server

On the server:

```bash
bash ~/setup.sh
```

It adds a swap file (extra memory on disk for the 1 GB server), installs Python, unpacks the app into `/opt/sdlc-runbook`, installs the packages, creates
`/opt/sdlc-runbook/.env`, and registers two background services (`sdlc-local-services`,
`sdlc-api`) that restart automatically after a crash or reboot.

**Check:** it ends with `Done. Next:`.

---

## 8. Set the environment variables

The app reads its settings from **`/opt/sdlc-runbook/.env`** on the server. Open it:

```bash
nano /opt/sdlc-runbook/.env
```

(or open it in VS Code via Remote - SSH), and make sure these lines are set:

| Variable | Value | Notes |
|---|---|---|
| `LLM_PROVIDER` | `bedrock` | Use Amazon Bedrock |
| `AWS_REGION` | e.g. `us-east-1` | The region where you enabled the model |
| `BEDROCK_MODEL_ID` | `amazon.nova-lite-v1:0` | Or the inference profile ID from 5.1 |
| `MOCK_AUTH` | `yes` | POC sign-in: pick any email and role. Protected by the IP rule in 5.4 |
| `RUN_STORE` | `dynamodb` | Save runs in the DynamoDB table |
| `DYNAMODB_TABLE` | `sdlc-runbook-runs` | The table from 5.2 |

Everything else can stay as in the example file. There is **no API key or database
password**: the server's IAM role (5.5) authorises Bedrock and DynamoDB.

Save with `Ctrl+O`, `Enter`, and exit with `Ctrl+X`.

---

## 9. Start, check and open the app

On the server:

```bash
sudo systemctl restart sdlc-local-services sdlc-api
curl http://localhost:8000/health
```

**Check:** it prints JSON with `"status":"ok"` and `"model_provider":"bedrock"`.

On your laptop, open **http://<SERVER_IP>:8000**, sign in as **Approver**, choose a tech
stack, attach a file from `samples/`, and run it end to end.

**Check the database:** DynamoDB → **Tables** → `sdlc-runbook-runs` → **Explore table items**
shows one item per run. Restart the app (`sudo systemctl restart sdlc-api`) and refresh the
browser: your runs are still in the history list.

---

## 10. Call the API

Everything the UI does is available over HTTP at `http://<SERVER_IP>:8000`.

**Sign-in for API calls:** each request carries a header with a base64-encoded identity:
`Authorization: Mock <base64 of {"name":"...","email":"...","roles":["Runbook.Approver"]}>`.
Use `Runbook.Approver` (start and approve) or `Runbook.Viewer` (read only).

### Easiest: the example script

In the VS Code terminal on your laptop (`.venv` active):

```bat
python deploy\call_api.py --base-url http://<SERVER_IP>:8000
python deploy\call_api.py --base-url http://<SERVER_IP>:8000 --full-run
```

The first command runs quick read-only checks; the second runs the whole pipeline and saves
the spec pack.

`--full-run` starts a run, approves every stage and saves `<run-id>-spec-pack.zip` in the
current folder (a few cents of Bedrock usage).

### With curl (built into Windows)

```bat
curl http://<SERVER_IP>:8000/health
```

Other endpoints need the sign-in header above, which is easiest to build in Python; the script
`deploy\call_api.py` shows each call (start, approve, download) step by step.

### Main endpoints

| Method & path | What it does |
|---|---|
| `GET /health` | Server status (no sign-in needed) |
| `POST /runs` | Start a run: `{"requirement_text": "..."}` |
| `GET /runs/{id}` | Current state of a run |
| `POST /runs/{id}/approve` | Approve the current stage: `{}` |
| `POST /runs/{id}/edit` | Revise the current stage: `{"correction_text": "..."}` |
| `POST /runs/{id}/reject` | Stop the run |
| `GET /runs/{id}/spec-pack` | Download the spec pack (zip) |

**Tips:** start, approve and edit wait for the model, so allow up to 5 minutes per call. `401` = missing or malformed sign-in header; `409` = action doesn't fit
the run's state; `422` = a guardrail blocked the text (the response says why).

---

## 11. Deploy changes

Whenever the code changes:

1. **Laptop:** rebuild the package.

   ```bat
   cd frontend && npm run build && cd ..
   python deploy\make_package.py
   ```

2. **Laptop:** copy it to the server.

   ```bat
   scp -i "%USERPROFILE%\.ssh\sdlc-runbook-key.pem" deploy\sdlc-runbook.zip ec2-user@<SERVER_IP>:~/
   ```

3. **Server:** install it.

   ```bash
   bash /opt/sdlc-runbook/deploy/ec2/update.sh
   ```

   **Check:** it ends with `Update OK`.

Your `.env`, outputs and **all runs** (saved in DynamoDB) are kept, so people can carry on
where they left off. Avoid deploying while someone is waiting on a stage, as that one request
is interrupted.
**Changing only a setting:** edit `.env`, then `sudo systemctl restart sdlc-api`.

---

## 12. Day-to-day operations and clean-up

| Task | How (on the server) |
|---|---|
| Live logs | `journalctl -u sdlc-api -f` (stop with `Ctrl+C`) |
| Restart | `sudo systemctl restart sdlc-local-services sdlc-api` |

**Save money:** EC2 → Instances → select → **Instance state → Stop** when not in use, and
**Start** when needed. The address stays the same and the app starts automatically.

**When the buildathon is over, delete everything:**
1. EC2 → Instances → **Terminate** `sdlc-runbook-poc`.
2. Elastic IPs → **Release** the address.
3. DynamoDB → Tables → select `sdlc-runbook-runs` → **Delete** (this deletes all saved runs).
4. Delete the security group `sdlc-runbook-sg`, the key pair `sdlc-runbook-key`, and the IAM
   role `sdlc-runbook-ec2-role`.

Bedrock has nothing to delete.

---

## 13. Troubleshooting

| Problem | Fix |
|---|---|
| `ssh: connect ... timed out` | Your IP changed: edit `sdlc-runbook-sg` → SSH rule → source **My IP** |
| `Permissions for '...pem' are too open` | Run the `icacls` commands in 5.3 |
| Browser can't open `http://<SERVER_IP>:8000` | Add your IP to the port-8000 rule in `sdlc-runbook-sg`; on the server, `curl localhost:8000/health` |
| Server slow, or `pip` killed during `setup.sh` | Check the swap is on: `swapon --show`. If it still struggles, stop the server → **Actions → Instance settings → Change instance type** → `t3.small` → start |
| `setup.sh` fails installing Python | Run `sudo dnf install -y python3.11 python3.11-pip unzip`, then `bash ~/setup.sh` again |
| Every run "blocked: guardrail check could not run" | `sudo systemctl restart sdlc-local-services` |
| Bedrock `AccessDeniedException` | Model access not granted in this region (5.1), or the IAM role isn't attached to the server (EC2 → Actions → Security → Modify IAM role) |
| Bedrock `... on-demand throughput isn't supported` | Use the inference profile ID, e.g. `us.amazon.nova-lite-v1:0`, in `BEDROCK_MODEL_ID` |
| Runs disappear after a restart / log says "Could not save run ... DynamoDB" | Check `RUN_STORE=dynamodb` and `DYNAMODB_TABLE` in `.env`, that the table exists in `AWS_REGION`, and that the IAM policy (5.5) includes the table |
| "Unable to locate credentials" | Server: attach the IAM role (5.5). Laptop: `aws configure` or `aws sso login` |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **EC2** | AWS's virtual servers ("instances") |
| **Security group** | The server's firewall: which IPs may reach which ports |
| **Key pair / .pem** | The private key that lets you log in to the server |
| **Elastic IP** | A fixed public IP address for the server |
| **IAM role** | Permissions given to the server itself, so no passwords or keys are stored on it |
| **Amazon Bedrock** | AWS's service for calling AI models without hosting them |
| **On-Demand** | Pay-per-use pricing (Bedrock and DynamoDB): no commitment, no idle cost |
| **Amazon DynamoDB** | AWS's serverless database; here, one item per saved run |
| **Provisioned Throughput** | Bedrock capacity billed by the hour: not for this POC |
| **Path** | The Windows list of folders searched for commands like `python` or `aws` |
| **`.env`** | The settings file the app reads at start-up; never shared |
| **SSH / scp** | Logging in to / copying files to the server |
| **systemd service** | A program Linux keeps running in the background |
| **Mock sign-in** | POC sign-in that trusts the identity the browser sends |
