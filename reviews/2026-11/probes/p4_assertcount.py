# pytest plugin (PYTHONPATH=reviews/2026-11/probes pytest -p p4_assertcount -s <tests>): prints how many times each test's own assert lines ran.
"""pytest plugin: for each test, counts how many of its own `assert` lines ran (including in nested loops)."""
import ast, sys, pytest, threading
_asserts = {}
def assert_lines(fn):
    code = fn.__code__
    try:
        src = open(code.co_filename).read()
    except OSError:
        return set()
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno <= code.co_firstlineno <= n.lineno + len(n.decorator_list) + 1 and n.name == code.co_name:
            lines = set()
            for m in ast.walk(n):
                if isinstance(m, ast.Assert):
                    lines.add(m.lineno)
            return lines
    return set()
RESULTS = []
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    fn = getattr(item, "function", None)
    if fn is None:
        yield; return
    want = assert_lines(fn); hit = {}
    fname = fn.__code__.co_filename
    def tracer(frame, event, arg):
        if frame.f_code.co_filename != fname:
            return None
        def local(frame, event, arg):
            if event == "line" and frame.f_lineno in want:
                hit[frame.f_lineno] = hit.get(frame.f_lineno, 0) + 1
            return local
        return local
    old = sys.gettrace(); sys.settrace(tracer)
    try:
        yield
    finally:
        sys.settrace(old)
    RESULTS.append((item.nodeid, len(want), sum(hit.values()), sorted(want - set(hit))))
def pytest_sessionfinish(session):
    for nodeid, n, ran, missed in RESULTS:
        print(f"\nASSERTS {nodeid}: {n} assert lines, {ran} executions, never ran: {missed}")
