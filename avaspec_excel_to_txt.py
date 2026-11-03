#!/usr/bin/env python3
"""
AvaSpec Excel to Text Converter

Converts AvaSpec Excel exports (.xlsx, .xls) to tab-separated TXT files for kinetics analysis:
- Column 1 (Time): Excel column B (milliseconds) divided by 1000
- Column 2 (Absorbance): Excel column C, decimal commas converted to dots

Usage: python avaspec_excel_to_txt.py [folder]   (default: the current folder)
"""

import random
import sys
from pathlib import Path

import pandas as pd

import kinetics_core

DATA_START_ROW = 4  # 1-indexed Excel row where the data begins


def process_excel_file(file_path: Path) -> None:
    """Convert one AvaSpec Excel file to a TXT file next to it."""
    print(f"-> Processing file: {file_path.name}")
    try:
        raw = pd.read_excel(file_path, sheet_name=0, skiprows=DATA_START_ROW - 1, header=None)
        if raw.empty or len(raw.columns) < 3:
            print(f"   ERROR: {file_path.name} doesn't have enough columns or is empty. Skipping.")
            return
        data = kinetics_core.parse_avaspec_rows(raw)
        if data.empty:
            print(f"   WARNING: No valid data found in {file_path.name}")
            return
        output_path = file_path.with_suffix('.txt')
        output_path.write_text(kinetics_core.avaspec_txt(data, file_path.name, experiment_date=raw.iloc[0, 0]),
                               encoding='utf-8')
        print(f"   Created: {output_path.name} ({len(data)} data points)")
    except Exception as error:
        print(f"   ERROR processing {file_path.name}: {error}")


def ask_choice(excel_files: list) -> str:
    """Return 'all', 'quit' or a valid file number as text."""
    print("\nAvailable Excel files:")
    for number, file in enumerate(excel_files, 1):
        print(f"  {number}. {file.name}")
    print(f"\nOptions: 'all', a number (1-{len(excel_files)}), or 'quit'")
    while True:
        choice = input("\nYour choice: ").strip().lower()
        if choice in ('all', 'quit') or (choice.isdigit() and 1 <= int(choice) <= len(excel_files)):
            return choice
        print(f"Please enter a number between 1 and {len(excel_files)}, 'all', or 'quit'.")


def pause() -> None:
    try:
        input("\nPress Enter to exit...")
    except EOFError:  # not running interactively
        pass


def main() -> None:
    print("================================================")
    print("     AvaSpec Excel to Text Converter")
    print("================================================")
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print(f"Scanning for Excel files in: {folder.resolve()}")
    excel_files = sorted([*folder.glob('*.xlsx'), *folder.glob('*.xls')])
    if not excel_files:
        print("\nNo Excel files found in the directory.")
        return pause()

    choice = ask_choice(excel_files)
    if choice == 'quit':
        print("\nExiting...")
        return
    print("\n" + "=" * 50 + "\nStarting processing...\n" + "=" * 50)
    for excel_file in excel_files if choice == 'all' else [excel_files[int(choice) - 1]]:
        process_excel_file(excel_file)
    print("\n" + "-" * 50 + "\nProcessing complete!\nText files have been created in the same folder.")
    print(f"\n💭 \"{random.choice(kinetics_core.QUOTES)}\"")
    pause()


if __name__ == "__main__":
    main()
