from src.agent.parsing import (
    compute_fingerprint,
    extract_exception_type,
    get_trigger_frame,
    normalize_path,
    path_candidates,
    split_embedded_trace,
)

PY = """Traceback (most recent call last):
  File "/app/src/api.py", line 10, in handler
    return svc.run(x)
  File "/usr/local/lib/python3.11/site-packages/foo/bar.py", line 5, in run
    pass
  File "/app/src/services/user.py", line 42, in get_user
    return data["email"]
KeyError: 'email'
"""


def test_python_trigger_frame_skips_library_frames():
    frame = get_trigger_frame(PY)
    assert (frame.path, frame.line, frame.function) == ("/app/src/services/user.py", 42, "get_user")


def test_javascript_and_java_frames():
    js = "TypeError: x\n    at getUser (/app/src/user.js:12:15)\n    at node:internal/modules/cjs/loader:1105:14"
    assert get_trigger_frame(js).path == "/app/src/user.js"
    java = "java.lang.NullPointerException: x\n    at com.acme.shop.OrderService.total(OrderService.java:77)"
    assert get_trigger_frame(java).path == "com/acme/shop/OrderService.java"


def test_paths():
    assert normalize_path("/app/src/x.py") == "src/x.py"
    assert path_candidates("/app/src/services/user.py") == ["src/services/user.py", "services/user.py", "user.py"]


def test_exception_type_and_embedded_trace():
    assert extract_exception_type("KeyError: 'email'", PY) == "KeyError"
    msg, trace = split_embedded_trace("boom\n" + PY, "")
    assert msg == "boom" and trace.startswith("Traceback")


def test_fingerprint_ignores_line_numbers_and_ids():
    a = compute_fingerprint("o/r", "KeyError: 'email'", PY)
    b = compute_fingerprint("o/r", "KeyError: 'email'", PY.replace("line 42", "line 99"))
    assert a == b and len(a) == 64
    assert a != compute_fingerprint("o/other", "KeyError: 'email'", PY)
