# Cline-X

Cline-X is an automated workflow server and management interface integrated directly with the **Cline CLI** (`cline`).

## Features

- **Direct Cline CLI Integration**: Spawns and interacts with the `cline` CLI binary directly via subprocesses rather than relying on VS Code GUI window automation or UI clicking.
- **Autonomous Execution**: Full support for `--yolo` mode and target project directories via `--cwd`.
- **Live Output Streaming**: Captures and streams `stdout` and `stderr` directly from the active Cline CLI process for real-time status and task progress tracking.
- **Task Queue & Sprint Management**: Queue up multiple prompts across different repositories and projects.
- **Remote Access & Notifications**: Integrated ngrok tunneling, API key authentication, and ntfy notifications.

## Prerequisites

- Python 3.10+
- [Cline CLI](https://github.com/cline/cline) installed globally (`npm install -g cline`) or accessible in your PATH.

## Installation

1. Clone this repository:
```bash
git clone https://github.com/AMAMazing/cline-x.git
cd cline-x
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create your `.env` configuration:
```env
NGROK_AUTHTOKEN=your_ngrok_token_here
CLINE_X_API_KEY=your_optional_fixed_api_key
```

4. Run the server:
```bash
python main.py
```

The server will launch on `http://127.0.0.1:3001`.

## CLI Usage Example

Tasks dispatched via `/send_message` or `/api/queue` execute:
```bash
cline --yolo --cwd "/path/to/project" "Your prompt here"
```

## Architecture

- `modules/cline_cli_utils.py`: Locates the `cline` binary and manages asynchronous subprocess execution, stream piping, and termination.
- `modules/queue_manager.py`: Coordinates sequential task execution across projects using the CLI process runner.
- `modules/automation_utils.py`: Native CLI dispatch bridge.
- `modules/chat_manager.py`: Multi-project chat and session history store.
- `main.py`: Flask application server with REST endpoints and WebSocket/SSE streaming.
