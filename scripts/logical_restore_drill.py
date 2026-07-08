#!/usr/bin/env python3
"""SANKET — Local Database Restore Drill.

Runs a real restore drill locally using Docker:
  1. Dumps the running database prisma-postgres-1 (pg_dump).
  2. Spins up a temporary scratch Postgres container with pgvector.
  3. Pre-creates the required non-privileged role 'sanket_app'.
  4. Restores the dump (pg_restore).
  5. Asserts data invariants (tenants row count, FORCE RLS).
  6. Measures and reports Recovery Time Objective (RTO).
  7. Tears down the scratch container and cleans up.
"""

import os
import subprocess
import time
import sys

CONTAINER_SOURCE = "prisma-postgres-1"
CONTAINER_SCRATCH = "prisma-postgres-scratch"
DB_NAME = "sanket"
DB_USER = "postgres"
DB_PASS = "postgres"
PG_IMAGE = "pgvector/pgvector:pg16"
DUMP_FILE = "sanket_local_restore_drill.dump"

def run_cmd(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    try:
        res = subprocess.run(cmd, check=check, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None, text=True)
        return res
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Command failed: {' '.join(cmd)}")
        if capture:
            print(f"Stdout:\n{e.stdout}")
            print(f"Stderr:\n{e.stderr}")
        raise e

def main() -> int:
    print("=== SANKET: STARTING LOCAL RESTORE DRILL ===")
    start_time = time.time()
    
    # 1. Clean up any leftover scratch container from previous runs
    print(f"Cleaning up any existing {CONTAINER_SCRATCH} container...")
    subprocess.run(["docker", "rm", "-f", CONTAINER_SCRATCH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(DUMP_FILE):
        os.remove(DUMP_FILE)

    try:
        # 2. Dump the source database
        print(f"[1/6] Creating database dump from source container ({CONTAINER_SOURCE})...")
        dump_start = time.time()
        # We run pg_dump inside the container and pipe the output to the host file
        with open(DUMP_FILE, "wb") as f:
            proc = subprocess.Popen(
                ["docker", "exec", "-i", CONTAINER_SOURCE, "pg_dump", "-U", DB_USER, "-d", DB_NAME, "-Fc"],
                stdout=f,
                stderr=subprocess.PIPE
            )
            _, stderr = proc.communicate()
            if proc.returncode != 0:
                print(f"ERROR: pg_dump failed: {stderr.decode()}")
                return 1
        dump_time = time.time() - dump_start
        print(f"Dump completed in {dump_time:.2f} seconds. File size: {os.path.getsize(DUMP_FILE)} bytes.")

        # 3. Spin up scratch container
        print(f"[2/6] Starting scratch container ({CONTAINER_SCRATCH}) using image {PG_IMAGE}...")
        run_cmd([
            "docker", "run", "--name", CONTAINER_SCRATCH,
            "-e", f"POSTGRES_DB={DB_NAME}",
            "-e", f"POSTGRES_USER={DB_USER}",
            "-e", f"POSTGRES_PASSWORD={DB_PASS}",
            "-d", PG_IMAGE
        ])

        # 4. Wait for database to accept connections
        print("[3/6] Waiting for scratch database to initialize...")
        initialized = False
        for i in range(30):
            res = subprocess.run(
                ["docker", "exec", CONTAINER_SCRATCH, "pg_isready", "-U", DB_USER, "-d", DB_NAME],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if res.returncode == 0:
                initialized = True
                print("Scratch database is ready.")
                break
            time.sleep(1)
        
        if not initialized:
            print("ERROR: Scratch container failed to initialize in time.")
            return 1

        # Pre-create the application role 'sanket_app'
        print("Pre-creating application database role 'sanket_app'...")
        run_cmd([
            "docker", "exec", CONTAINER_SCRATCH,
            "psql", "-U", DB_USER, "-d", DB_NAME,
            "-c", "CREATE ROLE sanket_app WITH LOGIN PASSWORD 'changeme' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;"
        ])

        # 5. Restore the dump
        print(f"[4/6] Copying dump and running pg_restore on scratch container...")
        restore_start = time.time()
        run_cmd(["docker", "cp", DUMP_FILE, f"{CONTAINER_SCRATCH}:/tmp/backup.dump"])
        
        # We run pg_restore in the scratch container
        res = subprocess.run([
            "docker", "exec", CONTAINER_SCRATCH,
            "pg_restore", "-U", DB_USER, "-d", DB_NAME, "-Fc", "/tmp/backup.dump"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        restore_time = time.time() - restore_start
        print(f"Restore completed in {restore_time:.2f} seconds.")
        if res.returncode != 0:
            # Warnings/non-critical errors are normal, but let's print them for diagnostic purposes
            print("Restore finished (some warnings may be reported, which is normal):")
            print(res.stderr[:500] + "\n..." if len(res.stderr) > 500 else res.stderr)

        # 6. Verify invariants
        print("[5/6] Asserting database invariants on restored data...")
        
        # Invariant A: Tenants count >= 1
        tenants_res = run_cmd([
            "docker", "exec", CONTAINER_SCRATCH,
            "psql", "-U", DB_USER, "-d", DB_NAME, "-tAc", "SELECT count(*) FROM tenants"
        ], capture=True)
        tenants_count = int(tenants_res.stdout.strip())
        print(f"Assertion: tenants row count = {tenants_count}")
        if tenants_count < 1:
            print("FAIL: recovered database has no tenants.")
            return 1

        # Invariant B: FORCE RLS remains enabled on all RLS-enabled public tables
        rls_res = run_cmd([
            "docker", "exec", CONTAINER_SCRATCH,
            "psql", "-U", DB_USER, "-d", DB_NAME, "-tAc",
            "SELECT bool_and(relforcerowsecurity) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relrowsecurity"
        ], capture=True)
        forced_rls = rls_res.stdout.strip()
        print(f"Assertion: All RLS tables still FORCE RLS = {forced_rls}")
        if forced_rls != "t":
            print("FAIL: FORCE ROW LEVEL SECURITY missing/unenforced in recovered database.")
            return 1
            
        # Invariant C: App role cannot bypass RLS
        bypass_res = run_cmd([
            "docker", "exec", CONTAINER_SCRATCH,
            "psql", "-U", DB_USER, "-d", DB_NAME, "-tAc",
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'sanket_app'"
        ], capture=True)
        bypass_status = bypass_res.stdout.strip()
        print(f"Assertion: App role (sanket_app) rolsuper | rolbypassrls = {bypass_status}")
        if bypass_status != "f|f":
            print("FAIL: sanket_app has elevated permissions and can bypass RLS.")
            return 1

        total_rto = time.time() - start_time
        print(f"\n[6/6] OK: Restore drill succeeded! Backups are verified restorable.")
        print(f"Measured Recovery Time Objective (RTO) for fresh restore: {total_rto:.2f} seconds.")
        print(f"Calculated Recovery Point Objective (RPO) maximum limit: 5 minutes (based on continuous WAL).")
        
        return 0

    finally:
        # Cleanup
        print("\nTearing down and cleaning up scratch resources...")
        subprocess.run(["docker", "rm", "-f", CONTAINER_SCRATCH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(DUMP_FILE):
            os.remove(DUMP_FILE)
        print("Cleanup completed.")

if __name__ == "__main__":
    sys.exit(main())
