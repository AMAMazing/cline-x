// Store active tabs
let claudeTabs = new Map();
let isProcessingRequest = false;

// Poll server for new requests
async function pollServer() {
  try {
    // Only poll if not currently processing a request
    if (!isProcessingRequest) {
      const response = await fetch('http://localhost:3000/extension-poll');
      const data = await response.json();

      if (data.requestId) {
        isProcessingRequest = true;

        try {
          // Create new tab with Claude
          const tab = await chrome.tabs.create({
            url: 'https://claude.ai/new',
            active: false
          });

          // Store tab info
          claudeTabs.set(tab.id, {
            prompt: data.prompt,
            requestId: data.requestId
          });
        } catch (error) {
          console.error('Error creating tab:', error);
          // Report error back to server
          await fetch(`http://localhost:3000/extension-error?requestId=${data.requestId}`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              error: error.message
            })
          });
          isProcessingRequest = false;
        }
      }
    }
  } catch (error) {
    console.error('Error polling server:', error);
  }

  // Poll again after delay
  setTimeout(pollServer, 1000);
}

// Start polling
pollServer();

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'claude_response') {
    const tabInfo = claudeTabs.get(sender.tab.id);
    if (tabInfo) {
      // Send response back to server
      fetch(`http://localhost:3000/extension-response?requestId=${tabInfo.requestId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          text: message.text
        })
      }).catch(error => {
        console.error('Error sending response:', error);
      }).finally(() => {
        // Clean up
        chrome.tabs.remove(sender.tab.id);
        claudeTabs.delete(sender.tab.id);
        isProcessingRequest = false;
      });
    }
  } else if (message.type === 'claude_error') {
    const tabInfo = claudeTabs.get(sender.tab.id);
    if (tabInfo) {
      // Report error back to server
      fetch(`http://localhost:3000/extension-error?requestId=${tabInfo.requestId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          error: message.error
        })
      }).catch(error => {
        console.error('Error reporting error:', error);
      }).finally(() => {
        // Clean up
        chrome.tabs.remove(sender.tab.id);
        claudeTabs.delete(sender.tab.id);
        isProcessingRequest = false;
      });
    }
  }
});

// Inject content script when Claude tab is ready
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && claudeTabs.has(tabId)) {
    const tabInfo = claudeTabs.get(tabId);
    
    // Send prompt to content script
    chrome.tabs.sendMessage(tabId, {
      type: 'process_request',
      prompt: tabInfo.prompt
    });
  }
});
