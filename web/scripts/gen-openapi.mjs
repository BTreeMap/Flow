#!/usr/bin/env node
/**
 * gen-openapi.mjs
 *
 * 1. Runs the backend OpenAPI dump script (via uv) to produce openapi.json.
 * 2. Runs openapi-typescript to generate TypeScript types from the schema.
 *
 * Usage:  node scripts/gen-openapi.mjs
 *   or:  npm run gen
 */

import { execFileSync } from "node:child_process";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync, mkdirSync } from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const webDir = resolve(__dirname, "..");
const apiDir = resolve(webDir, "../api");
const repoRoot = resolve(webDir, "../../../../..");

const openapiJson = resolve(apiDir, "openapi.json");
const outputTs = resolve(webDir, "src/gen/openapi.ts");

// ── Step 1: Generate OpenAPI JSON from the backend ─────────────────────────
console.log("→ Dumping OpenAPI schema from backend…");
try {
  execFileSync(
    "uv",
    [
      "run",
      "--directory",
      repoRoot,
      "--locked",
      "python",
      "-m",
      "scripts.dump_openapi",
      "--out",
      openapiJson,
    ],
    {
      cwd: apiDir,
      stdio: "inherit",
      env: { ...process.env, PYTHONPATH: apiDir },
    },
  );
} catch (err) {
  console.error("✗ Failed to dump OpenAPI schema from backend.");
  process.exit(1);
}

if (!existsSync(openapiJson)) {
  console.error(`✗ Expected OpenAPI file not found: ${openapiJson}`);
  process.exit(1);
}

// ── Step 2: Generate TypeScript types ──────────────────────────────────────
console.log("→ Generating TypeScript types from OpenAPI schema…");
const outDir = dirname(outputTs);
if (!existsSync(outDir)) {
  mkdirSync(outDir, { recursive: true });
}

try {
  execFileSync(
    "npm",
    ["exec", "--no", "--", "openapi-typescript", openapiJson, "-o", outputTs],
    { cwd: webDir, stdio: "inherit" },
  );
} catch (err) {
  console.error("✗ openapi-typescript generation failed.");
  process.exit(1);
}

console.log(`✓ Generated ${outputTs}`);
