import argparse
import sys
from pydantic import ValidationError
from .lib import import_model, load_data


def main():
    parser = argparse.ArgumentParser(
        description="Validate YAML/JSON against a Pydantic model."
    )
    parser.add_argument(
        "model", help="Model location: <file.py>:<Model> or <module.path>:<Model>"
    )
    parser.add_argument("input", help="Input YAML or JSON file to validate")
    args = parser.parse_args()

    try:
        model_class = import_model(args.model)
    except Exception as e:
        print(f"Error importing model: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        data = load_data(args.input)
    except Exception as e:
        print(f"Error loading input file: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        model_instance = model_class(**data)
        print("Validation successful! Data conforms to the model.")
    except ValidationError as ve:
        print("Validation failed:")
        print(ve.json())
        sys.exit(2)


if __name__ == "__main__":
    main()
