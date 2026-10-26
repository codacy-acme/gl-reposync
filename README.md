# gl-reposync

Adds GitLab Cloud repositories to Codacy.

- Skips **archived** GitLab repositories.
- Skips repositories **already in Codacy** (they are never modified).
- Runs as a **dry run** unless you pass `--apply`.

## Requirements

- Python 3.9+
- A GitLab personal access token with the `read_api` scope
- A Codacy [account API token](https://docs.codacy.com/codacy-api/api-tokens/#account-api-tokens)
  belonging to an **organization admin** (needed to list all repositories already in Codacy)
- The GitLab organization must already be added to Codacy

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GITLAB_TOKEN=...
export CODACY_API_TOKEN=...
```

## Usage

```bash
# 1. Preview what would be added
python gl_reposync.py --group my-group

# 2. Add the repositories
python gl_reposync.py --group my-group --apply
```

`--group` is the GitLab group (all subgroups are included) or a personal username.
Its top-level name is used as the Codacy organization, so
`gitlab.com/my-group/app` maps to `app.codacy.com/gl/my-group/app`.
You can pass a subgroup (`--group my-group/team`) to sync only that subtree.

## Behaviour

- Names are matched on the full path (`group/subgroup/project`), case-insensitively.
- A failed add is reported and the run continues; the exit code is 1 if anything failed.
- Rate limits (HTTP 429) and temporary server errors are retried automatically.
- Safe to re-run: only repositories not yet in Codacy are added.
