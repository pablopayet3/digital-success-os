"""One way to talk to the warehouse, whichever one it is.

Synthetic data, fictional company.

dev uses a local DuckDB file. prod uses a Databricks SQL warehouse with Unity
Catalog (`relay.bronze`, `relay.silver`, `relay.gold`). Python code that reads or
writes warehouse tables goes through this module, so it does not care which.

Three operations cover everything the project needs:
    query(sql)                 run a SELECT, get a pandas DataFrame
    execute(sql)               run a statement that returns nothing
    write_table(name, frame)   replace a table with the rows of a DataFrame

Table names are written the same way in both (for example `gold.account_scores`):
the Databricks connection is opened inside the `relay` catalog.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from common.paths import DATA_DIR
from common.settings import Settings, load_settings, secret


class DuckDBWarehouse:
    kind = "duckdb"

    def __init__(self, path: Path):
        self.con = duckdb.connect(str(path))

    def query(self, sql: str) -> pd.DataFrame:
        return self.con.execute(sql).df()

    def execute(self, sql: str) -> None:
        self.con.execute(sql)

    def write_table(self, table: str, frame: pd.DataFrame) -> None:
        self.con.register("frame_to_write", frame)
        self.con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM frame_to_write")
        self.con.unregister("frame_to_write")

    def close(self) -> None:
        self.con.close()


def databricks_token(host: str) -> str:
    """A token for this run, without anyone typing a secret.

    If DATABRICKS_TOKEN is set (a personal access token, or a secret in CI) it is used.
    Otherwise we sign in through the browser (OAuth): a tab opens, the person who is
    already logged in to Databricks approves, and a short-lived token comes back. It is
    kept in this process only, so dbt and the SQL connection can use it; it is never
    printed or written into the project.
    """
    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        return token
    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient(host=f"https://{host}", auth_type="external-browser")
    header = client.config.authenticate()  # {"Authorization": "Bearer ..."}
    token = header["Authorization"].removeprefix("Bearer ")
    os.environ["DATABRICKS_TOKEN"] = token  # dbt reads it from here, in this process
    return token


class DatabricksWarehouse:
    """Databricks SQL warehouse. Files reach it through a Unity Catalog volume."""

    kind = "databricks"

    def __init__(self, settings: Settings):
        from databricks import sql  # imported here: only prod needs it
        from databricks.sdk import WorkspaceClient

        host = secret("DATABRICKS_HOST")
        token = databricks_token(host)
        self.volume = settings.landing_volume
        self.con = sql.connect(
            server_hostname=host, http_path=secret("DATABRICKS_HTTP_PATH"), access_token=token
        )
        self.files = WorkspaceClient(host=f"https://{host}", token=token).files
        self._use_catalog(settings.catalog)

    def _use_catalog(self, catalog: str) -> None:
        """Work inside the project's catalog, creating it on the first run if allowed."""
        try:
            self.execute(f"CREATE CATALOG IF NOT EXISTS {catalog}")
        except Exception:  # no permission to create: fine if the catalog already exists
            pass
        try:
            self.execute(f"USE CATALOG {catalog}")
        except Exception as error:
            raise RuntimeError(
                f"The catalog '{catalog}' does not exist and could not be created. Set "
                "DATABRICKS_CATALOG to a catalog that exists (Free Edition has 'workspace')."
            ) from error

    def query(self, sql: str) -> pd.DataFrame:
        with self.con.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall_arrow().to_pandas()

    def execute(self, sql: str) -> None:
        with self.con.cursor() as cursor:
            cursor.execute(sql)

    def upload(self, local_path: Path, volume_path: str) -> str:
        """Copy a local file into the volume. Returns its full path there."""
        target = f"{self.volume}/{volume_path}"
        with open(local_path, "rb") as f:
            self.files.upload(target, f, overwrite=True)
        return target

    def write_table(self, table: str, frame: pd.DataFrame) -> None:
        """Write the rows as a Parquet file in the volume, then load it as a table."""
        # Found on the first real run: read_files() adds a `_rescued_data` column, which
        # then came back in the next read and broke the next write. So the file is read
        # directly as Parquet (no extra column), and a stray one is dropped on the way in.
        frame = frame.drop(columns=["_rescued_data"], errors="ignore")
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / f"{table}.parquet"
            frame.to_parquet(local, index=False)
            uploaded = self.upload(local, f"_from_python/{table}.parquet")
        self.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM parquet.`{uploaded}`")

    def close(self) -> None:
        self.con.close()


def open_warehouse(data_dir: Path = DATA_DIR, settings: Settings | None = None):
    """Open the warehouse of the current environment (DSO_ENV)."""
    settings = settings or load_settings()
    if settings.warehouse == "databricks":
        return DatabricksWarehouse(settings)
    return DuckDBWarehouse(data_dir / "warehouse.duckdb")
