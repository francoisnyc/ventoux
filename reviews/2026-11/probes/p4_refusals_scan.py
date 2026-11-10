# Lists each raise in src/ whose constant message text appears in no test and no guide (usage: python3 p4_refusals_scan.py <repository root>; a scan, candidates only).
"""Lists each refusal message in src/ (a raise, or a returned/appended refusal string) whose constant text appears nowhere in tests/ or docs/guides tested."""
import ast, glob, os, sys, re
root=sys.argv[1]
tests="".join(open(f).read() for f in glob.glob(os.path.join(root,"tests","**","*.py"),recursive=True))
tests+= "".join(open(f).read() for f in glob.glob(os.path.join(root,"tests","**","*.json"),recursive=True)); tests+="".join(open(f).read() for f in glob.glob(os.path.join(root,"docs","guides","*.md")))
tests_norm=re.sub(r'"\s*\n\s*(f?)"', "", tests)  # join implicit string concatenations roughly
def frags(node):
    out=[]
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value,str): out.append(n.value)
    return out
missing=[]; total=0
for f in sorted(glob.glob(os.path.join(root,"src","ventoux","**","*.py"),recursive=True)):
    t=ast.parse(open(f).read())
    for n in ast.walk(t):
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and n.exc.args:
            arg=n.exc.args[0]
            fs=[x.strip() for x in frags(arg) if len(x.strip())>=14]
            if not fs: continue
            total+=1
            best=max(fs,key=len)
            # a fragment found in tests (also check smaller fragments)
            if not any(x in tests or x in tests_norm for x in fs):
                missing.append(f"{os.path.relpath(f,root)}:{n.lineno} {type(n.exc.func).__name__=='Name' and n.exc.func.id or ast.unparse(n.exc.func)}: {best[:110]!r}")
print(f"refusals with a constant message: {total}; none of whose fragments appear in tests: {len(missing)}")
print("\n".join(missing))
