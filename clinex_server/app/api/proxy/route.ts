import { NextRequest, NextResponse } from 'next/server';
import { jobQueue, results, cleanup, Job, Result } from '../../lib/store';

// Helper to wait
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

async function handleRequest(req: NextRequest) {
    cleanup();
    const { searchParams } = new URL(req.url);
    const path = searchParams.get('path');

    if (!path) return new NextResponse('Missing path', { status: 400 });

    // 1. Extract Body (if any)
    let body = undefined;
    const contentType = req.headers.get('content-type');
    
    if (req.method !== 'GET' && req.method !== 'HEAD') {
        try {
            if (contentType && contentType.includes('application/json')) {
                body = await req.json();
            } else {
                const text = await req.text();
                if (text) body = text;
            }
        } catch (e) {
            // Body parsing failed or empty, ignore
        }
    }

    // 2. Extract Headers to Forward
    const forwardHeaders: any = {};
    
    // Forward Content-Type so Flask knows how to parse body
    if (contentType) forwardHeaders['Content-Type'] = contentType;
    
    // Forward Auth/Session cookies (Critical for CSRF and Sessions)
    const cookie = req.headers.get('cookie');
    if (cookie) forwardHeaders['Cookie'] = cookie;
    
    // Forward CSRF Token if present
    const csrfToken = req.headers.get('x-csrftoken') || req.headers.get('x-csrf-token');
    if (csrfToken) forwardHeaders['X-CSRFToken'] = csrfToken;

    // 3. Queue the job
    const id = Math.random().toString(36).substring(7);
    const job: Job = {
        id,
        method: req.method,
        path, 
        headers: forwardHeaders,
        body, 
        timestamp: Date.now()
    };
    
    jobQueue.push(job);

    // 4. Wait for result (Sync-ish Proxy)
    let attempts = 0;
    const MAX_ATTEMPTS = 150; // 15s timeout
    
    while (attempts < MAX_ATTEMPTS) {
        await sleep(100); 
        
        if (results.has(id)) {
            const result = results.get(id)!;
            results.delete(id); // Consume

            // 5. Construct Response
            let responseBody: any = result.body;
            
            if (result.isBase64 && typeof result.body === 'string') {
                responseBody = Buffer.from(result.body, 'base64');
            }

            // Forward relevant headers from Agent -> Client
            const responseHeaders = new Headers();
            if (result.headers) {
                Object.entries(result.headers).forEach(([k, v]) => {
                    if (typeof v === 'string') {
                        // Skip content-encoding/length as Next.js handles compression
                        if (!['content-length', 'content-encoding', 'transfer-encoding'].includes(k.toLowerCase())) {
                            responseHeaders.set(k, v);
                        }
                    }
                });
            }

            return new NextResponse(responseBody, {
                status: result.status,
                headers: responseHeaders
            });
        }
        
        attempts++;
    }

    return new NextResponse('Proxy Timeout - Agent did not respond', { status: 504 });
}

export { handleRequest as GET, handleRequest as POST, handleRequest as PUT, handleRequest as DELETE, handleRequest as PATCH };
