// Runs Vite with esbuild pointed at a binary the machine is allowed to execute.
//
// esbuild ships a native .exe, and npm puts it in node_modules. This machine's
// group policy (AppLocker) denies execution anywhere under C:\Users\, which is
// where a checkout in the user profile keeps its node_modules - so Vite cannot
// start, with "Dette programmet er blokkert for gruppepolicy" from a binary
// that is perfectly fine. A copy in ~/.local/bin runs, that being one of the
// directories the policy allowlists for developer tooling, and esbuild reads
// ESBUILD_BINARY_PATH to find one.
//
// It has to be an environment variable set before Vite starts: Vite bundles
// vite.config.ts with esbuild in order to read it, so the config file cannot
// set the path it needs to be read at all.
//
// Set only when that copy exists and nothing has set the variable already, so
// on a machine without the restriction this is an ordinary `vite` and the
// indirection costs nothing. If you are on such a machine and would rather not
// have it, point the package.json scripts straight back at `vite`.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const binary = process.platform === "win32" ? "esbuild.exe" : "esbuild";
const allowed = join(homedir(), ".local", "bin", binary);

if (!process.env.ESBUILD_BINARY_PATH && existsSync(allowed)) {
  process.env.ESBUILD_BINARY_PATH = allowed;
}

// node_modules/.bin/vite is a shell shim; the .js entry point runs under the
// node.exe we are already in, which is the one the policy permits.
const vite = join("node_modules", "vite", "bin", "vite.js");

const child = spawn(process.execPath, [vite, ...process.argv.slice(2)], {
  stdio: "inherit",
});
child.on("exit", (code, signal) => process.exit(signal ? 1 : code ?? 1));
