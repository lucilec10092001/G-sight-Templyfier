# Internal server deployment — Templyfier v53

Prepared for internal hosting, but not deployed or qualified on Givaudan
infrastructure. IT must validate installation, identity provider, access, load,
data handling, backup and restoration before opening the service to CMIs.

## Supported architecture

One application instance on one host, with a durable local disk. Store release
code and persistent business memory in separate directories. SQLite stores CMI
habits, personal profiles and change metadata with short atomic transactions and
a 10-second lock wait. Consumer Excel files and result values are not stored in
this database; processing uses process/session memory. This does not guarantee
instant erasure from RAM, caches, temporary files, logs or swap. IT must review
these locations and monitoring policies too.

Do not put SQLite on SMB/NFS/NAS, OneDrive or ephemeral storage, and do not use
multiple application replicas with this backend. UNC paths are rejected. Network
mounts on Linux cannot be identified reliably by the code and must be excluded
by IT. For multiple hosts, implement an IT-approved shared database adapter,
such as PostgreSQL; that adapter is not included. SQLite uses rollback journaling,
not WAL. Existing WAL databases are rejected rather than silently reconfigured.

Personal memory is isolated by verified SSO identity. Team reference is readable
by approved CMIs, but writable only by explicitly authorized referents. Personal
wave profiles remain private through the application interface. Remembered labels
can be confidential; absence of consumer scores does not make memory anonymous.

## Installation and service configuration

1. Extract into a new release folder. Preserve the separate durable data directory
   during upgrades. Back up business memory before a release change.
2. Create an isolated Python environment and install `requirements.txt` using the
   approved mirror. Direct dependencies match the tested Python 3.13 environment:
   Streamlit 1.62.0, openpyxl 3.1.5, pandas 2.3.3. The `[auth]` extra installs
   Authlib for OIDC. Real OIDC/Authlib integration was not tested locally.
   Review security advisories, transitive versions and upgrades under IT policy.
3. Create an existing durable local directory, for example `/var/lib/templyfier`
   or `D:\TemplyfierData`. Restrict OS access to the service account and approved
   administrators. Missing/relative directories, code directories and UNC paths
   are rejected. OS encryption, ACLs and backup access are IT responsibilities.
4. Set service environment variables outside source control:

   ```text
   TEMPLYFIER_MODE=server
   TEMPLYFIER_DATA_DIR=/var/lib/templyfier
   TEMPLYFIER_OIDC_ISSUER=<exact approved token iss claim>
   TEMPLYFIER_ALLOWED_USERS=<comma-separated full SHA256 identity keys>
   TEMPLYFIER_ADMINS=<authorized subset of those identity keys, or empty>
   ```

   Identity keys are `SHA256(iss + "\n" + sub)`, encoded in UTF-8 without
   truncation. Use verified claims for this application. Do not replace `sub`
   with email, `oid`, a manually entered identity or a browser HTTP header.
   The subject claim may be application-specific. Calculate the key with:

   ```python
   from templyfier.server_storage import identity_key
   print(identity_key("<exact issuer>", "<verified subject>"))
   ```

   IT maintains the explicit allowlist. There is no self-registration or automatic
   authorization by email domain. OIDC authenticates; the allowlist authorizes.
5. Register the application with the approved IdP and restrict assignment. Use
   `.streamlit/secrets.example.toml` to configure actual secrets via IT secret
   management, outside the ZIP/repository. Configure the exact HTTPS redirect URI
   ending `/oauth2callback`, a strong random cookie secret, client ID/secret and
   approved tenant metadata URL. No real credentials are supplied.
6. Use `launch_server.bat` on Windows or `sh launch_server.sh` on Linux, or an
   equivalent managed service explicitly setting server mode. **Do not expose
   `launch_templyfier.bat` or `install_and_launch.bat` as the shared service.**
7. Use internal HTTPS and a reverse proxy supporting WebSockets. Restrict the
   Streamlit port to the proxy. Keep XSRF/CORS enabled. Qualify upload size and
   session duration on real exports. No LLM/API AI or Streamlit usage telemetry
   is used; approved outbound IdP traffic is still required for SSO.

Server configuration failures do not fall back to desktop mode. Unauthenticated,
expired or unauthorized sessions cannot reach uploads or project memory. Verified
identity changes clear previous Streamlit project context. Switching memory
libraries preserves the project but asks the CMI to choose the client again.

