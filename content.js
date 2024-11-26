// Connect to background script
const port = chrome.runtime.connect({ name: 'claude-bridge' });

// Listen for messages from background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'process_request') {
    handleRequest(request.prompt).then(response => {
      if (response.error) {
        chrome.runtime.sendMessage({
          type: 'claude_error',
          error: response.error
        });
      } else {
        chrome.runtime.sendMessage({
          type: 'claude_response',
          text: response.text
        });
      }
    }).catch(error => {
      chrome.runtime.sendMessage({
        type: 'claude_error',
        error: error.message
      });
    });
    return true;
  }
});

// Handle request from background script
async function handleRequest(prompt) {
  try {
    // The textarea is visible in the screenshot with placeholder "How can Claude help you today?"
    const textarea = await waitForElement('textarea[placeholder="How can Claude help you today?"]', 30000);
    if (!textarea) {
      throw new Error('Timeout waiting for textarea');
    }
    
    // Type prompt into textarea
    textarea.value = prompt;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    
    // Click send button - in new interface it's the Enter key
    const enterEvent = new KeyboardEvent('keydown', {
      key: 'Enter',
      code: 'Enter',
      keyCode: 13,
      which: 13,
      bubbles: true
    });
    textarea.dispatchEvent(enterEvent);
    
    // Wait for response with timeout
    const success = await waitForResponse(60000);
    if (!success) {
      throw new Error('Timeout waiting for Claude response');
    }
    
    // Get last message content
    const messages = document.querySelectorAll('[data-message-author="assistant"]');
    if (messages.length === 0) {
      throw new Error('No response message found');
    }
    const lastMessage = messages[messages.length - 1];
    const responseText = lastMessage.textContent;
    
    if (!responseText || responseText.trim() === '') {
      throw new Error('Empty response from Claude');
    }
    
    return { text: responseText };
  } catch (error) {
    console.error('Error:', error);
    return { error: error.message };
  }
}

// Helper to wait for element with timeout
function waitForElement(selector, timeout = 10000) {
  return new Promise(resolve => {
    if (document.querySelector(selector)) {
      return resolve(document.querySelector(selector));
    }
    
    const startTime = Date.now();
    
    const observer = new MutationObserver(() => {
      if (document.querySelector(selector)) {
        observer.disconnect();
        resolve(document.querySelector(selector));
      } else if (Date.now() - startTime > timeout) {
        observer.disconnect();
        resolve(null);
      }
    });
    
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  });
}

// Helper to wait for response with timeout
function waitForResponse(timeout = 30000) {
  return new Promise(resolve => {
    const startTime = Date.now();
    
    const observer = new MutationObserver(() => {
      const responseElements = document.querySelectorAll('[data-message-author="assistant"]');
      if (responseElements.length > 0) {
        const lastResponse = responseElements[responseElements.length - 1];
        if (!lastResponse.querySelector('.animate-pulse')) {
          observer.disconnect();
          resolve(true);
        }
      }
      
      if (Date.now() - startTime > timeout) {
        observer.disconnect();
        resolve(false);
      }
    });
    
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  });
}
