# PostgreSQL database and schema manager

[Documentation](README.md) · [Project overview](../README.md)

From a project's directory:

```sh
db                              # Read .env in the current directory
db .env.local                   # Read a different file
db -f ./config/development.env
db --var DATABASE_URL           # Only use this variable
db --var DB_URL --var TEST_DB_URL
db --connections                # Show redacted targets without connecting
db --maintenance-db app_admin   # If the role cannot connect to postgres
```

The installer supplies `psql`; this does **not** install or start a PostgreSQL
server. It uses the database role and permissions in the selected connection.
The server's `postgres` database is used for database-level operations by default.
Your role needs CONNECT there and the appropriate CREATE/ownership privileges.

Recognized variables include `DB_URL`, `DATABASE_URL`, `TEST_DB_URL`,
`TEST_DATABASE_URL`, `DB_URLS`, and `DATABASE_URLS`. Use `--var NAME` for any other
name. Multiple connections can be a JSON array or a named JSON object on a single line:

```dotenv
DATABASE_URL=postgresql://app:password@localhost:5432/my_project
DB_URLS='{"local":"postgresql://localhost/my_project","test":"postgresql://localhost/my_project_test"}'
# Or: DB_URLS='["postgresql://localhost/my_project","postgresql://localhost/my_project_test"]'
```

An example lives in [`examples/postgres.env.example`](../examples/postgres.env.example). URL-encode special characters
in passwords. The parser supports `export`, quotes, inline comments, and `${VAR}`
references in double-quoted/unquoted values. It does not execute shell code.
Single quotes keep values literal. Credentials stay outside this repository;
passwords are supplied through a temporary mode-0600 password file and removed
after each `psql` call. Connection menus show names and endpoints without passwords.
Existing `.pgpass` authentication works when the URL contains no password.

Menus:

1. Select a connection, then **Databases** or **Schemas**.
2. For schemas, select the database to manage.
3. Choose **List**, **Create**, **Remove**, or **Reset**.
4. Use arrows to move, Space to select multiple targets, and Enter to accept.
   Escape returns to the previous menu. Ctrl-A selects all and Ctrl-D clears a
   batch selection. Single-choice menus accept Space or Enter.

Remove/reset shows the target server and object names and requires an exact typed
phrase such as `RESET app_test`. There are no table-management actions. Removing
or resetting a database/schema deletes its contained objects and data; schema
CASCADE can also remove dependent objects in other schemas.

- Database reset drops and recreates it from `template0`, preserving its owner,
  encoding/locale, tablespace, connection limit, access grants, and comment. Its
  custom schemas, data, installed extensions, and per-database settings are not
  restored. Active connections are **not** forcibly terminated.
- Schema reset drops and recreates the schema in one transaction, preserving its
  owner, access grants, and comment. A failed schema reset rolls back.
- Database reset cannot be atomic. If recreation fails after a successful drop,
  a private recreation script is kept under
  `~/.local/state/linux-setup/db-recovery/`; inspect the server and script before
  recovering. Other successful targets in a batch are not rolled back.
- `postgres`, template databases, the selected maintenance database, and system
  schemas are excluded from destructive selection. `public` is a user schema and
  can be explicitly reset or removed after confirmation.

SSL options such as `sslmode=require` are respected. Common ORM-only fields
(`schema`, `connection_limit`, `pool_timeout`, `pgbouncer`, `socket_timeout`, and
`statement_cache_size`) are ignored. Other unsupported URL options produce an
error rather than being silently discarded. Use a direct database endpoint when
a transaction-pooling proxy disallows database-level DDL.

Tests never read your project `.env` or connect to its databases. To additionally
run the integration tests, point this command at installed PostgreSQL **server**
binaries; the test creates, starts, and removes its own private cluster:

```sh
LINUX_SETUP_TEST_POSTGRES_BIN=/path/to/postgresql/bin \
  python3 -m unittest discover -s tests -v
```
