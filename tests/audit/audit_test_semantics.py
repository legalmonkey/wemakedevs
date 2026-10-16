"""Audit Check 2.7: Semantic analysis of every test file.
For each test file:
1. State what each test asserts.
2. Flag tests that assert nothing meaningful, assert against their own fixtures, or mock the thing under test.
"""
import ast
import inspect
import importlib
from pathlib import Path

def analyze_tests():
    test_files = sorted(list(Path("tests").glob("test_*.py")) + list(Path("tests/part_c").glob("test_*.py")))
    
    findings = []
    summary = []
    
    for tf in test_files:
        content = tf.read_text(encoding="utf-8")
        tree = ast.parse(content)
        
        file_summary = {"file": str(tf), "tests": []}
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                test_name = node.name
                docstring = ast.get_docstring(node) or "No docstring"
                
                assert_nodes = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
                assert_count = len(assert_nodes)
                
                # Check for mock usage
                has_mock = any(
                    isinstance(n, ast.Name) and "mock" in n.id.lower() 
                    or isinstance(n, ast.Attribute) and "mock" in n.attr.lower()
                    for n in ast.walk(node)
                )
                
                # Check for trivial assertions like assert True, assert x is not None only
                trivial_asserts = 0
                for a in assert_nodes:
                    if isinstance(a.test, ast.Constant) and a.test.value is True:
                        trivial_asserts += 1
                
                # Check if test asserts against self-fixtures or tautologies
                tautology = False
                for a in assert_nodes:
                    if isinstance(a.test, ast.Compare):
                        left = ast.unparse(a.test.left)
                        for comparator in a.test.comparators:
                            if left == ast.unparse(comparator):
                                tautology = True
                
                flag = []
                if assert_count == 0:
                    flag.append("ZERO_ASSERTS")
                if tautology:
                    flag.append("TAUTOLOGY_ASSERTION")
                if has_mock:
                    flag.append("USES_MOCK")
                if trivial_asserts > 0 and assert_count == trivial_asserts:
                    flag.append("ONLY_TRIVIAL_ASSERTS")
                    
                assertion_descriptions = []
                for a in assert_nodes[:3]:
                    try:
                        assertion_descriptions.append(ast.unparse(a.test))
                    except Exception:
                        pass
                
                file_summary["tests"].append({
                    "name": test_name,
                    "doc": docstring.strip().splitlines()[0] if docstring else "",
                    "assert_count": assert_count,
                    "flags": flag,
                    "sample_asserts": assertion_descriptions
                })
        summary.append(file_summary)
        
    return summary

def main():
    results = analyze_tests()
    print("=" * 80)
    print("AUDIT CHECK 2.7: COMPREHENSIVE TEST SUITE SEMANTIC AUDIT")
    print("=" * 80)
    
    total_tests = sum(len(f["tests"]) for f in results)
    flagged_tests = []
    
    for f in results:
        print(f"\nFILE: {f['file']} ({len(f['tests'])} tests)")
        for t in f["tests"]:
            flag_str = f" [FLAG: {', '.join(t['flags'])}]" if t['flags'] else ""
            print(f"  * {t['name']}: {t['assert_count']} assertions{flag_str}")
            print(f"    Intent: {t['doc']}")
            for sa in t["sample_asserts"]:
                print(f"      assert: {sa[:75]}")
            if t["flags"]:
                flagged_tests.append((f["file"], t["name"], t["flags"]))
                
    print("\n" + "=" * 80)
    print(f"SUMMARY: Inspected {len(results)} files, {total_tests} test cases.")
    print(f"Flagged tests: {len(flagged_tests)}")
    for f, t, flags in flagged_tests:
        print(f"  - {f} :: {t} -> {flags}")
    print("=" * 80)

def test_semantic_analysis_of_tests():
    main()


if __name__ == "__main__":
    main()
