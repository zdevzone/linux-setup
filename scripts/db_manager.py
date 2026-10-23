"""Keyboard-driven PostgreSQL database/schema management through psql."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import parse_qsl, quote, unquote, urlsplit


class DBError(RuntimeError):
    pass


def visible(value):
    return "".join(c if c.isprintable() else f"\\x{ord(c):02x}" for c in str(value))


def read_dotenv(path):
    """Parse data, never source shell code or execute command substitutions."""
    raw = {}
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)", line)
        if not match:
            raise DBError(f"Invalid dotenv assignment at line {number}")
        key, text = match.groups()
        expand = True
        if text.startswith(("'", '"')):
            delimiter, end, escaped = text[0], None, False
            for index, char in enumerate(text[1:], 1):
                if char == delimiter and not escaped:
                    end = index
                    break
                escaped = char == "\\" and not escaped
            if end is None or (text[end + 1:].strip() and not text[end + 1:].lstrip().startswith("#")):
                raise DBError(f"Invalid quoted value for {key} at line {number}")
            value = text[1:end]
            expand = delimiter == '"'
            if expand:
                replacements = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                value = re.sub(r'\\([nrt"\\])', lambda m: replacements[m[1]], value)
            else:
                value = value.replace("\\'", "'")
        else:
            value = re.sub(r"\s+#.*$", "", text).strip()
        raw[key] = (value, expand)

    def resolve(key, chain=()):
        if key in chain:
            raise DBError(f"Cyclic dotenv reference involving {key}")
        if key not in raw:
            if key in os.environ:
                return os.environ[key]
            raise DBError(f"Undefined dotenv reference: {key}")
        value, expand = raw[key]
        if not expand:
            return value
        return re.sub(r"\$\{([A-Za-z_][A-Za-z_0-9]*)\}", lambda m: resolve(m[1], (*chain, key)), value)

    # Resolve URL variables lazily: unrelated application settings are untouched.
    return raw, resolve


@dataclass(repr=False)
class Connection:
    name: str
    params: dict
    password: str = ""
    original: str = ""

    @property
    def database(self):
        return self.params.get("PGDATABASE", "postgres")

    @property
    def label(self):
        host = self.params.get("PGHOST", "local socket")
        port = self.params.get("PGPORT", "5432")
        user = self.params.get("PGUSER", "default user")
        return visible(f"{self.name}  {user}@{host}:{port}/{self.database}")

    def redact(self, text):
        text = text.replace(self.original, "[connection URL]") if self.original else text
        for password in [self.password, self.params.get("PGSSLPASSWORD", "")]:
            if not password:
                continue
            for secret in sorted({password, quote(password, safe="")}, key=len, reverse=True):
                text = text.replace(secret, "[redacted]")
        return visible(text)


QUERY_ENV = {
    "host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT", "user": "PGUSER",
    "dbname": "PGDATABASE", "sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY", "sslpassword": "PGSSLPASSWORD",
    "sslcrl": "PGSSLCRL", "sslcrldir": "PGSSLCRLDIR", "options": "PGOPTIONS",
    "connect_timeout": "PGCONNECT_TIMEOUT", "target_session_attrs": "PGTARGETSESSIONATTRS",
    "application_name": "PGAPPNAME", "channel_binding": "PGCHANNELBINDING",
}


def parse_connection(name, url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("postgres", "postgresql") or parsed.fragment:
            raise ValueError("Use a postgres:// or postgresql:// URL")
        params = {"PGDATABASE": unquote(parsed.path[1:]) or "postgres"}
        if parsed.hostname:
            if "," in parsed.hostname:
                raise ValueError("Use a single-host PostgreSQL connection URL")
            params["PGHOST"] = unquote(parsed.hostname)
        if parsed.port:
            params["PGPORT"] = str(parsed.port)
        if parsed.username is not None:
            params["PGUSER"] = unquote(parsed.username)
        password = unquote(parsed.password or "")
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            if key == "password":
                password = value
            elif key in QUERY_ENV:
                params[QUERY_ENV[key]] = value
            elif key not in {"schema", "connection_limit", "pool_timeout", "pgbouncer", "socket_timeout", "statement_cache_size"}:
                raise DBError(f"Unsupported URL option {visible(key)} in {visible(name)}; use libpq connection options such as sslmode")
        if any("\0" in value or "\n" in value or "\r" in value for value in [*params.values(), password]):
            raise ValueError("Connection fields cannot contain NULs or line breaks")
        return Connection(name, params, password, url)
    except ValueError:
        raise DBError(f"Invalid PostgreSQL URL in {name}; use a single-host postgres:// or postgresql:// URL") from None


def load_connections(path, variables=None):
    raw, resolve = read_dotenv(path)
    keys = variables or [key for key in raw if re.search(r"(?:DB|DATABASE).*URL", key, re.I)]
    connections = []
    for key in keys:
        if key not in raw:
            raise DBError(f"Variable {key} is not defined in {path}")
        value = resolve(key).strip()
        if not value:
            continue
        if value.startswith(("[", "{")):
            try:
                items = json.loads(value)
            except json.JSONDecodeError:
                raise DBError(f"{key} must contain valid JSON") from None
            if isinstance(items, list):
                items = {str(index + 1): item for index, item in enumerate(items)}
            if not isinstance(items, dict) or not all(isinstance(url, str) for url in items.values()):
                raise DBError(f"{key} must contain a JSON array of URLs or an object of named URLs")
            connections += [parse_connection(f"{key}.{label}", url) for label, url in items.items()]
        else:
            urls = re.split(r"\s+|,(?=postgres(?:ql)?://)", value)
            connections += [parse_connection(key if len(urls) == 1 else f"{key}.{i + 1}", url) for i, url in enumerate(urls)]
    if not connections:
        raise DBError("No PostgreSQL URLs found. Set DB_URL, DATABASE_URL, TEST_DB_URL, TEST_DATABASE_URL, DB_URLS, or use --var NAME")
    return connections


def identifier(name):
    if not name or len(name.encode()) > 63 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise DBError("Names must contain 1–63 UTF-8 bytes and no control characters")
    return '"' + name.replace('"', '""') + '"'


def literal(value):
    if "\0" in str(value):
        raise DBError("NUL is not allowed in SQL values")
    return "E'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


@contextmanager
def connection_env(connection, database):
    env = os.environ.copy()
    for key in [*QUERY_ENV.values(), "PGPASSWORD", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE"]:
        env.pop(key, None)
    env.update(connection.params)
    env["PGDATABASE"] = database
    env.setdefault("PGCONNECT_TIMEOUT", "8")
    env["PGAPPNAME"] = "linux-setup-db"
    env["PGCLIENTENCODING"] = "UTF8"
    env["PGOPTIONS"] = env.get("PGOPTIONS", "") + " -c statement_timeout=30000 -c lock_timeout=3000"
    if not connection.password:
        # Preserve the normal .pgpass behavior when the URL has no password.
        if "PGPASSFILE" in os.environ:
            env["PGPASSFILE"] = os.environ["PGPASSFILE"]
        yield env
        return
    with tempfile.NamedTemporaryFile(mode="w", prefix="dev-db-pass-", encoding="utf-8") as file:
        os.chmod(file.name, 0o600)
        password = connection.password.replace("\\", "\\\\").replace(":", "\\:")
        file.write(f"*:*:*:*:{password}\n")
        file.flush()
        env["PGPASSFILE"] = file.name
        yield env


class Postgres:
    def __init__(self, connection, maintenance="postgres"):
        self.connection, self.maintenance = connection, maintenance

    def execute(self, sql, database=None):
        with connection_env(self.connection, database or self.maintenance) as env:
            try:
                result = subprocess.run(["psql", "-X", "--no-password", "--quiet", "--no-align", "--tuples-only", "--set=ON_ERROR_STOP=1", "--file=-"],
                                        input=sql, env=env, capture_output=True, text=True, timeout=45)
            except subprocess.TimeoutExpired:
                raise DBError("PostgreSQL operation timed out; check the server before retrying") from None
        if result.returncode:
            raise DBError(self.connection.redact(result.stderr.strip() or "psql failed"))
        return result.stdout.strip()

    def query(self, sql, database=None):
        try:
            return json.loads(self.execute(sql, database))
        except json.JSONDecodeError:
            raise DBError("psql returned an unexpected response") from None

    def databases(self):
        return self.query("SELECT COALESCE(json_agg(json_build_object('name',datname,'owner',pg_get_userbyid(datdba)) ORDER BY datname),'[]'::json) FROM pg_database WHERE NOT datistemplate;")

    def schemas(self, database):
        return self.query("SELECT COALESCE(json_agg(json_build_object('name',nspname,'owner',pg_get_userbyid(nspowner)) ORDER BY nspname),'[]'::json) FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname <> 'information_schema';", database)

    def snapshot(self, kind, name, database=None):
        if kind == "database":
            sql = f"""SELECT (to_jsonb(d) || jsonb_build_object(
                'owner',pg_get_userbyid(datdba),'encoding_name',pg_encoding_to_char(encoding),
                'tablespace_name',(SELECT spcname FROM pg_tablespace WHERE oid=dattablespace),
                'comment',shobj_description(oid,'pg_database'),
                'grants',(SELECT COALESCE(json_agg(json_build_object('public',a.grantee=0,'role',pg_get_userbyid(a.grantee),'privilege',a.privilege_type,'grantable',a.is_grantable)),'[]'::json)
                          FROM aclexplode(COALESCE(datacl,acldefault('d',datdba))) a)))::json
                FROM pg_database d WHERE datname={literal(name)};"""
        else:
            sql = f"""SELECT json_build_object('name',nspname,'owner',pg_get_userbyid(nspowner),
                'comment',obj_description(oid,'pg_namespace'),
                'grants',(SELECT COALESCE(json_agg(json_build_object('public',a.grantee=0,'role',pg_get_userbyid(a.grantee),'privilege',a.privilege_type,'grantable',a.is_grantable)),'[]'::json)
                          FROM aclexplode(COALESCE(nspacl,acldefault('n',nspowner))) a))
                FROM pg_namespace WHERE nspname={literal(name)};"""
        value = self.execute(sql, database)
        if not value:
            raise DBError(f"{kind.title()} no longer exists: {visible(name)}")
        return json.loads(value)

    def protect(self, kind, name):
        identifier(name)
        if kind == "database" and name in {"postgres", "template0", "template1", self.maintenance}:
            raise DBError(f"Protected database: {visible(name)}")
        if kind == "schema" and (name.startswith("pg_") or name == "information_schema"):
            raise DBError(f"Protected schema: {visible(name)}")

    def create(self, kind, name, database=None):
        self.protect(kind, name)
        suffix = " TEMPLATE template0" if kind == "database" else ""
        self.execute(f"CREATE {kind.upper()} {identifier(name)}{suffix};", database)

    def remove(self, kind, name, database=None):
        self.protect(kind, name)
        suffix = " CASCADE" if kind == "schema" else ""
        # No FORCE: an occupied database must be disconnected by its users first.
        self.execute(f"DROP {kind.upper()} {identifier(name)}{suffix};", database)

    def reset(self, kind, name, database=None):
        self.protect(kind, name)
        snapshot = self.snapshot(kind, name, database)
        if kind == "database" and snapshot.get("datistemplate"):
            raise DBError("Template databases cannot be reset")
        create = create_statement(kind, name, snapshot)
        restore = restore_access(kind, name, snapshot)
        if kind == "schema":
            self.execute(f"BEGIN;\nDROP SCHEMA {identifier(name)} CASCADE;\n{create}\n{restore}\nCOMMIT;", database)
            return
        # CREATE/DROP DATABASE cannot run in a transaction. Retain a private
        # recreation script if recreation fails after a successful DROP.
        folder = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "linux-setup/db-recovery"
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", prefix="recreate-", dir=folder, delete=False) as file:
            file.write(create + "\n" + restore + "\n")
            recovery = Path(file.name)
        os.chmod(recovery, 0o600)
        dropped = False
        try:
            self.execute(f"DROP DATABASE {identifier(name)};")
            dropped = True
            self.execute(create)
            self.execute(restore)
        except DBError as error:
            if dropped:
                raise DBError(f"Reset was interrupted after DROP; inspect the database before retrying. Recovery SQL: {recovery}. {error}") from None
            recovery.unlink(missing_ok=True)
            raise
        recovery.unlink(missing_ok=True)


def create_statement(kind, name, snapshot):
    owner = identifier(snapshot["owner"])
    if kind == "schema":
        return f"CREATE SCHEMA {identifier(name)} AUTHORIZATION {owner};"
    sql = f"CREATE DATABASE {identifier(name)} WITH TEMPLATE template0 OWNER {owner}"
    for option, field in [("ENCODING", "encoding_name"), ("LC_COLLATE", "datcollate"), ("LC_CTYPE", "datctype")]:
        if snapshot.get(field) is not None:
            sql += f" {option} {literal(snapshot[field])}"
    provider = snapshot.get("datlocprovider")
    if provider in {"c", "i", "b"}:
        sql += " LOCALE_PROVIDER " + {"c": "libc", "i": "icu", "b": "builtin"}[provider]
    locale = snapshot.get("datlocale") or snapshot.get("daticulocale")
    if locale and provider in {"i", "b"}:
        sql += f" {'ICU_LOCALE' if provider == 'i' else 'BUILTIN_LOCALE'} {literal(locale)}"
    if snapshot.get("daticurules") and provider == "i":
        sql += " ICU_RULES " + literal(snapshot["daticurules"])
    if snapshot.get("tablespace_name"):
        sql += " TABLESPACE " + identifier(snapshot["tablespace_name"])
    sql += f" CONNECTION LIMIT {int(snapshot.get('datconnlimit', -1))}"
    if not snapshot.get("datallowconn", True):
        sql += " ALLOW_CONNECTIONS false"
    return sql + ";"


def restore_access(kind, name, snapshot):
    target = f"{kind.upper()} {identifier(name)}"
    statements = [f"REVOKE ALL ON {target} FROM PUBLIC;", f"REVOKE ALL ON {target} FROM {identifier(snapshot['owner'])};"]
    allowed = {"CONNECT", "CREATE", "TEMPORARY", "TEMP"} if kind == "database" else {"CREATE", "USAGE"}
    for grant in snapshot.get("grants", []):
        privilege = grant["privilege"]
        if privilege not in allowed:
            raise DBError("Unexpected privilege in PostgreSQL catalog")
        role = "PUBLIC" if grant["public"] else identifier(grant["role"])
        extra = " WITH GRANT OPTION" if grant["grantable"] else ""
        statements.append(f"GRANT {privilege} ON {target} TO {role}{extra};")
    if snapshot.get("comment") is not None:
        statements.append(f"COMMENT ON {target} IS {literal(snapshot['comment'])};")
    return "\n".join(statements)


def choose(title, choices, multi=False):
    if not choices:
        print("No available items.")
        return [] if multi else None
    args = ["fzf", "--height=80%", "--layout=reverse", "--border", "--no-sort", "--read0", "--print0",
            "--delimiter=\t", "--with-nth=2..", "--prompt=" + title + " > ",
            "--header=↑/↓ move · Space select · Enter accept · Esc back"]
    args += ["--multi", "--bind=space:toggle+down,ctrl-a:select-all,ctrl-d:deselect-all"] if multi else ["--bind=space:accept"]
    env = os.environ.copy()
    env["FZF_DEFAULT_OPTS"] = ""
    env.pop("FZF_DEFAULT_OPTS_FILE", None)
    data = "".join(f"{index}\t{visible(label)}\0" for index, (label, _) in enumerate(choices))
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, text=True, env=env)
    if result.returncode in (1, 130):
        return [] if multi else None
    if result.returncode:
        raise DBError("fzf could not open its menu")
    selected = []
    for row in result.stdout.split("\0"):
        if row:
            try:
                index = int(row.split("\t", 1)[0])
                if not 0 <= index < len(choices):
                    raise ValueError
                selected.append(choices[index][1])
            except (ValueError, IndexError):
                raise DBError("Invalid menu selection") from None
    return selected if multi else (selected[0] if selected else None)


def confirm(action, kind, names, connection, database):
    print(f"\nConnection: {connection.label}")
    if kind == "schema":
        print("Database:", visible(database))
    print("Targets:", ", ".join(visible(n) for n in names))
    print("This permanently deletes all contained data and objects. Schema CASCADE may also remove dependent objects in other schemas.")
    if action == "reset" and kind == "database":
        print("Database reset drops and recreates the database; the two operations cannot be atomic. Active connections are not forced off.")
    phrase = f"{action.upper()} {names[0]}" if len(names) == 1 else f"{action.upper()} {len(names)} {kind.upper()}S"
    return input(f"Type {visible(phrase)} to continue: ") == phrase


def manage(pg, kind, database=None):
    while True:
        action = choose(kind.title() + " actions", [(n.title(), n) for n in ["list", "create", "remove", "reset"]] + [("Back", "back")])
        if action in (None, "back"):
            return
        try:
            if action == "create":
                name = input(f"New {kind} name (blank cancels): ").strip()
                if name:
                    pg.create(kind, name, database)
                    print(f"Created {kind}: {visible(name)}")
            else:
                rows = pg.databases() if kind == "database" else pg.schemas(database)
                if action == "list":
                    print(f"\n{'NAME':<36} OWNER")
                    for row in rows:
                        print(f"{visible(row['name']):<36} {visible(row['owner'])}")
                else:
                    targets = []
                    for row in rows:
                        try:
                            pg.protect(kind, row["name"])
                            targets.append((f"{row['name']}  (owner: {row['owner']})", row["name"]))
                        except DBError:
                            pass
                    names = choose(f"{action.title()} {kind}s", targets, multi=True)
                    if names and confirm(action, kind, names, pg.connection, database):
                        for name in names:
                            getattr(pg, action)(kind, name, database)
                            print(f"{action.title()} complete: {visible(name)}")
                    elif names:
                        print("Cancelled; no changes made.")
        except DBError as error:
            print(f"\n{error}", file=sys.stderr)
        input("\nEnter to return to the menu…")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", default=".env", help="Dotenv file (default: .env)")
    parser.add_argument("-f", "--env-file", help="Explicit dotenv file path")
    parser.add_argument("--var", action="append", help="Read only this variable; repeat for multiple variables. By default, discover URL names including DB_URL, DATABASE_URL, TEST_DB_URL, and TEST_DATABASE_URL")
    parser.add_argument("--maintenance-db", default="postgres", help="Database for server-level operations")
    parser.add_argument("--connections", action="store_true", help="List redacted connection labels without connecting")
    args = parser.parse_args(argv)
    try:
        connections = load_connections(Path(args.env_file or args.file).expanduser(), args.var)
        if args.connections:
            for connection in connections:
                print(connection.label)
            return 0
        for program in ["psql", "fzf"]:
            if not shutil.which(program):
                raise DBError(f"Missing {program}; run ./install.sh from linux-setup")
        if not sys.stdin.isatty():
            raise DBError("The interactive manager requires a terminal; --connections works without one")
        while True:
            connection = choose("Connection", [(c.label, c) for c in connections])
            if connection is None:
                return 0
            pg = Postgres(connection, args.maintenance_db)
            while True:
                action = choose(connection.label, [("Databases", "database"), ("Schemas", "schema"), ("Switch connection", "switch"), ("Quit", "quit")])
                if action in (None, "switch"):
                    break
                if action == "quit":
                    return 0
                try:
                    if action == "database":
                        manage(pg, "database")
                    else:
                        database = choose("Database for schemas", [(r["name"], r["name"]) for r in pg.databases()])
                        if database is not None:
                            manage(pg, "schema", database)
                except DBError as error:
                    print(error, file=sys.stderr)
                    input("Enter to return…")
    except (DBError, OSError) as error:
        print(f"dev-db: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 130
