#!/usr/bin/env node
/**
 * DinextTable core test entrypoint.
 * Usage (from this directory): node run.mjs
 * Or: npm run test:dinext-table --prefix frappe-bench/apps/dinext_common
 */
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const testFiles = readdirSync(__dirname)
    .filter((name) => name.endsWith(".test.mjs"))
    .map((name) => join(__dirname, name));

const result = spawnSync(
    process.execPath,
    ["--test", ...testFiles],
    { stdio: "inherit", cwd: __dirname }
);

process.exit(result.status ?? 1);
