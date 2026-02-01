#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const execPath = process.execPath;
let localStorageArgs = [];

try {
  const help = spawnSync(execPath, ["--help"], { encoding: "utf8" });
  const output = `${help.stdout ?? ""}${help.stderr ?? ""}`;
  if (output.includes("--localstorage-file")) {
    localStorageArgs = [
      "--localstorage-file=/tmp/portfolio-exporter-localstorage.json",
    ];
  }
} catch {
  // If detection fails, proceed without the flag.
}

const scriptDir = dirname(fileURLToPath(import.meta.url));
const vitestCli = resolve(scriptDir, "../node_modules/vitest/dist/cli.js");
const args = [...localStorageArgs, vitestCli, ...process.argv.slice(2)];

const result = spawnSync(execPath, args, { stdio: "inherit" });
if (result.error) {
  console.error(result.error);
  process.exit(1);
}
process.exit(result.status ?? 1);
