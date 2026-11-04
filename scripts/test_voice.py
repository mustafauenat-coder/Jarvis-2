import argparse
from pathlib import Path

from app.storage import data_dir
from app.voice import LocalVoice


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="jarvis-test.wav")
    args = parser.parse_args()
    output = Path(args.output)
    output.write_bytes(LocalVoice(data_dir()).synthesize("Jarvis ist online."))
    print("WAV erzeugt:", output.resolve())


if __name__ == "__main__":
    main()
