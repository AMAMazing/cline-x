const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const app = express();
const port = 3000;

app.use(cors());
app.use(express.json());

// Read config file
const config = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));

// Store pending requests and active requests
const pendingRequests = new Map();
const activeRequests = new Map();

// Homepage
app.get('/', (req, res) => {
  res.send(`
    <h1>Claude API Bridge</h1>
    <p>This server bridges Cline extension to Claude web interface.</p>
    <p>Endpoint: POST /chat/completions</p>
  `);
});

// OpenAI compatible endpoint
app.post('/chat/completions', async (req, res) => {
  try {
    // Log incoming request
    console.log('Received request:', JSON.stringify(req.body, null, 2));

    // Get last message from request
    const messages = req.body.messages;
    const lastMessage = messages[messages.length - 1];
    const requestId = Date.now().toString();

    // Store request data
    pendingRequests.set(requestId, {
      res: res,
      prompt: lastMessage.content
    });

    console.log(`Request ${requestId} waiting for extension to poll`);

  } catch (error) {
    console.error('Error:', error);
    res.status(500).json({ 
      error: {
        message: error.message,
        type: 'server_error',
        param: null,
        code: null
      }
    });
  }
});

// Endpoint for extension to poll for new requests
app.get('/extension-poll', (req, res) => {
  // Find first pending request
  for (const [requestId, data] of pendingRequests) {
    // Move request from pending to active
    activeRequests.set(requestId, data);
    pendingRequests.delete(requestId);

    return res.json({
      requestId,
      prompt: data.prompt
    });
  }
  
  // No pending requests
  res.json({ requestId: null });
});

// Endpoint to receive response from extension
app.post('/extension-response', (req, res) => {
  const response = req.body;
  const requestId = req.query.requestId;
  
  // Get original request data
  const requestData = activeRequests.get(requestId);
  if (!requestData) {
    return res.status(404).json({error: 'Request not found'});
  }

  // Send response to original request
  requestData.res.json({
    id: 'chatcmpl-' + requestId,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model: 'gpt-3.5-turbo-0613',
    usage: {
      prompt_tokens: 1,
      completion_tokens: 1,
      total_tokens: 2
    },
    choices: [{
      index: 0,
      message: {
        role: 'assistant',
        content: response.text
      },
      finish_reason: 'stop'
    }],
    system_fingerprint: null
  });

  // Clean up
  activeRequests.delete(requestId);
  res.sendStatus(200);
});

// Error handling for requests that time out or fail
app.post('/extension-error', (req, res) => {
  const requestId = req.query.requestId;
  const error = req.body.error;

  const requestData = activeRequests.get(requestId);
  if (requestData) {
    requestData.res.status(500).json({
      error: {
        message: error || 'Request failed',
        type: 'extension_error',
        param: null,
        code: null
      }
    });
    activeRequests.delete(requestId);
  }

  res.sendStatus(200);
});

app.listen(port, () => {
  console.log(`API bridge running at http://localhost:3000`);
  console.log(`Using extension ID: ${config.extensionId}`);
});
