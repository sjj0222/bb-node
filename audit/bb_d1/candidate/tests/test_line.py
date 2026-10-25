import ast
import os
import subprocess
import sys
import tempfile
import unittest

# make "events.line" importable no matter where the runner is started from:
# the project root of this copy is the parent dir of this tests/ folder.
_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0,_ROOT)

# snapshot of sys.modules taken right before / right after the import of the
# module under test, so we can prove that the import itself pulls nothing in.
_BEFORE_IMPORT=set(sys.modules)
import events.line as L
_AFTER_IMPORT=set(sys.modules)

_FILE=os.path.join(_ROOT,"events","line.py")

# project modules the module under test must never import
_FORBIDDEN_MODULES=(
    "core.log",
    "core.status",
    "core.collector",
    "events.engine_v3",
    "events.group_v3",
    "replay.event_v1",
    "replay.event_v2",
)

# verbatim copy of parse_line() as it exists in HEAD:events/line.py of this
# copy (git -C devcopy show HEAD:events/line.py) - it must not change.
GOLDEN_PARSE_LINE='''def parse_line(s):
    s=str(s).strip().replace(" ","")
    if not s:
        return None
    try:
        if "/" in s:
            a,b=s.split("/",1)
            x=float(a)
            y=float(b)
            if not b.startswith(("+","-")):
                y=-abs(y) if x<0 else abs(y)
            return [x,y]
        return [float(s)]
    except:
        return None'''

# script executed in a fresh interpreter, in an empty temporary directory
_PURITY_SUBPROCESS=(
    "import sys\n"
    "sys.path.insert(0," + repr(_ROOT) + ")\n"
    "import events.line\n"
    "bad=[m for m in " + repr(_FORBIDDEN_MODULES) + " if m in sys.modules]\n"
    "print('FORBIDDEN_MODULES:'+','.join(bad))\n"
    "print('IMPORT_OK')\n"
)


