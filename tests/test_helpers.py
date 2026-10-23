import io
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import db_manager as db
import ports


class DotenvTests(unittest.TestCase):
    def load(self, text, variables=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            path.write_text(text)
            return db.load_connections(path, variables)

    def test_named_and_array_urls_and_variable_expansion(self):
        connections = self.load('PASS=secret\nDB_URL="postgresql://me:${PASS}@localhost/app" # comment\nDB_URLS=\'{"test":"postgresql://localhost/app_test"}\'\nDATABASE_URLS=["postgresql://localhost/other"]\n')
        self.assertEqual([c.database for c in connections], ["app", "app_test", "other"])
        self.assertEqual(connections[0].password, "secret")
        self.assertNotIn("secret", connections[0].label)
        self.assertEqual(connections[1].name, "DB_URLS.test")

    def test_explicit_variable_and_unrelated_settings(self):
        connections = self.load('UNRELATED=${NOT_DEFINED}\nCONNECTION=postgres://localhost/app\n', ["CONNECTION"])
        self.assertEqual(connections[0].database, "app")

    def test_commands_are_not_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "executed"
            with self.assertRaises(db.DBError):
                self.load(f'DB_URL="$(touch {marker})"\n')
            self.assertFalse(marker.exists())

    def test_cyclic_reference_and_invalid_json_hide_values(self):
        with self.assertRaisesRegex(db.DBError, "Cyclic"):
            self.load('A=${B}\nB=${A}\nDB_URL=${A}\n')
        with self.assertRaises(db.DBError) as error:
            self.load('DB_URLS=["super-secret"\n')
        self.assertNotIn("super-secret", str(error.exception))

    def test_orm_options_are_ignored_and_ssl_options_are_preserved(self):
        connection = db.parse_connection("DB_URL", "postgresql://me:p%3Aa%5Css@localhost:5433/app?schema=private&sslmode=require")
        self.assertEqual(connection.password, "p:a\\ss")
        self.assertEqual(connection.params["PGSSLMODE"], "require")
        self.assertEqual(connection.params["PGPORT"], "5433")
        self.assertNotIn("schema", connection.params)

    def test_no_url_or_password_in_psql_arguments(self):
        connection = db.parse_connection("DB_URL", "postgres://me:p%3Aa%5Css@localhost/app")
        saved = []
        def execute(args, **kwargs):
            self.assertNotIn(connection.original, " ".join(args))
            self.assertNotIn(connection.password, " ".join(args))
            self.assertNotIn("PGPASSWORD", kwargs["env"])
            file = Path(kwargs["env"]["PGPASSFILE"])
            saved.append(file)
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
            self.assertEqual(file.read_text(), "*:*:*:*:p\\:a\\\\ss\n")
            return subprocess.CompletedProcess(args, 1, "", "connection failed p:a\\ss")
        with patch.object(db.subprocess, "run", side_effect=execute):
            with self.assertRaises(db.DBError) as error:
                db.Postgres(connection).execute("SELECT 1;")
        self.assertNotIn(connection.password, str(error.exception))
        self.assertTrue(all(not path.exists() for path in saved))


class DatabaseActionTests(unittest.TestCase):
    def setUp(self):
        self.pg = db.Postgres(db.parse_connection("test", "postgres://localhost/app"))
        self.snapshot = {"owner": "owner", "grants": [{"public": True, "role": "", "privilege": "USAGE", "grantable": False}], "comment": "a comment"}

    def test_identifiers_cannot_inject_commands(self):
        name = 'test"; DROP DATABASE postgres; --'
        self.assertEqual(db.identifier(name), '"test""; DROP DATABASE postgres; --"')
        with patch.object(self.pg, "execute") as execute:
            self.pg.create("schema", name, "app")
        self.assertEqual(execute.call_args.args[0], 'CREATE SCHEMA "test""; DROP DATABASE postgres; --";')
        with self.assertRaises(db.DBError):
            db.identifier("x" * 64)

    def test_protected_objects_are_never_dropped(self):
        with patch.object(self.pg, "execute") as execute:
            for kind, name in [("database", "postgres"), ("database", "template0"), ("schema", "pg_catalog"), ("schema", "information_schema")]:
                with self.assertRaises(db.DBError):
                    self.pg.remove(kind, name)
        execute.assert_not_called()

    def test_schema_reset_is_atomic_and_restores_owner_and_grants(self):
        with patch.object(self.pg, "snapshot", return_value=self.snapshot), patch.object(self.pg, "execute") as execute:
            self.pg.reset("schema", "app", "db")
        sql = execute.call_args.args[0]
        self.assertTrue(sql.startswith("BEGIN;"))
        self.assertTrue(sql.endswith("COMMIT;"))
        self.assertIn('CREATE SCHEMA "app" AUTHORIZATION "owner"', sql)
        self.assertIn('GRANT USAGE ON SCHEMA "app" TO PUBLIC', sql)
        self.assertIn('COMMENT ON SCHEMA "app"', sql)

    def test_database_reset_preserves_recovery_sql_after_recreation_failure(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_STATE_HOME": temp}):
            snapshot = {**self.snapshot, "grants": [], "datcollate": "C", "datctype": "C", "encoding_name": "UTF8", "datlocprovider": "c"}
            with patch.object(self.pg, "snapshot", return_value=snapshot), patch.object(self.pg, "execute", side_effect=["", db.DBError("cannot recreate")]) as execute:
                with self.assertRaisesRegex(db.DBError, "Recovery SQL"):
                    self.pg.reset("database", "app")
            self.assertEqual(execute.call_args_list[0].args[0], 'DROP DATABASE "app";')
            files = list(Path(temp).rglob("*.sql"))
            self.assertEqual(len(files), 1)
            self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
            self.assertIn('CREATE DATABASE "app"', files[0].read_text())

    def test_declined_confirmation_does_not_change_database(self):
        with patch.object(db, "choose", side_effect=["remove", ["app"], "back"]), patch.object(db, "confirm", return_value=False), patch.object(db, "input", return_value=""), patch.object(self.pg, "databases", return_value=[{"name": "app", "owner": "me"}]), patch.object(self.pg, "remove") as remove:
            db.manage(self.pg, "database")
        remove.assert_not_called()

    def test_fzf_multi_selection_binds_space_and_uses_opaque_ids(self):
        with patch.object(db.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "1\tignored\0")) as run:
            result = db.choose("Items", [("first", "value1"), ("second", "value2")], multi=True)
        self.assertEqual(result, ["value2"])
        self.assertIn("--bind=space:toggle+down,ctrl-a:select-all,ctrl-d:deselect-all", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["env"]["FZF_DEFAULT_OPTS"], "")


class PortTests(unittest.TestCase):
    def test_parsers_handle_ipv6_and_hidden_pids(self):
        rows = ports.parse_lsof("p12\ncnode\nn[::1]:3000\nn127.0.0.1:4000\n")
        self.assertEqual([r["port"] for r in rows], [3000, 4000])
        rows = ports.parse_ss('LISTEN 0 128 [::]:3000 [::]:* users:(("node",pid=12,fd=4))\nLISTEN 0 128 *:4000 *:*\n')
        self.assertEqual(rows[0]["pid"], 12)
        self.assertIsNone(rows[1]["pid"])

    def test_cancelled_kill_and_changed_listener_are_not_signalled(self):
        row = {"port": 3000, "pid": 987654, "command": "test", "address": "*:3000"}
        with patch.object(ports, "listeners", return_value=[row]), patch.object(ports.sys.stdin, "isatty", return_value=True), patch.object(ports, "input", return_value="n"), patch.object(ports.os, "kill") as kill:
            self.assertEqual(ports.stop([3000]), 0)
        kill.assert_not_called()
        with patch.object(ports, "listeners", side_effect=[[row], []]), patch.object(ports.os, "kill") as kill:
            self.assertEqual(ports.stop([3000], yes=True), 0)
        kill.assert_not_called()

    def test_default_signal_is_term_and_flags_may_precede_ports(self):
        row = {"port": 3000, "pid": 987654, "command": "test", "address": "*:3000"}
        with patch.object(ports, "listeners", return_value=[row]), patch.object(ports, "process_identity", return_value="same"), patch.object(ports.os, "kill") as kill:
            ports.stop([3000], yes=True)
        kill.assert_called_once_with(987654, signal.SIGTERM)
        with patch.object(ports, "stop", return_value=0) as stop:
            self.assertEqual(ports.main(["kill", "--force", "--yes", "3000"]), 0)
        stop.assert_called_once_with([3000], True, True)

    def test_real_listener_can_be_listed_and_stopped(self):
        if not (shutil_which("lsof") or shutil_which("ss")):
            self.skipTest("No port inspection tool installed")
        process = subprocess.Popen([sys.executable, "-u", "-c", "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1]); time.sleep(60)"], stdout=subprocess.PIPE, text=True)
        try:
            port = int(process.stdout.readline())
            self.assertIn(process.pid, [row["pid"] for row in ports.listeners([port])])
            self.assertEqual(ports.stop([port], yes=True), 0)
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdout.close()


def shutil_which(name):
    import shutil
    return shutil.which(name)
