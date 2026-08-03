// CRA auto-picks up src/setupTests.js for every Jest run.
// Phase 23 Session 5 — react-router v7 requires Web Streams + Encoder
// polyfills under jsdom (which doesn't ship them).
import { TextEncoder, TextDecoder } from "util";
if (typeof global.TextEncoder === "undefined") global.TextEncoder = TextEncoder;
if (typeof global.TextDecoder === "undefined") global.TextDecoder = TextDecoder;
