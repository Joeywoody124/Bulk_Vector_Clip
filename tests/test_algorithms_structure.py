"""Structural checks on the algorithm files.

These cannot import the modules - that needs QGIS - so they read the source
with ``ast`` instead. Crude, but it catches the failures that are otherwise
invisible until QGIS silently drops a tool from the toolbox: a duplicate
algorithm id, a missing ``createInstance``, or a tool that was written but
never added to the provider.
"""

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALGS_DIR = os.path.join(ROOT, "fieldkit", "algs")

REQUIRED_METHODS = {
    "initAlgorithm",
    "processAlgorithm",
    "name",
    "displayName",
    "group",
    "groupId",
    "shortHelpString",
    "createInstance",
}


def algorithm_classes():
    """Every QgsProcessingAlgorithm subclass in fieldkit/algs, by file."""
    found = []
    for filename in sorted(os.listdir(ALGS_DIR)):
        if not filename.endswith(".py") or filename.startswith("__"):
            continue
        path = os.path.join(ALGS_DIR, filename)
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "QgsProcessingAlgorithm" in bases:
                found.append((filename, node))
    return found


def returned_string(class_node, method_name):
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            for statement in ast.walk(node):
                if isinstance(statement, ast.Return) and isinstance(
                    statement.value, ast.Constant
                ):
                    return statement.value.value
    return None


class AlgorithmStructureTest(unittest.TestCase):
    def setUp(self):
        self.classes = algorithm_classes()

    def test_there_are_algorithms(self):
        self.assertGreaterEqual(len(self.classes), 7)

    def test_every_algorithm_implements_the_required_methods(self):
        for filename, node in self.classes:
            defined = {
                child.name for child in node.body
                if isinstance(child, ast.FunctionDef)
            }
            missing = REQUIRED_METHODS - defined
            self.assertFalse(
                missing,
                "%s.%s is missing %s" % (filename, node.name, sorted(missing)),
            )

    def test_algorithm_ids_are_unique_and_toolbox_safe(self):
        seen = {}
        for filename, node in self.classes:
            identifier = returned_string(node, "name")
            self.assertIsNotNone(
                identifier, "%s.%s has no literal name()" % (filename, node.name))
            self.assertNotIn(
                identifier, seen,
                "id %r used by both %s and %s"
                % (identifier, seen.get(identifier), filename))
            self.assertTrue(
                identifier.islower() and identifier.isalnum(),
                "id %r in %s should be lowercase alphanumeric" % (identifier, filename))
            seen[identifier] = filename

    def test_groups_are_from_the_known_set(self):
        for filename, node in self.classes:
            group = returned_string(node, "groupId")
            self.assertIn(group, {"editing", "sheets", "bulk"},
                          "%s uses an unexpected group %r" % (filename, group))

    def test_help_is_not_a_stub(self):
        for filename, node in self.classes:
            help_text = returned_string(node, "shortHelpString")
            # Implicitly-concatenated strings parse as one Constant only when
            # they are a single literal; a joined help string shows up as a
            # BinOp or JoinedStr, which is fine - just skip the length check.
            if help_text is not None:
                self.assertGreater(
                    len(help_text), 80,
                    "%s.%s has a stub help string" % (filename, node.name))

    def test_provider_registers_every_algorithm(self):
        with open(os.path.join(ROOT, "fieldkit", "provider.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read(), "provider.py")
        registered = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "ALGORITHMS" for t in node.targets
            ):
                registered = {
                    element.id for element in node.value.elts
                    if isinstance(element, ast.Name)
                }
        self.assertTrue(registered, "provider.py has no ALGORITHMS list")
        self.assertEqual(
            registered,
            {node.name for _, node in self.classes},
            "provider.py and fieldkit/algs disagree about which tools exist",
        )


if __name__ == "__main__":
    unittest.main()
