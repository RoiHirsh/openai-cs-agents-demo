# Lucentive Club Agent System

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![NextJS](https://img.shields.io/badge/Built_with-NextJS-blue)
![OpenAI API](https://img.shields.io/badge/Powered_by-OpenAI_API-orange)

This repository contains the Lucentive Club agent system built on top of the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/). It provides AI-powered customer service for Lucentive Club's AI trading bot financing services.

It is composed of two parts:

1. A python backend that handles the agent orchestration logic for Lucentive Club's customer service workflows

2. A Next.js UI allowing the visualization of the agent orchestration process and providing a chat interface. It uses [ChatKit](https://openai.github.io/chatkit-js/) to provide a high-quality chat interface.

![Demo Screenshot](screenshot.jpg)

## How to use

### Setting your OpenAI API key

You can set your OpenAI API key in your environment variables by running the following command in your terminal:

```bash
export OPENAI_API_KEY=your_api_key
```

You can also follow [these instructions](https://platform.openai.com/docs/libraries#create-and-export-an-api-key) to set your OpenAI key at a global level.

Alternatively, you can set the `OPENAI_API_KEY` environment variable in an `.env` file at the root of the `python-backend` folder. You will need to install the `python-dotenv` package to load the environment variables from the `.env` file. And then, add these lines of code to your app:

```bash
from dotenv import load_dotenv

load_dotenv()
```

### Install dependencies

Install the dependencies for the backend by running the following commands:

```bash
cd python-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For the UI, you can run:

```bash
cd ui
npm install
```

### Run the app

You can either run the backend independently if you want to use a separate UI, or run both the UI and backend at the same time.

#### Run the backend independently

From the `python-backend` folder, run:

```bash
python -m uvicorn main:app --reload --port 8000
```

The backend will be available at: [http://localhost:8000](http://localhost:8000)

#### Run the UI & backend simultaneously

From the `ui` folder, run:

```bash
npm run dev
```

The frontend will be available at: [http://localhost:3000](http://localhost:3000)

This command will also start the backend.

## Deploy on Railway

When deploying the **Python backend** with Railway (Railpack), the default Python 3.13.x may not have precompiled binaries yet. To avoid `mise ERROR no precompiled python found`:

1. In Railway: open your **backend service** → **Variables**.
2. Add a variable: **`RAILPACK_PYTHON_VERSION`** = **`3.12`** (or `3.12.7`).
3. Redeploy.

This forces Railpack to use Python 3.12 instead of 3.13. The repo also includes `runtime.txt` and `python-backend/runtime.txt` with `python-3.12.7`; if the build still picks 3.13, the env var overrides it.

## Customization

This app is designed for demonstration purposes. Feel free to update the agent prompts, guardrails, and tools to fit your own customer service workflows or experiment with new use cases! The modular structure makes it easy to extend or modify the orchestration logic for your needs.

## Agents included

- Triage Agent: entry point that routes to specialists based on customer needs.
- Scheduling Agent: handles call scheduling requests and suggests available call times.
- Onboarding Agent: guides new leads through the onboarding process (trading experience, budget, broker setup).
- Investments FAQ Agent: answers investment-related questions about trading bots, stocks, investments, and related topics.

## Features

- **Intelligent Routing**: The Triage Agent automatically routes customers to the appropriate specialist based on their needs
- **Call Scheduling**: The Scheduling Agent handles call booking with availability checking and Calendly integration
- **Onboarding Flow**: The Onboarding Agent guides new leads through a structured onboarding process
- **Investment FAQs**: The Investments FAQ Agent provides answers to questions about trading bots, investments, and related topics
- **Guardrails**: Input guardrails ensure conversations stay focused on Lucentive Club services and prevent inappropriate requests

## Contributing

You are welcome to open issues or submit PRs to improve this app, however, please note that we may not review all suggestions.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
