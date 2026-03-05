# Contributing to Momentum MGM

## Branch Strategy

We use **feature branches** off `main`. Every meaningful unit of work gets its own branch.

```
main
├── feat/project-scaffolding
├── feat/core-engine
├── feat/api-layer
├── feat/frontend-ui
├── fix/issue-short-description
└── docs/update-architecture
```

### Branch Naming

| Prefix | Use case |
|---|---|
| `feat/` | New feature or capability |
| `fix/` | Bug fix |
| `refactor/` | Code restructure (no behavior change) |
| `docs/` | Documentation only |
| `test/` | Tests only |
| `chore/` | Tooling, deps, config |

### Workflow

```bash
# 1. Always branch from main
git checkout main && git pull
git checkout -b feat/your-feature-name

# 2. Commit often, with clear messages (see below)
git add <specific files>
git commit -m "feat: short description of what and why"

# 3. Push and open PR against main
git push -u origin feat/your-feature-name
gh pr create --title "feat: ..." --body "..."

# 4. Merge via PR (squash or merge commit depending on complexity)
```

---

## Commit Message Convention

We follow **Conventional Commits**:

```
<type>(<scope>): <short description>

[optional body — what & why, not how]

[optional footer — breaking changes, issue refs]
```

**Types:** `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`

**Examples:**
```
feat(api): add /momentum endpoint returning score breakdown
fix(auth): handle expired token edge case in middleware
docs(architecture): add sequence diagram for data flow
chore(deps): update to React 19
```

---

## Pull Request Checklist

Before merging:
- [ ] Code runs locally without errors
- [ ] Relevant tests pass (or new tests added)
- [ ] `docs/bugs.md` updated if a bug was found/fixed
- [ ] `CHANGELOG.md` updated with the change
- [ ] PR description explains *why*, not just *what*

---

## Code Style

*To be defined once stack is confirmed.*

---

*Last updated: 2026-03-05*
