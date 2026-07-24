"""
verify.py - prove the web version still matches the desktop version.

Run this after any change to the server, after a Python or pandas upgrade,
and after adding a vessel. It compares every run in the document: text,
font size, bold, underline and POD colour.

    python verify.py loading_list.csv "CONTSHIP VOW" reference_from_exe.docx

Exit code 0 means identical. Anything else means something moved.
"""
import io
import sys
import contextlib

import pandas as pd
from docx import Document

from core import ListLogic


def fingerprint(source):
    """Every run in the document, with the formatting that matters."""
    doc = Document(source)
    runs = []
    for para in doc.paragraphs:
        for run in para.runs:
            colour = (run.font.color.rgb
                      if run.font.color and run.font.color.type is not None
                      else None)
            runs.append((run.text, run.font.size, run.bold,
                         run.underline, str(colour)))
    return runs


def title_of(path):
    """
    The heading the reference actually prints, taken from the document.

    Don't derive it from the file name - a file called 4743_CONTSHIP_VOW.docx
    may well have been generated with the name "4743 CONTSHIP VOW", and the
    underscores would show up as a false difference.
    """
    for para in Document(path).paragraphs:
        text = "".join(r.text for r in para.runs).strip()
        if text:
            return text
    return "List"


def main(csv_path, vessel, reference):
    heading = title_of(reference)
    df = pd.read_csv(csv_path, engine="python")
    with contextlib.redirect_stdout(io.StringIO()):
        ListLogic().generateWordDoc(df, vessel, "_verify.docx",
                                    heading + ".docx")

    ours = fingerprint("_verify.docx")
    theirs = fingerprint(reference)

    print(f"vessel     : {vessel}")
    print(f"rows in CSV: {len(df)}")
    print(f"runs ours  : {len(ours)}")
    print(f"runs ref   : {len(theirs)}")

    if ours == theirs:
        print("\nIDENTICAL - the web version reproduces the desktop output.")
        return 0

    print("\nDIFFERENCES FOUND:")
    for i, (a, b) in enumerate(zip(ours, theirs)):
        if a != b:
            print(f"  run {i}\n    ours: {a}\n    ref : {b}")
    if len(ours) != len(theirs):
        print(f"  run count differs: {len(ours)} vs {len(theirs)}")
    print("\nIf the reference was opened in Word before you saved it, the "
          "differences are probably your own edits, not a fault.")
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
