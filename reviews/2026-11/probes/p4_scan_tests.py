# Lists tests with no assertion, constant assertions, assertions only inside a loop or an if, and broad pytest.raises (usage: python3 p4_scan_tests.py <repository root>; a scan, it gives no RESULT line).
import ast, sys, glob, os
root = sys.argv[1]
files = sorted(glob.glob(os.path.join(root, "tests", "*.py")))
asserting_helpers = {}
def has_assert(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Assert): return True
        if isinstance(n, ast.With):
            for it in n.items:
                c = it.context_expr
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr in ("raises","warns"): return True
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("raises","fail"): return True
    return False
# helpers that assert, across all test files (by name)
for f in files:
    t = ast.parse(open(f).read())
    for n in ast.walk(t):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and has_assert(n):
            asserting_helpers.setdefault(n.name, f)
def calls(node):
    out=set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            fn=n.func
            if isinstance(fn, ast.Name): out.add(fn.id)
            elif isinstance(fn, ast.Attribute): out.add(fn.attr)
    return out
noassert=[]; broad=[]; const=[]; loop_only=[]
for f in files:
    src=open(f).read(); t=ast.parse(src); rel=os.path.relpath(f, root)
    for n in ast.walk(t):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith("test"):
            direct = has_assert(n)
            helpers = calls(n) & set(asserting_helpers)
            if not direct and not helpers:
                noassert.append(f"{rel}:{n.lineno} {n.name}")
            # asserts only inside loops/ifs
            if direct:
                top=[]
                def visit(node, depth_in):
                    for ch in ast.iter_child_nodes(node):
                        inside = depth_in or isinstance(node,(ast.For,ast.AsyncFor,ast.While,ast.If, ast.comprehension))
                        if isinstance(ch, ast.Assert): top.append(inside)
                        if isinstance(ch,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda)): continue
                        visit(ch, inside)
                visit(n, False)
                if top and all(top) and not helpers and not any(isinstance(x,ast.With) for x in ast.walk(n)):
                    loop_only.append(f"{rel}:{n.lineno} {n.name}")
        if isinstance(n, ast.Assert):
            tst=n.test
            if isinstance(tst, ast.Constant) and tst.value: const.append(f"{rel}:{n.lineno} assert {ast.unparse(tst)}")
            if isinstance(tst, ast.BoolOp) and isinstance(tst.op, ast.Or) and any(isinstance(v, ast.Constant) and v.value for v in tst.values):
                const.append(f"{rel}:{n.lineno} assert {ast.unparse(tst)}")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr=="raises":
            if n.args:
                a=ast.unparse(n.args[0])
                has_match=any(k.arg=="match" for k in n.keywords)
                if "Exception" == a or a.startswith("(") and "Exception" in a.split(",")[0] or a in("BaseException","ValueError","TypeError","Exception"):
                    broad.append(f"{rel}:{n.lineno} raises({a}){'' if has_match else ' NO match'}")
print("== tests with no assertion (direct or via a helper that asserts):", len(noassert)); print("\n".join(noassert))
print("== constant asserts:", len(const)); print("\n".join(const))
print("== asserts only inside loop/if:", len(loop_only)); print("\n".join(loop_only))
print("== broad raises:", len(broad)); print("\n".join(broad))
