"""Check an agent's explanation against the verdict JSON: every number in the text is in the JSON, and the verdict matches.

Usage: python eval/check_agent_text.py <verdict.json> <answer.txt> [<request.json>]
The optional request holds the tool-call arguments; numbers from it (e.g. the offline day) also count as known.
"""
import json
import re
import sys
from pathlib import Path

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![\w.,])\d+(?:\.\d+)?%?")
LABELS = [
    (re.compile(r"\bnot[ _]enough[ _]data\b", re.I), "not_enough_data"),
    (re.compile(r"\bconfirmed\b", re.I), "confirmed"),
    (re.compile(r"\bearly\b", re.I), "early"),
    (re.compile(r"\btie\b", re.I), "tie"),
]


def _walk(value, numbers: list[float], strings: list[str]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        numbers.append(float(value))
    elif isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _walk(item, numbers, strings)
    elif isinstance(value, list):
        for item in value:
            _walk(item, numbers, strings)


def _parse(piece: str) -> tuple[float, int]:
    digits = piece.rstrip("%").replace(",", "")
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    return float(digits), decimals


def _known(verdict: dict) -> tuple[list[float], set[str]]:
    numbers, strings = [], []
    _walk(verdict, numbers, strings)
    dates = {d for s in strings for d in DATE.findall(s)}
    for s in strings:
        numbers += [_parse(t)[0] for t in NUMBER.findall(DATE.sub(" ", s))]
    return numbers, dates


def _matches(piece: str, numbers: list[float]) -> bool:
    shown, decimals = _parse(piece)
    tolerance = 0.5 * 10 ** -decimals + 1e-9
    candidates = [abs(n) for n in numbers] + [abs(n) * 100 for n in numbers]
    return any(abs(c - shown) <= tolerance for c in candidates)


def stated_verdict(text: str) -> str | None:
    bold = " ".join(re.findall(r"\*\*(.+?)\*\*", text))
    for source in (bold, text):
        hits = [(m.start(), label) for pattern, label in LABELS for m in pattern.finditer(source)]
        if hits:
            return min(hits)[1]
    return None


def check(verdict: dict, text: str, request: dict | None = None) -> dict:
    numbers, dates = _known({"verdict": verdict, "request": request or {}})
    unmatched = [d for d in DATE.findall(text) if d not in dates]
    found = NUMBER.findall(DATE.sub(" ", text))
    unmatched += [t for t in found if not _matches(t, numbers)]
    stated = stated_verdict(text)
    verdict_ok = stated == verdict.get("verdict")
    return {
        "numbers_checked": len(found) + len(DATE.findall(text)),
        "unmatched": unmatched,
        "verdict_expected": verdict.get("verdict"),
        "verdict_stated": stated,
        "verdict_ok": verdict_ok,
        "passed": verdict_ok and not unmatched,
    }


def check_files(json_path: Path, text_path: Path, request_path: Path | None = None) -> dict:
    request = json.loads(Path(request_path).read_text()) if request_path else None
    return check(json.loads(Path(json_path).read_text()), Path(text_path).read_text(), request)


if __name__ == "__main__":
    result = check_files(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]) if len(sys.argv) > 3 else None)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
