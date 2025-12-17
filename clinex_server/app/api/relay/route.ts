import { NextRequest, NextResponse } from 'next/server';
import { jobQueue, results, cleanup, Job, Result } from '../../lib/store';

// NOTE: In a production serverless environment (like Vercel), global variables
// are not guaranteed to persist between requests or be shared across instances.
// For a robust "Zero Dependency" solution without a database (Redis/KV),
// this memory-based approach works BEST when there is only one active server instance
// (typical for low-traffic hobby projects).
// If this fails in production, you MUST use Vercel KV or a similar store.

export async function GET(req: NextRequest) {
    cleanup();
    const { searchParams } = new URL(req.url);
    const action = searchParams.get('action');

    // 1. AGENT POLL: Agent asks "Do I have work?"
    if (action === 'poll') {
        if (jobQueue.length === 0) {
            return NextResponse.json({ pending: false }, { status: 200 });
        }
        // FIFO: Take the oldest job
        const job = jobQueue.shift();
        return NextResponse.json({ pending: true, job }, { status: 200 });
    }

    // 2. CLIENT POLL: Client asks "Is my result ready?"
    if (action === 'result') {
        const id = searchParams.get('id');
        if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 });

        if (results.has(id)) {
            const result = results.get(id)!;
            results.delete(id); // Consume result (one-time read)
            return NextResponse.json({ completed: true, result }, { status: 200 });
        }
        
        return NextResponse.json({ completed: false }, { status: 200 });
    }

    return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
}

export async function POST(req: NextRequest) {
    cleanup();
    const { searchParams } = new URL(req.url);
    const action = searchParams.get('action');

    // 3. CLIENT QUEUE: Client says "Fetch this page please"
    if (action === 'queue') {
        try {
            const body = await req.json();
            const { method, path, body: data, headers } = body;
            
            const id = Math.random().toString(36).substring(7);
            const job: Job = {
                id,
                method,
                path,
                body: data,
                headers,
                timestamp: Date.now()
            };
            
            jobQueue.push(job);
            return NextResponse.json({ success: true, id }, { status: 200 });
        } catch (e) {
            return NextResponse.json({ error: 'Invalid body' }, { status: 400 });
        }
    }

    // 4. AGENT COMPLETE: Agent says "Here is the result"
    if (action === 'complete') {
        try {
            const body = await req.json();
            const { id, status, headers, body: content, isBase64 } = body;
            
            if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 });

            const result: Result = {
                id,
                status,
                headers,
                body: content,
                timestamp: Date.now(),
                isBase64 // Capture binary flag
            };
            
            results.set(id, result);
            return NextResponse.json({ success: true }, { status: 200 });
        } catch (e) {
            return NextResponse.json({ error: 'Invalid body' }, { status: 400 });
        }
    }

    return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
}
