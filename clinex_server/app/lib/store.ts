export type Job = {
    id: string;
    method: string;
    path: string;
    body?: any;
    headers?: any;
    timestamp: number;
};

export type Result = {
    id: string;
    status: number;
    headers: any;
    body: string; // Base64 encoded or text
    timestamp: number;
    isBase64?: boolean;
};

// In-memory storage
// We use globalThis to attempt persistence across hot-reloads in dev
const globalStore = globalThis as unknown as {
    jobQueue: Job[];
    results: Map<string, Result>;
};

if (!globalStore.jobQueue) globalStore.jobQueue = [];
if (!globalStore.results) globalStore.results = new Map();

export const jobQueue = globalStore.jobQueue;
export const results = globalStore.results;

// Cleanup old data periodically (simple garbage collection)
const CLEANUP_INTERVAL = 60 * 1000;
let lastCleanup = Date.now();

export function cleanup() {
    const now = Date.now();
    if (now - lastCleanup > CLEANUP_INTERVAL) {
        // Keep jobs younger than 30s
        // Note: modifying the array in place or reassignment is tricky with exports.
        // We'll just mutate the array contents.
        const freshJobs = jobQueue.filter(j => now - j.timestamp < 30000);
        jobQueue.length = 0;
        jobQueue.push(...freshJobs);
        
        // Expire results older than 30s
        results.forEach((res, id) => {
            if (now - res.timestamp > 30000) {
                results.delete(id);
            }
        });
        
        lastCleanup = now;
    }
}
