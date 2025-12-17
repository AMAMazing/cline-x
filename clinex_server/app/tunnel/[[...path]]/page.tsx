"use client";

import React, { useState, useEffect, useRef } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';

// Helper to wait
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

export default function TunnelPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  // path is an array like ['dashboard'] or ['images', 'logo.png']
  // If undefined, it's the root /tunnel
  const pathArray = params?.path as string[] || [];
  const currentPath = '/' + pathArray.join('/');

  // Reconstruct query string
  const queryString = searchParams.toString();
  const fullPath = currentPath + (queryString ? `?${queryString}` : '');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const processingRef = useRef(false);

  const addLog = (msg: string) => {
    setLogs(prev => [...prev, `${new Date().toLocaleTimeString()} - ${msg}`]);
  };

  useEffect(() => {
    // If we just navigated here, reset the takeover flag if we were using one? 
    // Actually, since we nuke the DOM, this component unmounts essentially. 
    // But React might keep it if we use Next.js navigation. 
    // For safety, we allow re-running if fullPath changes.
    if (processingRef.current && document.getElementById('clinex-takeover-marker')) return;
    processingRef.current = true;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setLogs([]);
      addLog(`Starting tunnel sequence for: ${fullPath}`);
      
      try {
        // 1. Queue the job
        addLog("Step 1: Queueing job at /api/relay...");
        const queueRes = await fetch('/api/relay?action=queue', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            method: 'GET',
            path: fullPath,
            headers: {} 
          })
        });
        
        if (!queueRes.ok) throw new Error(`Queue failed: ${queueRes.status}`);
        
        const queueData = await queueRes.json();
        if (!queueData.success) throw new Error(queueData.error || 'Failed to queue job');
        
        const requestId = queueData.id;
        addLog(`Step 1 Success. Job ID: ${requestId}`);
        
        // 2. Poll for result (Max 60s)
        addLog("Step 2: Waiting for Local Agent to pick up job...");
        let attempts = 0;
        let result = null;
        const MAX_ATTEMPTS = 120; // 60s
        
        while (attempts < MAX_ATTEMPTS) {
          await sleep(500);
          const pollRes = await fetch(`/api/relay?action=result&id=${requestId}`);
          const pollData = await pollRes.json();
          
          if (pollData.completed) {
            result = pollData.result;
            addLog("Step 2 Success: Result received from Agent!");
            break;
          }
          
          attempts++;
          if (attempts % 10 === 0) addLog(`Still waiting... (${attempts}/${MAX_ATTEMPTS})`);
        }
        
        if (!result) {
            addLog("Error: Timed out waiting for Agent.");
            throw new Error('Request timed out. Is your Python Agent running and connected to THIS server?');
        }
        
        // 3. Process Content (DOM Takeover)
        addLog("Step 3: Performing Full Page Takeover...");
        
        let processedBody = result.body;
        
        // --- LINK REWRITING STRATEGY ---
        // NAVIGATION -> /tunnel (Browser URL updates, React renders Page)
        // ASSETS/DATA -> /api/proxy (Browser fetches raw data)

        // 1. CSS Links (<link href="...">) -> Proxy
        // Must come before generic href replacement
        processedBody = processedBody.replace(/<link([^>]+)href=["']\/([^"']+)["']([^>]*)>/g, '<link$1href="/api/proxy?path=/$2"$3>');

        // 2. Scripts/Images/Forms (<script src="...">, <img src="...">, <form action="...">) -> Proxy
        // We want these to fetch data, not hit the tunnel page logic
        processedBody = processedBody.replace(/(src|action)=["']\/([^"']+)["']/g, '$1="/api/proxy?path=/$2"');
        
        // 3. CSS url() -> Proxy
        processedBody = processedBody.replace(/url\((["']?)\/([^"')]+)(["']?)\)/g, 'url($1/api/proxy?path=/$2$3)');

        // 4. Anchor Tags (<a href="...">) -> Tunnel
        // These are actual navigation events
        processedBody = processedBody.replace(/<a([^>]+)href=["']\/([^"']+)["']([^>]*)>/g, '<a$1href="/tunnel/$2"$3>');

        // 5. Javascript Window Location -> Tunnel
        processedBody = processedBody.replace(/window\.location(\.href)?\s*=\s*["']\/([^"']*)["']/g, 'window.location$1="/tunnel/$2"');
        
        // 6. Inject Tunnel Patch Script
        const patchScript = `
          <script>
            (function() {
              console.log("[ClineX] Tunnel Active - Patching Network for Proxy");
              
              // Mark DOM as taken over
              const marker = document.createElement('div');
              marker.id = 'clinex-takeover-marker';
              marker.style.display = 'none';
              document.body.appendChild(marker);

              // 1. Patch Fetch -> Proxy
              const originalFetch = window.fetch;
              window.fetch = function(input, init) {
                if (typeof input === 'string' && input.startsWith('/')) {
                  if (!input.startsWith('/tunnel') && !input.startsWith('/api')) {
                     console.log("[ClineX] Proxying fetch: " + input);
                     // Encode the path to ensure query params in the target url don't break the proxy url
                     input = '/api/proxy?path=' + encodeURIComponent(input);
                  }
                }
                return originalFetch(input, init);
              };
              
              // 2. Patch XHR -> Proxy
              const originalOpen = XMLHttpRequest.prototype.open;
              XMLHttpRequest.prototype.open = function(method, url) {
                if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/tunnel') && !url.startsWith('/api')) {
                   console.log("[ClineX] Proxying XHR: " + url);
                   url = '/api/proxy?path=' + encodeURIComponent(url);
                }
                return originalOpen.apply(this, arguments);
              };
              
              // 3. Patch History -> Tunnel
              // When the app says "Change URL to /dashboard", we want it to say "/tunnel/dashboard"
              const originalPushState = history.pushState;
              history.pushState = function(state, title, url) {
                 if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/tunnel') && !url.startsWith('/api')) {
                    url = '/tunnel' + url;
                 }
                 return originalPushState.apply(this, arguments);
              };
              
              const originalReplaceState = history.replaceState;
              history.replaceState = function(state, title, url) {
                 if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/tunnel') && !url.startsWith('/api')) {
                    url = '/tunnel' + url;
                 }
                 return originalReplaceState.apply(this, arguments);
              };

            })();
          </script>
        `;
        
        if (processedBody.includes('<head>')) {
            processedBody = processedBody.replace('<head>', '<head>' + patchScript);
        } else {
            processedBody = patchScript + processedBody;
        }
        
        // --- EXECUTE TAKEOVER ---
        // This wipes the current document (Next.js app) and replaces it with the new content
        // This is the only way to guarantee 100% style isolation and correctness
        document.open();
        document.write(processedBody);
        document.close();
        
      } catch (err: any) {
        console.error(err);
        setError(err.message);
        addLog(`Critical Error: ${err.message}`);
        setLoading(false);
      }
    };

    fetchData();
  }, [fullPath]);

  // If we successfully takeover, this UI will vanish instantly.
  // If loading or error, this remains.

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] text-white flex flex-col items-center justify-center p-6">
        <div className="w-16 h-16 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mb-6"></div>
        <h2 className="text-xl font-bold text-blue-400 mb-2">Establishing Tunnel</h2>
        <p className="text-gray-400 mb-8 animate-pulse">Routing request to local machine...</p>
        
        <div className="w-full max-w-lg bg-[#111] border border-gray-800 rounded-xl p-4 font-mono text-xs text-gray-500 h-64 overflow-y-auto shadow-inner">
            {logs.map((log, i) => (
                <div key={i} className="mb-1 border-b border-gray-800/50 pb-1 last:border-0">{log}</div>
            ))}
            <div className="animate-pulse">_</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0A0A0A] text-white flex flex-col items-center justify-center p-4">
        <div className="bg-red-900/20 border border-red-500/50 rounded-xl p-8 max-w-xl w-full shadow-2xl">
          <h2 className="text-2xl font-bold text-red-400 mb-4 flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
            Connection Failed
          </h2>
          <p className="text-white text-lg mb-6">{error}</p>
          
          <div className="bg-black/50 rounded-lg p-4 mb-6 text-sm font-mono text-gray-400 overflow-y-auto max-h-40 border border-gray-700">
             {logs.map((log, i) => (
                <div key={i}>{log}</div>
            ))}
          </div>

          <div className="flex gap-4">
            <button 
                onClick={() => window.location.reload()}
                className="flex-1 bg-red-600 hover:bg-red-500 text-white px-6 py-3 rounded-lg transition-colors font-semibold"
            >
                Retry Connection
            </button>
            <button 
                onClick={() => router.push('/')}
                className="px-6 py-3 rounded-lg border border-gray-700 hover:bg-gray-800 text-gray-300 transition-colors"
            >
                Back to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null; // Should be overwritten
}
