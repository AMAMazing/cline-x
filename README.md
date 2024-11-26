# Claude API Bridge

Bridge between VSCode Cline extension and Claude web interface to reduce API costs.

## How It Works

1. Cline sends request to local server
2. Server injects script into page
3. Script communicates with Chrome extension
4. Extension automates Claude web interface
5. Response flows back through the chain

## Setup

1. **Install Chrome Extension:**
   - Open Chrome and go to `chrome://extensions/`
   - Enable "Developer mode" in top right
   - Click "Load unpacked" and select this folder
   - Copy your extension ID (shown under the extension name)
   - Paste your extension ID in `config.json`

2. **Setup Local Server:**
   ```bash
   # Install dependencies
   npm install
   
   # Start server
   npm start
   ```
   Server will run at http://localhost:3000

3. **Configure Cline in VSCode:**
   - Open VSCode settings (Ctrl+,)
   - Search for "Cline"
   - Set these settings:
   ```json
   {
     "cline.openaiApiBase": "http://localhost:3000",
     "cline.openaiApiKey": "any-value",
     "cline.provider": "openai"
   }
   ```

## Components

1. **Server (server.js)**
   - Provides OpenAI-compatible API endpoint
   - Injects communication script into page
   - Handles response routing

2. **Extension**
   - **background.js**: Manages tab creation/cleanup
   - **content.js**: Automates Claude interface
   - **manifest.json**: Extension configuration

3. **Communication Flow**
   ```
   Cline -> Server -> Page Script -> Extension -> Claude -> Extension -> Server -> Cline
   ```

## Requirements

- Node.js installed
- Chrome browser
- Logged into Claude at https://claude.ai
- VSCode with Cline extension

## Troubleshooting

1. Ensure you're logged into Claude
2. Check extension ID in config.json matches
3. Verify server is running
4. Check Chrome DevTools console for errors
5. Ensure all components are properly connected:
   - Server running at http://localhost:3000
   - Extension loaded and enabled
   - Cline settings configured correctly

## Limitations

- Requires keeping Claude web logged in
- May be slower than direct API
- Could break if Claude web interface changes
