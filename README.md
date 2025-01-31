# Cline X (Web interface)

A Python-based API bridge that enables Cline (VS Code Extension) to interact with the LLMs web interface, providing OpenAI-compatible API endpoints for seamless integration.

## Overview

This project creates a Flask server that acts as a middleware between Cline and LLM webchat interface, translating API requests into web interactions. It simulates an OpenAI-compatible API endpoint, allowing Cline to use the web interface as if it were communicating with the OpenAI API.

## Features

- OpenAI-compatible API endpoints
- Automated browser interaction with LLM logged in
- Request rate limiting and management
- Clipboard-based data transfer
- Streaming response support
- Comprehensive error handling and logging
- Support for various content formats

## Prerequisites

- Python 3.6+
- Windows OS (due to win32clipboard dependency)
- Chrome/Firefox browser installed
- Active LLM account logged in

Required Python packages:
```
flask
pywin32
pyautogui
optimisewait
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/AMAMazing/cline-x.git
```

2. Install dependencies:
```bash
pip install flask pywin32 pyautogui
```

3. Set up the image directory structure (required for GUI automation):
```
images/
├── approve.png
├── copy.png
├── error.png
├── instructions.png
├── likedislike.png
├── proceed.png
├── proceed2.png
├── resume.png
├── run.png
├── runcommand.png
├── save.png
├── startnewtask.png
├── typesmthn.png
└── alt1440/
    ├── claudenew.png
    ├── copy.png
    └── submit.png
```

## Configuration

1. Update the image paths in `claude.py`:
```python
set_autopath(r"path/to/your/images")
set_altpath(r"path/to/your/images/alt1440")
```

2. Adjust the `MIN_REQUEST_INTERVAL` (default: 5 seconds) if needed to match your rate limiting requirements.

## Usage

1. Start the server:
```bash
python main.py
```

2. Configure Cline to use the local API endpoint:
   - Open Cline settings in VS Code
   - Select "OpenAI Compatible" as the API provider
   - Set Base URL to: `http://localhost:3001`
   - Set API Key to any non-empty value (e.g., "any-value")
   - Set Model ID to "gpt-3.5-turbo"


The server will now:
1. Receive API requests from Cline
2. Open Claude.ai in a new browser tab
3. Input the prompt and retrieve the response
4. Return formatted response to Cline

## Technical Details

### API Endpoint

- POST `/chat/completions`: Main endpoint for chat completions
- GET `/`: Health check endpoint

### Key Components

- **Flask Server**: Handles HTTP requests and provides API endpoints
- **Browser Automation**: Uses PyAutoGUI and optimisewait for GUI interaction
- **Clipboard Management**: Handles data transfer between the server and Claude.ai
- **Response Processing**: Cleans and formats Claude's responses to match OpenAI API structure

### Rate Limiting

The server implements a simple rate limiting mechanism:
- Minimum 5-second interval between requests
- Automatic request queueing if interval not met

### Error Handling

- Comprehensive logging system
- Graceful error handling for API requests
- Unicode text handling for clipboard operations

## Limitations

- Windows-only support (due to win32clipboard)
- Requires active browser window
- Depends on GUI automation (sensitive to UI changes)
- Requires logged-in web session
- Rate-limited by design

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](LICENSE)

## Disclaimer

This project is not officially affiliated with Anthropic, OpenAI, or Cline. Use at your own discretion and in accordance with respective terms of service.
