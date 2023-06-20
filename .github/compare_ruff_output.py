"""Compare ruff output and complain when number of violations increases."""

import json
import logging
from pathlib import Path

ParsedResult = dict[tuple[str, str], tuple[int, str]]
Comparison = dict[tuple[str, str], tuple[int, int, str]]

logging.basicConfig(format="%(levelname)s: %(message)s")


def parse_results(filename: Path) -> ParsedResult:
    """Read json and generate statistics."""
    parsed_results: ParsedResult = {}
    for violation in json.loads(filename.read_text()):
        key = (violation["filename"].replace(r"\.tox\reference", ""), violation["code"])
        count = parsed_results.get(key, (0, ""))[0] + 1
        parsed_results[key] = (count, violation["message"])
    return parsed_results


def compare_results(*, result: ParsedResult, reference: ParsedResult) -> Comparison:
    """Compare two ruff results and generate a report.

    Read two results from ruff, one from the actual code and one from the reference and compare them.
    If there is any violation on a per file and per rule basis where the number of violations increased,
    this will be part of the return value.


    Returns:
        A dictionary mapping from the key which is a tuple of filename and rule code to a tuple consisting of
        the reference violations, the actual violations, and the rule message.
    """
    comparison: Comparison = {}
    for key, violation_details in result.items():
        violations = violation_details[0]
        reference_violations = reference.get(key, (0, ""))[0]
        message = violation_details[1]
        if violations > reference_violations:
            comparison[key] = (reference_violations, violations, message)
    return comparison


def output_violations(comparison: Comparison) -> bool:
    """Print output and return if everything is ok."""
    for key, violation_details in comparison.items():
        logging.error(
            f"Violations increased from {violation_details[0]} to {violation_details[1]} "
            f"for rule {key[1]} [{violation_details[2]}] in file '{key[0]}'.",
        )
    if len(comparison) > 0:
        return False
    return True


result = parse_results(Path("ruff.json"))
reference = parse_results(Path("ref.json"))

comparison = compare_results(result=result, reference=reference)
if output_violations(comparison) is False:
    exc_msg = {"Code quality regression detected."}
    print(f"::error::{exc_msg}")  # noqa: T201
    raise ValueError(exc_msg)
