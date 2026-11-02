# Security and publication boundary

Keep actual user/research data outside this public repository. The examples are
synthetic and contain no real conversations, participants or researcher corpus.
Do not commit credentials, cookies, profiles, authentication bundles, SSH keys,
private hosts, personal account configuration, logs, original documents or databases.
Encrypted private material is also excluded from this code-only release.

The repository has a new public history; it does not import a private repository's
commit graph, deleted files, branches, tags or Git LFS objects. The publication
manifest enumerates the reviewed files. Review future diffs and staged files, not
only the current working tree. A .gitignore is not a data-loss prevention system.

`audit_publication.py` detects a small set of prohibited file types and common secret
patterns. A pass is not proof of anonymity, copyright clearance or absence of all
secrets. Human review of the actual selected files remains required. It does not
redact source material or turn a private corpus into a safe public release.

Do not disclose a vulnerability containing private information in a public issue.
Use an owner-configured private security channel when available. No contact address
or account-specific reporting endpoint is bundled in this release.
