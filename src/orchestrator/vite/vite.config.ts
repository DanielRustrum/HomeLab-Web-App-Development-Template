import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

type InputMap = Record<string, string>;

/**
 * Load a precomputed entries manifest if one exists.
 */
function loadEntriesManifest(filePath: string | undefined, rootDir: string): InputMap | null {
  const resolvedPath = filePath
    ? path.resolve(filePath)
    : path.resolve(rootDir, "entries.json");
  if (!fs.existsSync(resolvedPath)) return null;
  try {
    const raw = fs.readFileSync(resolvedPath, "utf-8");
    return JSON.parse(raw) as InputMap;
  } catch {
    return null;
  }
}

/**
 * Walk the routes directory and map TSX files to Vite entry keys.
 */
function collectEntries(routesDir: string, rootDir: string): InputMap {
  const entries: InputMap = {
    "shell.html": path.resolve(rootDir, "shell.html"),
  };
  if (!fs.existsSync(routesDir)) {
    return entries;
  }

  const stack: string[] = [routesDir];
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current) continue;

    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
        continue;
      }
      if (!entry.isFile() || !entry.name.endsWith(".tsx")) {
        continue;
      }

      const rel = path.relative(routesDir, fullPath);
      const key = rel.replace(/\\/g, "/").replace(/\.tsx$/, "");
      entries[key] = fullPath;
    }
  }

  return entries;
}

export default defineConfig(() => {
  // Resolve build inputs and output directory from environment, with fallbacks.
  const rootDir = process.env.VITE_ROOT
    ? path.resolve(process.env.VITE_ROOT)
    : process.cwd();
  const manifestEntries = loadEntriesManifest(process.env.ROUTES_MANIFEST, rootDir);
  const routesDir = process.env.ROUTES_DIR
    ? path.resolve(process.env.ROUTES_DIR)
    : path.resolve(process.cwd(), "routes");
  const outDir = process.env.OUT_DIR
    ? path.resolve(process.env.OUT_DIR)
    : path.resolve(process.cwd(), "dist");

  return {
    root: rootDir,
    plugins: [react()],
    build: {
      outDir,
      emptyOutDir: true,
      manifest: true,
      assetsDir: "",
      copyPublicDir: false,
      rollupOptions: {
        input: manifestEntries ?? collectEntries(routesDir, rootDir),
      },
    },
  };
});
