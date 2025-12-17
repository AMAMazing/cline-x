# Cline X Server (clinex.dev)

This is the central relay server for Cline X Sync. It connects your local Cline agent to a web-based interface, allowing remote access without temporary Ngrok URLs.

## Architecture

*   **Framework**: Next.js (App Router)
*   **Deployment**: Vercel (Serverless Functions)
*   **Communication**: HTTP Long Polling / Server-Sent Events (SSE) for relaying data between the Local Agent and the Web Client.

## Prerequisites

1.  **Node.js**: Install Node.js (v18 or later).
2.  **Vercel CLI**: Install globally via npm:
    ```bash
    npm install -g vercel
    ```

## Setup & Deployment

1.  **Navigate to this directory**:
    ```bash
    cd clinex_server
    ```

2.  **Install Dependencies**:
    ```bash
    npm install
    ```

3.  **Local Development** (Optional):
    ```bash
    npm run dev
    ```
    The server will start at `http://localhost:3000`.

4.  **Deploy to Vercel**:
    Run the deploy command and follow the prompts.
    ```bash
    vercel
    ```
    *   Set up and deploy? **Yes**
    *   Which scope? **(Select your account)**
    *   Link to existing project? **No**
    *   Project name? **clinex-server** (or your preferred name)
    *   Directory? **./**
    *   Modify settings? **No**

5.  **Production Deployment**:
    Once tested, deploy to production:
    ```bash
    vercel --prod
    ```

## Post-Deployment

1.  Copy the URL provided by Vercel (e.g., `https://clinex-server.vercel.app`).
2.  You may want to map a custom domain (like `clinex.dev`) in the Vercel dashboard.
3.  Update your local `clinex_agent.py` (or `clinex_config.json`) to point to this new URL.
