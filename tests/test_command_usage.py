"""Unified usage drift without launching one interpreter per help page."""
import argparse
import re
from pathlib import Path
import unittest
import recap

ROOT = Path(__file__).resolve().parents[1]


class CommandUsageTests(unittest.TestCase):
    def test_all_unified_usage_lines_match_current_parser(self):
        parser = recap.build_parser()
        # argparse exposes no public subparser iterator; inspect actions solely
        # for documentation checks, not dispatch. Canonical prog and color-off
        # avoid interpreter-launcher and Python 3.14 terminal differences.
        choices = next(action.choices for action in parser._actions
                       if isinstance(action, argparse._SubParsersAction))
        parsers = {'': parser, **choices}
        expected = {}
        for name, value in parsers.items():
            value.prog = 'recap.py' + (' ' + name if name else '')
            if hasattr(value, 'color'):
                value.color = False
            expected[name] = ' '.join(value.format_usage().split())
        text = (ROOT/'docs/COMMANDS.md').read_text(encoding='utf-8')
        observed = {}
        for line in re.findall(r'^usage: recap\.py[^\n]*', text, re.M):
            parts = line.split()
            name = parts[2] if parts[2] in choices else ''
            self.assertNotIn(name, observed)
            observed[name] = ' '.join(line.split())
        self.assertEqual(observed, expected)


if __name__ == '__main__':
    unittest.main()
