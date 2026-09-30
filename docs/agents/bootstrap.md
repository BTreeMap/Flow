# Repository bootstrap

## Submodule setup (`.github/skills`)
Shared agent skills are vendored via a git submodule.

- Fresh clone: `git clone --recurse-submodules <repo>`.
- Existing checkout: `git submodule update --init --recursive` before relying on any
  repo-local skill.
- If the mapping is missing/broken, register it via git (don't hand-edit `.gitmodules`):

```bash
git submodule add https://github.com/BTreeMap/SKILLs.git .github/skills
git submodule sync -- .github/skills
git submodule update --init --recursive .github/skills
```

- Verify: confirm `.gitmodules` has the `.github/skills` path/URL, then
  `git submodule status --recursive`.

## Required skill loading
- Before creating/reviewing/rewriting a commit message, load and follow
  `.github/skills/git-commits/SKILL.md`. Do not improvise a different commit standard.
- Before creating/editing a reusable skill under `.github/skills`, load and follow
  `.github/skills/authoring-skills/SKILL.md`.
- Treat repo-local skills as the authoritative workflow helpers when they apply.