class TestLineCompare(unittest.TestCase):
    # ---------------- AC1: sign flip is detected ----------------

    def test_ac1_sign_flip_is_detected(self):
        for old,new in [
            ("-0.5","+0.5"),
            ("0.5","-0.5"),
            ("-0.25","+0.25"),
            ("-1/1.5","+1/1.5"),
        ]:
            with self.subTest(old=old,new=new):
                r=L.compare_line(old,new)
                self.assertIs(r["changed"],True)

    # ---------------- AC1b: sign flip classification ----------------

    def test_ac1b_sign_flip_is_classified_as_cross_sign_flip(self):
        for old,new in [
            ("-0.5","+0.5"),
            ("0.5","-0.5"),
            ("-0.25","+0.25"),
            ("-1/1.5","+1/1.5"),
        ]:
            with self.subTest(old=old,new=new):
                r=L.compare_line(old,new)
                self.assertEqual(r["direction"],"CROSS")
                self.assertEqual(r["change_type"],"SIGN_FLIP")

    def test_ac1b_sign_flip_steps_equal_quarter_goal_units_of_total_movement(self):
        # hardcoded expectations: the number of quarter goals travelled from
        # the old value to the new one.  No recomputation from the
        # implementation itself, so a wrong implementation cannot pass.
        cases=[
            ("-0.5","+0.5",4.0),      # 0.5 -> 0.5 below/above = 1.0 goal
            ("0.5","-0.5",4.0),       # mirrored
            ("-0.25","+0.25",2.0),    # 0.5 goal
            ("-0.5","+1/1.5",7.0),    # 1.75 goals
            ("-1/1.5","+1/1.5",10.0), # 2.5 goals
        ]
        for old,new,steps in cases:
            with self.subTest(old=old,new=new):
                r=L.compare_line(old,new)
                self.assertIs(r["changed"],True)
                self.assertEqual(r["direction"],"CROSS")
                self.assertEqual(r["change_type"],"SIGN_FLIP")
                self.assertEqual(r["steps"],steps)

    def test_ac1b_sign_flip_steps_concrete_values(self):
        self.assertEqual(L.compare_line("-0.5","+0.5")["steps"],4.0)
        self.assertEqual(L.compare_line("-0.25","+0.25")["steps"],2.0)
        self.assertEqual(L.compare_line("0.5","-0.5")["steps"],4.0)
        self.assertEqual(L.compare_line("-1/1.5","+1/1.5")["steps"],10.0)

    # ---------------- AC2: equivalent spellings stay unchanged ----------------

    def test_ac2_equivalent_spellings_are_unchanged(self):
        for old,new in [
            ("-0.5","-0.50"),
            ("0","0.0"),
            ("-1/1.5","-1.25"),
            ("0/0.5","0/0.50"),
        ]:
            with self.subTest(old=old,new=new):
                r=L.compare_line(old,new)
                self.assertIs(r["changed"],False)
                self.assertEqual(r["direction"],"SAME")
                self.assertEqual(r["change_type"],"SAME")
                self.assertEqual(r["steps"],0)

    def test_ac2b_identical_spellings_are_unchanged(self):
        for old,new in [
            ("-0.5","-0.5"),
            ("0","0"),
            ("-1/1.5","-1/1.5"),
        ]:
            with self.subTest(old=old,new=new):
                r=L.compare_line(old,new)
                self.assertIs(r["changed"],False)
                self.assertEqual(r["direction"],"SAME")
                self.assertEqual(r["change_type"],"SAME")
                self.assertEqual(r["steps"],0)

    # ---------------- AC3: regression, pre-fix classification preserved ----------------

    def test_ac3_regression_magnitude_cases_keep_pre_fix_classification(self):
        cases=[
            ("-0.5","-0.75","DEEPER","QUARTER_STEP",1.0),
            ("-1","-1/1.5","DEEPER","QUARTER_STEP",1.0),
            ("-1/1.5","-1","SHALLOWER","QUARTER_STEP",1.0),
            ("+0.5","+0.25","SHALLOWER","QUARTER_STEP",1.0),
            ("+0.25","+0.5","DEEPER","QUARTER_STEP",1.0),
            ("0","-0.5","DEEPER","HALF_STEP",2.0),
            ("-0.5","0","SHALLOWER","HALF_STEP",2.0),
            ("0.5","0/0.5","SHALLOWER","QUARTER_STEP",1.0),
            ("0/0.5","0.5","DEEPER","QUARTER_STEP",1.0),
            ("1","1/1.5","DEEPER","QUARTER_STEP",1.0),
            ("1/1.5","1","SHALLOWER","QUARTER_STEP",1.0),
        ]
        for old,new,direction,change_type,steps in cases:
            with self.subTest(old=old,new=new):
                r=L.compare_line(old,new)
                self.assertIs(r["changed"],True)
                self.assertEqual(r["direction"],direction)
                self.assertEqual(r["change_type"],change_type)
                self.assertEqual(r["steps"],steps)

    def test_ac3_zero_is_neutral_and_is_not_a_sign_flip(self):
        # 0 -> -0.5 and -0.5 -> 0 keep the old magnitude classification
        r=L.compare_line("0","-0.5")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"DEEPER")
        self.assertEqual(r["change_type"],"HALF_STEP")
        self.assertEqual(r["steps"],2.0)

        r=L.compare_line("-0.5","0")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"SHALLOWER")
        self.assertEqual(r["change_type"],"HALF_STEP")
        self.assertEqual(r["steps"],2.0)

    def test_ac3b_legacy_multi_step_classification_is_preserved(self):
        # ground truth taken from the ORIGINAL implementation
        # (git -C devcopy show HEAD:events/line.py):
        #   compare_line("-0.5","-1.25") -> DEEPER / MULTI_STEP / 3.0
        # (depth 0.5 -> 1.25, difference 0.75 = 3 quarter goals)
        r=L.compare_line("-0.5","-1.25")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"DEEPER")
        self.assertEqual(r["change_type"],"MULTI_STEP")
        self.assertEqual(r["steps"],3.0)

    # ---------------- AC4: unparsable input ----------------

    def test_ac4_unparsable_input_returns_unknown(self):
        for old,new in [
            ("abc","-0.5"),       # old side unparsable
            (None,"-0.5"),
            ("",""),
            ("-0.5","abc"),       # new side unparsable
            ("-0.5",None),
            ("-0.5",""),
        ]:
            with self.subTest(old=old,new=new):
                r=L.compare_line(old,new)
                self.assertIs(r["changed"],None)
                self.assertEqual(r["direction"],"UNKNOWN")
                self.assertEqual(r["change_type"],"UNKNOWN")
                self.assertIs(r["steps"],None)

    # ---------------- AC5: norm() purity ----------------

    def test_ac5_norm_keeps_raw_legs_and_depth_unchanged(self):
        n=L.norm("-1/1.5")
        self.assertEqual(n["raw"],"-1/1.5")
        self.assertEqual(n["legs"],[-1.0,-1.5])
        self.assertEqual(n["depth"],1.25)

        n=L.norm("-0.5")
        self.assertEqual(n["raw"],"-0.5")
        self.assertEqual(n["legs"],[-0.5])
        self.assertEqual(n["depth"],0.5)

        n=L.norm("0")
        self.assertEqual(n["raw"],"0")
        self.assertEqual(n["legs"],[0.0])
        self.assertEqual(n["depth"],0.0)

        n=L.norm("0/0.5")
        self.assertEqual(n["raw"],"0/0.5")
        self.assertEqual(n["legs"],[0.0,0.5])
        self.assertEqual(n["depth"],0.25)

        n=L.norm("+1/1.5")
        self.assertEqual(n["raw"],"+1/1.5")
        self.assertEqual(n["legs"],[1.0,1.5])
        self.assertEqual(n["depth"],1.25)

    def test_ac5_norm_exposes_signed_value_additively(self):
        self.assertEqual(L.norm("-1/1.5")["value"],-1.25)
        self.assertEqual(L.norm("+1/1.5")["value"],1.25)
        self.assertEqual(L.norm("-0.5")["value"],-0.5)
        self.assertEqual(L.norm("+0.5")["value"],0.5)
        self.assertEqual(L.norm("0")["value"],0.0)
        self.assertEqual(L.norm("0/0.5")["value"],0.25)
        self.assertIsNone(L.norm("abc"))

    def test_ac5_norm_value_keeps_full_float_precision(self):
        # the signed value must not be rounded away: a tiny value has to
        # stay visible (only the 1e-9 equality tolerance may absorb noise)
        self.assertEqual(L.norm("-0.00001")["value"],-0.00001)
        self.assertEqual(L.norm("+0.00001")["value"],0.00001)
        self.assertNotEqual(L.norm("-0.00001")["value"],0.0)
        self.assertNotEqual(L.norm("+0.00001")["value"],0.0)
        self.assertEqual(L.norm("0")["value"],0.0)

    def test_ac5_parse_line_is_untouched(self):
        # real source-identity check: the current parse_line() must be
        # byte-for-byte the one of HEAD:events/line.py
        with open(_FILE,encoding="utf-8") as fh:
            src=fh.read()
        tree=ast.parse(src)
        fn=next(n for n in tree.body
                if isinstance(n,ast.FunctionDef) and n.name=="parse_line")
        current=ast.get_source_segment(src,fn)
        self.assertIsNotNone(current)
        self.assertEqual(current.rstrip(),GOLDEN_PARSE_LINE.rstrip())

        # behavioural assertions
        self.assertEqual(L.parse_line("-0.5"),[-0.5])
        self.assertEqual(L.parse_line("-1/1.5"),[-1.0,-1.5])
        self.assertEqual(L.parse_line("0/0.5"),[0.0,0.5])
        self.assertIsNone(L.parse_line("abc"))
        self.assertIsNone(L.parse_line(""))

    def test_ac5_import_pulls_no_project_modules_and_no_io_modules(self):
        # (a) importing events.line must not drag in any project module
        for name in _FORBIDDEN_MODULES:
            with self.subTest(module=name):
                self.assertNotIn(name,sys.modules)
                self.assertNotIn(name,_AFTER_IMPORT)
        # ... and must not have added them either
        self.assertEqual(
            sorted(_AFTER_IMPORT-_BEFORE_IMPORT),
            sorted(set(_AFTER_IMPORT-_BEFORE_IMPORT)-set(_FORBIDDEN_MODULES)))

        # sqlite3/socket may legitimately live in sys.modules (the test
        # runner itself imported them), so the module object is checked
        # instead: it must not reference any of them
        for name in ("sqlite3","socket","os","requests"):
            with self.subTest(module=name):
                self.assertNotIn(name,L.__dict__)

    def test_ac5_import_creates_no_file_in_a_fresh_directory(self):
        # (b) a fresh interpreter, run in an empty temporary directory,
        #     must be able to import events.line without creating anything
        try:
            tmp=tempfile.TemporaryDirectory()
        except OSError as exc:
            self.skipTest("no usable temporary directory here: %r"%exc)
        with tmp:
            env=dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"]="1"
            try:
                proc=subprocess.run(
                    [sys.executable,"-c",_PURITY_SUBPROCESS],
                    cwd=tmp.name,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    timeout=120)
            except OSError as exc:
                self.skipTest("cannot launch a subprocess here: %r"%exc)
            self.assertEqual(proc.returncode,0,
                "subprocess failed:\n%s"%proc.stderr)
            self.assertNotIn("Traceback",proc.stderr)
            self.assertIn("IMPORT_OK",proc.stdout)
            self.assertIn("FORBIDDEN_MODULES:",proc.stdout)
            forbidden=proc.stdout.split("FORBIDDEN_MODULES:",1)[1]
            forbidden=forbidden.split("\n",1)[0].strip()
            self.assertEqual(forbidden,"",
                "importing events.line pulled in: %s"%forbidden)
            self.assertEqual(os.listdir(tmp.name),[],
                "importing events.line created files: %r"%os.listdir(tmp.name))

    # ---------------- boundary cases ----------------

    def test_boundary_whitespace_and_explicit_plus_zero(self):
        r=L.compare_line(" -0.5 ","-0.5")
        self.assertIs(r["changed"],False)
        self.assertEqual(r["direction"],"SAME")
        self.assertEqual(r["change_type"],"SAME")
        self.assertEqual(r["steps"],0)

        r=L.compare_line("0","+0")
        self.assertIs(r["changed"],False)
        self.assertEqual(r["direction"],"SAME")
        self.assertEqual(r["change_type"],"SAME")
        self.assertEqual(r["steps"],0)

    def test_boundary_zero_to_plus_half_is_not_a_sign_flip(self):
        # a value of exactly 0 is neutral: it never counts as a sign flip,
        # so "0" -> "+0.5" keeps the plain magnitude classification
        r=L.compare_line("0","+0.5")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"DEEPER")
        self.assertEqual(r["change_type"],"HALF_STEP")
        self.assertEqual(r["steps"],2.0)

    def test_boundary_sign_flip_across_asymmetric_depths_is_cross(self):
        # different depths but opposite signs -> still a money crossing
        r=L.compare_line("-0.5","+1/1.5")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"CROSS")
        self.assertEqual(r["change_type"],"SIGN_FLIP")
        self.assertEqual(r["steps"],7.0)

    def test_boundary_depth_equality_is_exact_like_the_original(self):
        # the original implementation compared the depth with "==", so a
        # 1e-9 depth difference is still a change (ground truth from
        # HEAD:events/line.py: DEEPER / MULTI_STEP / 3.999999886872274e-09)
        r=L.compare_line("0.5","0.500000001")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"DEEPER")
        self.assertEqual(r["change_type"],"MULTI_STEP")
        self.assertEqual(r["steps"],3.999999886872274e-09)

    def test_boundary_sub_eps_values_are_neutral(self):
        # a value inside the 1e-9 neutral band carries no polarity: it must
        # not be reported as a sign flip (that would end up with steps=0.0)
        r=L.compare_line("-1e-12","+2e-12")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"DEEPER")
        self.assertEqual(r["change_type"],"MULTI_STEP")
        self.assertNotEqual(r["steps"],0.0)

        # equal sub-EPS values: unchanged (the 1e-9 tolerance absorbs them)
        r=L.compare_line("-1e-12","+1e-12")
        self.assertIs(r["changed"],False)
        self.assertEqual(r["direction"],"SAME")
        self.assertEqual(r["change_type"],"SAME")
        self.assertEqual(r["steps"],0)

        # the neutral band is the only reason for that: a value clearly
        # outside of it (1e-5) does flip
        r=L.compare_line("-1e-5","+1e-5")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"CROSS")
        self.assertEqual(r["change_type"],"SIGN_FLIP")

    def test_boundary_tiny_sign_crossing_is_detected(self):
        # a crossing below 5e-5 must still be visible, and its step count
        # must not collapse to 0.0
        r=L.compare_line("-0.00001","+0.00001")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"CROSS")
        self.assertEqual(r["change_type"],"SIGN_FLIP")
        self.assertNotEqual(r["steps"],0.0)
        self.assertAlmostEqual(r["steps"],0.0001,places=9)

        r=L.compare_line("-0.0001","+0.0001")
        self.assertIs(r["changed"],True)
        self.assertEqual(r["direction"],"CROSS")
        self.assertEqual(r["change_type"],"SIGN_FLIP")
        self.assertNotEqual(r["steps"],0.0)
        self.assertAlmostEqual(r["steps"],0.0008,places=9)

    # ---------------- guard: the module under test is the devcopy one ----------------

    def test_module_under_test_is_this_devcopy(self):
        self.assertEqual(
            os.path.dirname(os.path.dirname(os.path.abspath(L.__file__))),
            _ROOT)


if __name__=="__main__":
    unittest.main()
