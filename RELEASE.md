# Releasing SoundStage

How a version of SoundStage gets to PyPI and onto a GitHub release page, what is set up for it
and why, and what to do when a step fails. The website is not part of a release: it deploys on
its own from `main` (see [The website](#the-website)).

## What a release is

| Where | What | How |
|---|---|---|
| [PyPI `soundstage`](https://pypi.org/project/soundstage/) | sdist and wheel of the package `soundstage` (engine, CLI, Blender side); no examples, samples or tests | `.github/workflows/publish.yaml`, started by pushing a tag `v<version>` |
| [GitHub releases](https://github.com/Agents-Robots/soundstage/releases) | a page per tag with release notes | by hand with `gh release create` |

## Who may do what

- **Publishing is irreversible.** PyPI never accepts the same version number twice, not even
  after the files are deleted. A tag `v*` is pushed only on the maintainer's go-ahead; coding
  agents never push one on their own.
- **The maintainer approves every upload.** The PyPI job runs in the GitHub environment `pypi`,
  which requires the approval of `chgloor`. Only the maintainer approves, in their own browser;
  an agent never approves a deployment, even with access to the maintainer's login. This keeps a
  person between a pushed tag and an upload that cannot be undone.

## One-time setup (done)

Kept here so that it can be checked or rebuilt.

- **PyPI**: the project `soundstage` belongs to the maintainer's PyPI account. Its trusted
  publisher is GitHub, repository `Agents-Robots/soundstage`, workflow `publish.yaml`,
  environment *(Any)*. Trusted Publishing means PyPI accepts uploads from that workflow through a
  short-lived OIDC token; no API token is stored anywhere.
- **GitHub environment `pypi`** (Settings → Environments):
  - required reviewer `chgloor` (self-review allowed, since the maintainer pushes the tags too);
  - deployment branches and tags: only tags matching `v*`.
- **Ruleset on `main`** (id 26218617): blocks deleting `main` and force-pushing to it, with no
  bypass. Tags are not covered by it.
- **Release README**: PyPI shows `README.md` without the repository around it, so
  `tools/pypi_readme.py` rewrites its relative links and pictures to GitHub URLs at the released
  tag before the build. The README in the repository stays as it is.

## Making a release

1. Make sure `main` is green: `.venv/bin/ruff check .` and `.venv/bin/pytest` locally, and the
   `tests` workflow on the last commit.
2. Bump `version` in `pyproject.toml` (the only place the version is written). Commit
   (`Version X.Y.Z: <what is new>`) and push to `main`.
3. Optional dry run of what PyPI will show:

   ```bash
   python3 tools/pypi_readme.py --ref vX.Y.Z --out tmp/README.pypi.md   # the README as PyPI shows it
   python3 -m venv tmp/rel && tmp/rel/bin/pip install build twine
   tmp/rel/bin/python -m build --outdir tmp/dist && tmp/rel/bin/python -m twine check --strict tmp/dist/*
   ```

4. Tag the bump commit and push the tag (after the go-ahead, see above):

   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```

5. The `publish` workflow runs:
   - **build**: refuses a tag that does not match `version` in `pyproject.toml`, rewrites the
     README (`tools/pypi_readme.py --ref <tag>`), builds sdist and wheel, runs
     `twine check --strict`, keeps `dist/` as a workflow artifact;
   - **pypi**: waits for approval. The maintainer opens the run under Actions →
     *Review deployments* → `pypi` → *Approve and deploy*. The job then uploads `dist/` with
     `pypa/gh-action-pypi-publish` (with attestations).
6. Write the GitHub release page for the tag:

   ```bash
   gh release create vX.Y.Z -R Agents-Robots/soundstage --title "SoundStage X.Y.Z" --notes-file notes.md
   ```

   Release notes: one bullet per user-visible change, in plain technical language; links into
   the docs point at the tag (`https://github.com/Agents-Robots/soundstage/blob/vX.Y.Z/...`), not
   at `main`; end with `Install: pip install soundstage==X.Y.Z`. Known limitations get their own
   line. The pages of v0.1.0 and v0.1.1 are examples.
7. Check the result in a fresh venv:

   ```bash
   python3 -m venv tmp/check && tmp/check/bin/pip install soundstage==X.Y.Z
   tmp/check/bin/soundstage --help && tmp/check/bin/soundstage blender-path
   ```

   Right after the upload, pip may not find the new version for a minute or two (PyPI's index
   is cached); retry.

## When something goes wrong

- **Tag and version do not match**: the build job fails and nothing is uploaded. Delete the
  tag (`git push origin :refs/tags/vX.Y.Z && git tag -d vX.Y.Z`), fix `pyproject.toml`, tag again.
- **Build or `twine check` fails**: same as above; nothing reached PyPI, so the version number is
  still free.
- **Approval rejected or never given**: nothing is uploaded. A pending deployment expires after
  30 days. Re-run the workflow from the Actions page to ask again.
- **A broken version reached PyPI**: it cannot be replaced. Yank it on PyPI (Manage project → Releases →
  Options → Yank, with a reason), which keeps pinned installs working but hides it from `pip install
  soundstage`, then release a fixed version with the next number. Note the yank on its GitHub
  release page.
- **The pypi job fails on the trusted publisher** (`invalid-publisher` or similar): the
  repository, workflow file name or environment no longer match what PyPI expects. Renaming
  `publish.yaml`, the repository or the organisation needs the same change on PyPI first.

## The website

[agents-robots.github.io/soundstage](https://agents-robots.github.io/soundstage/) is built from
`site/` by `.github/workflows/pages.yml` on every push to `main` that touches `site/**` (or by
hand: `gh workflow run pages.yml -R Agents-Robots/soundstage --ref main`). It is not tied to a
version; its install line says `pip install soundstage` without a number, so it needs no change
for a release.

If the deploy job fails with *No artifacts named "github-pages"* right after a successful upload,
GitHub had not registered the artifact yet. *Re-run failed jobs* does not help (it then finds two
artifacts of that name); start a fresh run with the command above.
