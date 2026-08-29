---
name: release
description: Manage semantic versioning — bump major/minor/patch, update VERSION file, commit, tag, and push to GitHub. Use when you want to version and publish the current state of the application.
---

# Release Skill

Manage semantic versioning, git tags, and GitHub pushes for this project.

## When to Use

Invoke `/release` when you want to version and publish the current state of the application. This skill handles:
- Bumping `major`, `minor`, or `patch` version
- Updating version files (`package.json`, `pyproject.toml`, `VERSION`, etc.)
- Committing the version bump
- Creating and pushing a git tag
- Pushing the branch to GitHub

## Workflow

Follow these steps exactly when `/release` is invoked:

### 1. Parse the bump type

The user will call `/release` with one of:
- `/release major` — breaking changes (1.0.0 → 2.0.0)
- `/release minor` — new features, backwards-compatible (1.0.0 → 1.1.0)
- `/release patch` — bug fixes (1.0.0 → 1.0.1)

If no argument is given, ask the user: "What type of release? (major / minor / patch)"

### 2. Detect the current version

Check in order:
1. `package.json` → `.version` field
2. `pyproject.toml` → `[tool.poetry] version` or `[project] version`
3. `VERSION` file (plain semver string)
4. Latest git tag matching `v*.*.*`

If none found, assume `0.0.0` and inform the user.

### 3. Compute the new version

Apply semver rules:
- `major`: increment major, reset minor and patch to 0
- `minor`: increment minor, reset patch to 0
- `patch`: increment patch only

### 4. Verify git state

Run `git status` to check for uncommitted changes.
- If there are uncommitted changes, ask: "There are uncommitted changes. Commit them before releasing, or abort?"
- If user says commit, stage all changes with `git add -A` and commit with message `chore: prepare for release vX.Y.Z`
- If user says abort, stop here.

### 5. Update version files

Update whichever version file(s) were found in step 2:
- `package.json`: update the `"version"` field with `sed` or by editing directly
- `pyproject.toml`: update the `version = "..."` line under `[tool.poetry]` or `[project]`
- `VERSION`: overwrite the file with the new version string

### 6. Commit the version bump

```bash
git add <version-file(s)>
git commit -m "chore: bump version to vX.Y.Z"
```

### 7. Create an annotated git tag

```bash
git tag -a "vX.Y.Z" -m "Release vX.Y.Z"
```

### 8. Push branch and tag to GitHub

```bash
git push origin HEAD
git push origin "vX.Y.Z"
```

If `git push` fails due to no upstream set, run:
```bash
git push --set-upstream origin <current-branch>
git push origin "vX.Y.Z"
```

### 9. Confirm

Report back to the user:
- New version: `vX.Y.Z`
- Tag created: `vX.Y.Z`
- Pushed to: `origin/<branch>` and tag `vX.Y.Z`
- Link to the tag on GitHub if the remote URL is detectable

## Error handling

- If `git` is not initialized: say "This project has no git repository. Run `git init` and set a GitHub remote first."
- If no GitHub remote: say "No remote named 'origin' found. Add one with `git remote add origin <url>`."
- If push is rejected (non-fast-forward): warn the user and do NOT force-push. Ask them to pull and retry.
- If the tag already exists: say "Tag vX.Y.Z already exists. Did you mean a different bump type?"

## Example

```
/release minor
```

Output:
```
Current version: 1.3.0
New version:     1.4.0

✓ Updated VERSION
✓ Committed: chore: bump version to v1.4.0
✓ Tagged: v1.4.0
✓ Pushed branch to origin/main
✓ Pushed tag v1.4.0

Release v1.4.0 is live.
```
