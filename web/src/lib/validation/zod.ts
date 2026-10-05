import { z } from "zod";

// Zod 4 probes `new Function("")` on first schema use; the production CSP has
// no 'unsafe-eval', so the probe would log a violation on every load.
// Import `z` from here, never from "zod" (and never "zod/compile").
z.config({ jitless: true });

export { z };