## Memory migration and concurrent changes

Memory stores deliberately taught rules; it does not train an AI model. Compatible
source wording, type, stage and response structure control suggestions. Ambiguous
or incomplete metric recipes are left for CMI review rather than partially applied.

For desktop migration, export the relevant client's memory using the backup button,
or obtain `client_memory.json` from the existing Windows preferences location.
On the server select **My workspace**, open **Transfer existing memory**, upload
the JSON, choose the client and review the proposed import before confirmation.
Imported rules replace only the displayed matching contexts; unrelated rules and
clients are retained. Authorized referents can import into **Team reference** after
CMI review. The service account's desktop habits are never imported automatically.
Existing wave settings profiles remain portable. Legacy technical type/key values
are retained internally for compatibility; user-facing labels are English.

Concurrent edits to the same client's memory require re-reading rather than
overwriting the latest choices. Edits to different clients are combined atomically.
The audit stores UTC date, technical actor, workspace, action and revision, without
question labels or scores. It is not cryptographically tamper-proof. IT must define
retention and purge; there is no automatic audit purge in this release.

## Backup and restoration

Back up memory as business data, not just release code. The supplied script uses
SQLite's backup API, validates integrity and refuses to overwrite an existing
destination. Run with approved OS rights and protected internal backup paths:

```text
python backup_server_memory.py --database /var/lib/templyfier/templyfier.sqlite3 --output /approved-backup/templyfier-2026-09-14.sqlite3
```

Quote Windows paths. Do not blindly copy a live database without a consistent
backup protocol. To restore: stop the service, preserve the current database,
validate `PRAGMA integrity_check` on the backup, replace the stopped database under
IT control, restore ACLs, restart and verify personal and team workspaces.
Test restoration before production. Changes/loss of `iss` or `sub` can make old
personal workspaces inaccessible and require an IT migration.

## Acceptance before shared use

- Real SSO: approved CMI, denied account, referent, expiry, logout, account switch,
  revocation and actual Authlib/IdP connectivity. Local tests use simulated claims.
- Personal/team isolation, administrator permissions, concurrent edits and imports.
- Approved export samples: Monadic, Paired, multiple splits, reordered products,
  two/three/more benchmarks, missing comparisons, both layouts and gaps on/off.
- Excel recalculation and comparison of scores, bases, fills, formulas and KPI
  decisions against source files. KPI review points do not certify statistics.
- Representative concurrent-user and large-file load; memory/CPU/timeouts, proxy
  WebSockets, upload limits, retention, monitoring, OS security and outgoing traffic.
- Backup integrity, restoration, release rollback and preservation of durable data.

The application is prepared for this architecture; these production controls are
not certified by the local test suite.

## Personal draft retention and unattended cleanup

Persistent project drafts are opt-in. Set TEMPLYFIER_DRAFT_RETENTION_DAYS to an IT
approved whole number from 1 to 365 in the service environment. Unset means server
drafts are disabled; portable configuration downloads remain available. Example:

```text
TEMPLYFIER_DRAFT_RETENTION_DAYS=30
```

Expiry is assigned when a draft is saved; changing policy does not retroactively
shorten previously saved expiry dates. Maximum 20 active drafts per personal
workspace. Drafts use the existing durable SQLite database and are included in
its consistent backup. Application isolation uses the verified SSO identity,
including when Team reference is selected. Named drafts are saved explicitly,
not automatically. Source files must be re-uploaded to resume. Draft records are
configuration/labels and source fingerprints only, but can still be confidential.

Opening the draft list deletes that user's expired active records. To enforce
cleanup for absent users, IT must schedule the included maintenance command on
the host using the same server environment and protected service account:

```text
python purge_expired_drafts.py
```

The command deletes expired drafts across personal workspaces transactionally,
adds metadata-only audit entries and preserves memory, profiles and active drafts.
Malformed records roll back the transaction. Configure the required maintenance
frequency, monitoring and failure alerts under IT policy; this release does not
create an OS scheduled task. Record deletion is logical database deletion, not
forensic erasure of disk, journals, existing backups or swap. IT must independently
apply backup retention, storage encryption and disposal policy.

Acceptance must include real SSO cross-user draft isolation, exact-source resume,
CMR mismatch, expiry for absent users, concurrent draft changes, backup restore and
service-account maintenance. Local SSO workflow checks use simulated claims only.
