#!/usr/bin/env python3

import os
import json
import requests
import subprocess
import time
import sys
from typing import Callable, List, Any

# use docker or podman
engine = os.getenv("ENGINE", "docker")
base_url = "http://localhost:8081"


class TestCase:
    def __init__(self, name: str, fn: Callable):
        self.name = name
        self.run = fn


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def run_cleanup_cmd(args: List[str]) -> None:
    print(f"running: {' '.join(args)}", file=sys.stderr)
    try:
        result = subprocess.run(
            args, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if result.returncode == 0:
            print("  ✓ cleanup ok", file=sys.stderr)
        else:
            print(f"  ! cleanup fail (exit code {result.returncode})", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("  ! cleanup timeout", file=sys.stderr)


# kvs ops


def kvs_get(key: str) -> requests.Response:
    return requests.get(f"{base_url}/data/{key}")


def kvs_put(key: str, value: str) -> requests.Response:
    return requests.put(f"{base_url}/data/{key}", json={"value": value})


def kvs_delete(key: str) -> requests.Response:
    return requests.delete(f"{base_url}/data/{key}")


def kvs_get_all() -> requests.Response:
    return requests.get(f"{base_url}/data")


def kvs_clear() -> None:
    # util to clear all data
    for key in kvs_get_all().json().keys():
        r = kvs_delete(key)
        assert r.status_code == 200, f"failed to delete key {key}"


# test functions


def test_put_and_get():
    # new key should return 201
    r = kvs_put("test1", "hello")
    assert r.status_code == 201, f"expected 201 for new key, got {r.status_code}"

    # get should return value
    r = kvs_get("test1")
    assert r.status_code == 200, f"expected 200 for get, got {r.status_code}"
    assert r.json()["value"] == "hello", f"wrong value returned: {r.json()}"

    # clean up
    kvs_delete("test1")


def test_update():
    # setup
    kvs_put("test2", "original")

    # update should return 200
    r = kvs_put("test2", "updated")
    assert r.status_code == 200, f"expected 200 for update, got {r.status_code}"

    # verify update worked
    r = kvs_get("test2")
    assert r.json()["value"] == "updated", "update failed"

    # clean up
    kvs_delete("test2")


def test_delete():
    # setup
    kvs_put("test3", "delete_me")

    # delete should work
    r = kvs_delete("test3")
    assert r.status_code == 200, f"expected 200 for delete, got {r.status_code}"

    # key should be gone
    r = kvs_get("test3")
    assert r.status_code == 404, f"expected 404 after delete, got {r.status_code}"


def test_bulk_operations():
    # start empty
    kvs_clear()
    r = kvs_get_all()
    assert r.status_code == 200, f"expected 200 for empty get, got {r.status_code}"
    assert r.json() == {}, f"expected empty store, got: {r.json()}"

    # add data one by one, verify after each
    test_data = {"a": "first", "b": "second", "c": "third"}
    for k, v in test_data.items():
        # add new key
        r = kvs_put(k, v)
        assert (
            r.status_code == 201
        ), f"expected 201 for new key {k}, got {r.status_code}"

        # verify everything so far
        r = kvs_get_all()
        expected = {ek: test_data[ek] for ek in test_data.keys() if ek <= k}
        assert r.json() == expected, f"wrong data after adding {k}: {r.json()}"

    # verify that we can update the stored data
    updates = {"a": "updated_a", "c": "updated_c"}
    for k, v in updates.items():
        r = kvs_put(k, v)
        assert r.status_code == 200, f"expected 200 for update {k}, got {r.status_code}"

    # verify final state matches what we updated to
    r = kvs_get_all()
    expected = test_data.copy()
    expected.update(updates)
    assert r.json() == expected, f"wrong data after updates: {r.json()}"

    # verify delete affects bulk view
    r = kvs_delete("b")
    assert r.status_code == 200, f"expected 200 for delete, got {r.status_code}"

    r = kvs_get_all()
    del expected["b"]
    assert r.json() == expected, f"wrong data after delete: {r.json()}"

    # clean up
    kvs_clear()


def test_error_cases():
    # missing value field
    r = requests.put(f"{base_url}/data/test", json={"bad": "field"})
    assert r.status_code == 400, f"expected 400 for missing value, got {r.status_code}"

    # missing json
    r = requests.put(f"{base_url}/data/test", data="not json")
    assert r.status_code == 400, f"expected 400 for invalid json, got {r.status_code}"


# run test set
tests = [
    TestCase("put and get", test_put_and_get),
    TestCase("updates", test_update),
    TestCase("deletes", test_delete),
    TestCase("bulk operations", test_bulk_operations),
    TestCase("error cases", test_error_cases),
]


def run_tests(project_dir: str) -> dict:
    from contextlib import redirect_stdout, redirect_stderr
    from io import StringIO

    result = {"score": 0, "log": ""}
    log_buffer = StringIO()

    with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
        print(f"\ntesting project in {project_dir}")
        container = None

        try:
            # build docker image
            subprocess.run(
                [engine, "build", "-t", "kvstore-test", project_dir],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )

            # start container
            container = subprocess.Popen(
                [
                    engine,
                    "run",
                    "--rm",  # clean up container after exit
                    "--name",
                    "kvstore_test_container",
                    "-it",  # interactive
                    "--init",  # signal handling
                    "-p",
                    "8081:8081",  # port fwd
                    "kvstore-test",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # wait for service to become available
            start_time = time.time()
            connected = False
            while time.time() - start_time < 30:
                try:
                    requests.get(f"{base_url}/data")
                    connected = True
                    break
                except requests.ConnectionError:
                    time.sleep(0.5)

            if not connected:
                result["log"] = log_buffer.getvalue()
                return result

            # run all tests
            all_passed = True
            n_passed = 0
            for test in tests:
                try:
                    test.run()
                    n_passed += 1
                    print(f"  ✓ {test.name}")
                except Exception as e:
                    print(f"  ✗ {test.name} failed: {str(e)}")
                    all_passed = False

            result["score"] = 1 if all_passed else 0
            result["n_passed"] = n_passed

        except subprocess.CalledProcessError as e:
            print(f"docker build failed: {str(e)}")
        except Exception as e:
            print(f"unexpected error: {str(e)}")
        finally:
            # ensure proper cleanup of docker resources
            if container:
                container.kill()
                container.wait()
                run_cleanup_cmd([engine, "rm", "-f", "kvstore_test_container"])

    result["log"] = log_buffer.getvalue()
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 test.py <project_directory>")
        sys.exit(1)

    results = run_tests(sys.argv[1])
    print("\ntest results:")
    print(f"score: {results['score']}/1")
    print(f"log output:\n{results['log']}")
