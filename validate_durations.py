import os
import sys
import subprocess
import argparse
from common import *
from metadata_handler import get_effective_index, get_alias_for_index

# Tolerance in seconds for duration comparison
DURATION_TOLERANCE = 1

def get_video_duration(filepath):
    """Return duration of video file in seconds using ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        filepath
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                         universal_newlines=True)
        return float(output.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print_colored(f"Error getting duration for {filepath}: {e}",
                      "validate", ColorsEnum.RED.value)
        return None

def main():
    parser = argparse.ArgumentParser(
        description="Validate rendered clip durations and optionally delete failed clips."
    )
    parser.add_argument('-y', '--yes', action='store_true',
                        help='Automatically delete clips that fail due to duration mismatch')
    args = parser.parse_args()

    # Ensure targets are loaded
    load_targets()

    if not isinstance(TARGETS, list) or len(TARGETS) < 2:
        print_colored("Invalid or empty TARGETS data", "validate",
                      ColorsEnum.RED.value)
        sys.exit(1)

    meta = TARGETS[0]
    meta_prefix = meta.get("prefix", "Part ")

    total_clips = 0
    passed = 0
    failed = 0          # duration mismatch, file exists
    missing = 0
    failed_files = []   # paths of existing clips with duration mismatch

    # Iterate over each video entry (raw index 1,2,3...)
    for raw_index in range(1, len(TARGETS)):
        video_data = TARGETS[raw_index]
        if not isinstance(video_data, dict):
            continue

        # Skip entries that are not actual video timestamps
        if "prefix" in video_data or "aliases" in video_data:
            continue

        # Determine folder name based on raw index (same as in clip_video)
        folder_name = sanitize(f"{meta_prefix}{raw_index}").lower()
        video_folder = os.path.join(OUTPUT_DIR, folder_name)

        # Get effective index and alias for this raw index
        effective_index = get_effective_index(TARGETS, raw_index)
        alias = get_alias_for_index(TARGETS, str(raw_index))

        # Build the display name (the prefix used in the clip filename)
        if alias:
            display_name = alias
        else:
            display_name = f"{meta_prefix}{effective_index}"

        # Process each timestamp in this video
        for start_time, duration in video_data.items():
            # Skip any metadata keys that might have slipped through
            if start_time in ("prefix", "aliases"):
                continue

            # Validate that start_time is a proper timestamp
            try:
                timestamp_to_sec(start_time)   # just to check format
            except (ValueError, TypeError):
                # Not a timestamp key – skip it
                continue

            expected_duration = duration + 2 * CLIP_BUFFER_SECONDS

            # Build clip filename exactly as in clip_video()
            safe_start = start_time.replace(':', '..')
            filename = f"{display_name}_{safe_start}_timestamped.mp4".lower()
            filename = filename.replace(" ", "_")   # remove any spaces
            clip_path = os.path.join(video_folder, filename)

            total_clips += 1

            if not os.path.exists(clip_path):
                print_colored(f"MISSING: {clip_path}", "validate",
                              ColorsEnum.RED.value)
                missing += 1
                continue

            actual_duration = get_video_duration(clip_path)
            if actual_duration is None:
                failed += 1
                failed_files.append(clip_path)
                continue

            diff = abs(actual_duration - expected_duration)
            if diff <= DURATION_TOLERANCE:
                print_colored(f"OK: {clip_path} ({actual_duration:.2f}s / {expected_duration:.2f}s)",
                              "validate", ColorsEnum.GREEN.value)
                passed += 1
            else:
                print_colored(f"FAIL: {clip_path} duration mismatch "
                              f"(expected {expected_duration:.2f}s, got {actual_duration:.2f}s)",
                              "validate", ColorsEnum.RED.value)
                failed += 1
                failed_files.append(clip_path)

    # Summary
    print("\n" + "="*50)
    print(f"Total clips checked: {total_clips}")
    print(f"Passed: {passed}")
    print(f"Failed (duration mismatch): {failed}")
    print(f"Missing: {missing}")
    
    should_delete = args.yes
    if failed_files and not args.yes:
        should_delete = input(f"{len(failed_files)} clips failed: Delete? Y/N: ").lower().startswith("y")
    

    # Auto‑delete failed files if requested
    if should_delete and failed_files:
        print("\n" + "-"*50)
        print(f"Deleting {len(failed_files)} failed clip(s) due to duration mismatch:")
        for path in failed_files:
            try:
                os.remove(path)
                print_colored(f"Deleted: {path}", "validate", ColorsEnum.YELLOW.value)
            except OSError as e:
                print_colored(f"Error deleting {path}: {e}", "validate", ColorsEnum.RED.value)
        print("-"*50)
    else:
        if failed_files:
            print(f"Ignoring {len(failed_files)} failed clip(s)...")

    # Final status
    any_issues = (failed > 0 or missing > 0)
    if not any_issues:
        print_colored("All clips validated successfully.", "validate",
                      ColorsEnum.GREEN.value)
    else:
        print_colored("Some clips have issues.", "validate",
                      ColorsEnum.RED.value)
        sys.exit(1)

if __name__ == "__main__":
    main()
