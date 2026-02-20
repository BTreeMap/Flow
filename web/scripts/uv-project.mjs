import { dirname, resolve } from "node:path";
import { existsSync } from "node:fs";

function findMonorepoRoot(startDir) {
  let dir = startDir;
  while (true) {
    const parent = dirname(dir);
    const isRoot = parent === dir;

    const hasPyproject = existsSync(resolve(dir, "pyproject.toml"));
    const hasUvLock = existsSync(resolve(dir, "uv.lock"));
    const hasLib = existsSync(resolve(dir, "src/h4ckath0n/__init__.py"));
    const hasScaffolder = existsSync(
      resolve(dir, "packages/create-h4ckath0n/package.json"),
    );

    if (hasPyproject && hasUvLock && hasLib && hasScaffolder) return dir;
    if (isRoot) return null;
    dir = parent;
  }
}

/**
 * Determine which uv project should be used when running backend commands from the web template.
 *
 * Priority:
 * 1) H4CKATH0N_UV_PROJECT or UV_PROJECT explicit override (power users / CI)
 * 2) Monorepo root (dev inside this repo)
 * 3) The sibling API project (generated app layout: web/ next to api/)
 */
export function resolveUvProject(webDir, apiDir) {
  const override =
    process.env.H4CKATH0N_UV_PROJECT || process.env.UV_PROJECT || "";
  if (override.trim()) return override;
  const monorepoRoot = findMonorepoRoot(webDir);
  return monorepoRoot || apiDir;
}
