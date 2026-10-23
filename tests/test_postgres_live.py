"""Optional integration test. Always starts its own isolated PostgreSQL cluster."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import db_manager as db

TEST_POSTGRES_BIN = os.environ.get("LINUX_SETUP_TEST_POSTGRES_BIN") or os.environ.get("DEV_SETUP_TEST_POSTGRES_BIN")

@unittest.skipUnless(TEST_POSTGRES_BIN, "Set LINUX_SETUP_TEST_POSTGRES_BIN to test with a disposable local server")
class PostgresLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="linux-setup-postgres-")
        cls.root = Path(cls.temporary.name)
        cls.data, cls.socket = cls.root / "data", cls.root / "socket"
        cls.socket.mkdir()
        cls.bin = Path(TEST_POSTGRES_BIN)
        shared = cls.bin.parents[3] / "share/postgresql" / cls.bin.parent.name
        command = [str(cls.bin / "initdb"), "-D", str(cls.data), "-U", "dev_setup_test", "--auth=trust", "--no-locale", "--encoding=UTF8"]
        if shared.is_dir():
            command += ["-L", str(shared)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            cls.temporary.cleanup()
            raise RuntimeError(result.stderr)
        cls.log = (cls.root / "postgres.log").open("w")
        cls.server = subprocess.Popen([str(cls.bin / "postgres"), "-D", str(cls.data), "-k", str(cls.socket), "-h", "", "-p", "5432"], stdout=cls.log, stderr=subprocess.STDOUT)
        cls.connection = db.parse_connection("isolated test server", "postgresql://dev_setup_test@/postgres?host=" + quote(str(cls.socket), safe=""))
        cls.pg = db.Postgres(cls.connection)
        for _ in range(100):
            try:
                cls.pg.execute("SELECT 1;")
                return
            except db.DBError:
                if cls.server.poll() is not None:
                    break
                time.sleep(0.1)
        cls.server.send_signal(signal.SIGINT)
        cls.server.wait(timeout=10)
        cls.log.close()
        error = (cls.root / "postgres.log").read_text()
        cls.temporary.cleanup()
        raise RuntimeError("Temporary PostgreSQL did not start: " + error)

    @classmethod
    def tearDownClass(cls):
        cls.server.send_signal(signal.SIGINT)
        cls.server.wait(timeout=10)
        cls.log.close()
        cls.temporary.cleanup()

    def test_database_and_schema_lifecycle_preserves_access(self):
        pg = self.pg
        database, schema = 'app "quoted"', 'schema "quoted"'
        pg.execute('CREATE ROLE "dev_access";')
        pg.create("database", database)
        self.assertIn(database, [row["name"] for row in pg.databases()])
        pg.create("schema", schema, database)
        pg.execute(f"GRANT USAGE ON SCHEMA {db.identifier(schema)} TO dev_access; COMMENT ON SCHEMA {db.identifier(schema)} IS 'preserve me'; CREATE TABLE {db.identifier(schema)}.test (id integer);", database)
        before = pg.snapshot("schema", schema, database)
        pg.reset("schema", schema, database)
        after = pg.snapshot("schema", schema, database)
        self.assertEqual(before, after)
        tables = pg.query("SELECT json_build_object('count',count(*)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=" + db.literal(schema) + ";", database)
        self.assertEqual(tables["count"], 0)
        pg.remove("schema", schema, database)
        self.assertNotIn(schema, [row["name"] for row in pg.schemas(database)])
        pg.execute(f"REVOKE ALL ON DATABASE {db.identifier(database)} FROM PUBLIC; GRANT CONNECT ON DATABASE {db.identifier(database)} TO dev_access; COMMENT ON DATABASE {db.identifier(database)} IS 'database comment';")
        before = pg.snapshot("database", database)
        pg.reset("database", database)
        after = pg.snapshot("database", database)
        for key in ["owner", "encoding_name", "datcollate", "datctype", "datconnlimit", "comment", "grants"]:
            self.assertEqual(before[key], after[key], key)
        pg.remove("database", database)
        self.assertNotIn(database, [row["name"] for row in pg.databases()])
        # A SQL-looking name is still only an identifier.
        strange = 'quoted"; DROP DATABASE postgres; --'
        pg.create("database", strange)
        self.assertIn("postgres", [row["name"] for row in pg.databases()])
        pg.remove("database", strange)

    def test_public_schema_reset_and_active_database_refusal(self):
        pg = self.pg
        name = "active_test"
        pg.create("database", name)
        before = pg.snapshot("schema", "public", name)
        pg.reset("schema", "public", name)
        self.assertEqual(before, pg.snapshot("schema", "public", name))
        with db.connection_env(self.connection, name) as env:
            child = subprocess.Popen(["psql", "-X", "--no-password", "--command", "SELECT pg_sleep(30);"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    row = pg.query("SELECT json_build_object('count',count(*)) FROM pg_stat_activity WHERE datname='active_test';")
                    if row["count"]:
                        break
                    time.sleep(0.05)
                self.assertTrue(row["count"])
                with self.assertRaises(db.DBError):
                    pg.remove("database", name)
            finally:
                child.terminate()
                child.wait(timeout=5)
        pg.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='active_test' AND pid <> pg_backend_pid();")
        pg.remove("database", name)
