# Projects Mount Point

This directory is intentionally empty in the logic repo.

Do not commit personal project metadata or project entry points here.

Expected usage:

- mount or symlink your own data repo separately
- expose project state from the data layer
- keep the logic repo portable across different users and machines

Examples of data-layer content that should not live here by default:

- `projects/*/STATUS.md`
- `projects/*/memory/`
- personal symlinks to local code repositories
