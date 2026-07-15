# Releasing Lazyread

PyPI publication uses GitHub Actions trusted publishing, so the repository does
not store a long-lived PyPI token.

## One-time setup

1. Create a protected GitHub environment named `pypi` and require maintainer
   approval for deployment.
2. In the PyPI account's **Publishing** settings, register a pending publisher:
   project `lazyread`, owner `JayFarei`, repository `lazyread`, workflow
   `release.yml`, environment `pypi`.

The pending publisher creates the PyPI project on first use; it does not reserve
the project name before then.

## Publish a version

1. Update the matching versions in `pyproject.toml`, `src/lazyread/__init__.py`,
   and `web/package.json`, then refresh `uv.lock` and `web/package-lock.json`.
2. Merge a green pull request to `main`.
3. Create and publish a GitHub release tagged `v<version>` from that merge commit.

The release workflow rejects a mismatched tag, builds without local UV sources,
smoke-tests both the wheel and source distribution, and publishes with a
short-lived OIDC credential.
