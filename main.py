from pathlib import Path
from orchestrator.pipeline import Pipeline
from services.output_writer import write_json, write_markdown


def main() -> None:
    print("=== AI QA Orchestrator ===\n")
    print("Paste your requirement text. Enter a blank line when done:")

    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)

    raw_input = "\n".join(lines).strip()
    if not raw_input:
        print("No input provided. Exiting.")
        return

    pipeline = Pipeline()
    session = pipeline.run(raw_input)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    write_json(session.test_cases, output_dir / "test_cases.json")
    write_markdown(session.test_cases, output_dir / "test_cases.md")

    print(f"\nDone. {len(session.test_cases)} test case(s) written to {output_dir}/")


if __name__ == "__main__":
    main()
