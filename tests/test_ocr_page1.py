import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from mcc.preprocess.ocr import ocr_columns


class TestOcrPage1(unittest.TestCase):
    def test_page1_columns(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        in_dir = repo_root / "pre" / "columns"
        if not in_dir.exists():
            self.skipTest("Missing out/columns; run segment step first.")
        required = [in_dir / f"page-0001-col-{idx}.png" for idx in range(1, 6)]
        if any(not path.exists() for path in required):
            self.skipTest("Missing page-0001 column images in out/columns.")
        if shutil.which("tesseract") is None:
            self.skipTest("Missing tesseract binary.")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            try:
                ocr_columns(
                    in_dir=in_dir,
                    out_dir=out_dir,
                    start_page=1,
                    end_page=1,
                    lang="chi_sim+eng",
                    psm=6,
                    oem=None,
                    tessdata_dir=None,
                    skip_existing=False,
                    no_progress=True,
                )
            except SystemExit as exc:
                message = str(exc)
                if (
                    "Missing dependency tesseract" in message
                    or "Missing Tesseract" in message
                ):
                    self.skipTest(message)
                raise

            total_rows = 0
            matched_rows = 0
            for idx in range(1, 6):
                expected_path = (
                    repo_root / "tests" / "data" / f"page-0001-col-{idx}.csv"
                )
                actual_path = out_dir / f"page-0001-col-{idx}.csv"
                self.assertTrue(
                    actual_path.exists(), f"Missing OCR output {actual_path}"
                )
                with expected_path.open(
                    "r", encoding="utf-8", newline=""
                ) as expected_file:
                    expected_rows = list(csv.reader(expected_file))
                with actual_path.open("r", encoding="utf-8", newline="") as actual_file:
                    actual_rows = list(csv.reader(actual_file))
                self.assertEqual(
                    len(expected_rows),
                    len(actual_rows),
                    f"Row count mismatch for {actual_path}",
                )
                total_rows += len(expected_rows)
                matched_rows += sum(
                    1
                    for expected, actual in zip(expected_rows, actual_rows)
                    if expected == actual
                )

            min_accuracy = 0.98
            accuracy = matched_rows / total_rows if total_rows else 0.0
            self.assertGreaterEqual(
                accuracy,
                min_accuracy,
                f"Accuracy {accuracy:.2%} below threshold {min_accuracy:.2%}",
            )


if __name__ == "__main__":
    unittest.main()
