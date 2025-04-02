import json
import difflib
import sys

def compare_json_files(baseline_path, new_path):
    with open(baseline_path) as base_file, open(new_path) as new_file:
        base_data = json.load(base_file)
        new_data = json.load(new_file)

        base_text = json.dumps(base_data, indent=2, sort_keys=True)
        new_text = json.dumps(new_data, indent=2, sort_keys=True)

        diff = list(difflib.unified_diff(
            base_text.splitlines(), new_text.splitlines(),
            lineterm="", fromfile="Baseline", tofile="New Report"
        ))

        return "\n".join(diff)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 compare_dbsat.py <baseline.json> <new_report.json>")
        sys.exit(1)

    baseline = sys.argv[1]
    new_report = sys.argv[2]

    changes = compare_json_files(baseline, new_report)
    if changes:
        print("Configuration Drift Detected:\n" + changes)
    else:
        print("No Drift Detected")
