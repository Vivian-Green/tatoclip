# tatoclip.py
import math
from common import *
from metadata_handler import get_effective_index, resolve_alias_to_effective_index, get_alias_for_index
from ui_handler import get_ui_handler, init_loading_ui, calculate_total_work_units, update_loading_ui, close_ui

# Constants and config

class DrawType(Enum):
    STATIC = "static"
    UPDATING = "updating"

video_downloading_times = []
video_clipping_times = []
clipping_times = {}

def build_clip_and_timestamp_script(input_file, start_time, duration, output_file, prefix):
    global TIMESTAMP_ARGS
    draw_type = TIMESTAMP_ARGS.get("draw_type", "updating").lower()

    if draw_type == DrawType.UPDATING.value:  # todo: windows support. This pile of backslashes is proooobably only linux compatible
        strftime_expr = "%-M\\\\\\\\\\:%S"

        show_hours = start_time + duration >= 3600
        if show_hours:
            strftime_expr = "%-H\\\\\\\\\\:%M\\\\\\\\\\:%S"

        text = f"{prefix}\\ %{{pts\\:gmtime\\:{start_time}\\:{strftime_expr}}}"
    elif draw_type == DrawType.STATIC.value:
        text = f"{prefix} {sec_to_timestamp(start_time + CLIP_BUFFER_SECONDS).replace(':', '\\:')}"
    else:
        print(f"unknown draw type {draw_type}")
        exit(1)

    resolution = get_mp4_bounds(input_file)[1]

    x_offset = TIMESTAMP_ARGS.get("x_offset", 0)
    y_offset = TIMESTAMP_ARGS.get("y_offset", 0)
    font_size = TIMESTAMP_ARGS.get("font_size", 0)
    borderw = TIMESTAMP_ARGS.get("borderw", 0)
    shadowx = TIMESTAMP_ARGS.get("shadowx", 0)
    shadowy = TIMESTAMP_ARGS.get("shadowy", 0)

    if resolution == 1080:
        print("1080p")
    else:
        print(f"{resolution}p - SCALING")
        ratio = resolution / 1080
        x_offset = int(math.floor(x_offset * ratio))
        y_offset = int(math.ceil(y_offset * ratio))
        font_size = int(math.ceil(font_size * ratio))
        borderw = int(math.ceil(borderw * ratio))
        shadowx = int(math.ceil(shadowx * ratio))
        shadowy = int(math.ceil(shadowy * ratio))
        print(y_offset)
        print(font_size)

    drawtext_filter = (
        f"drawtext=\"text='{text}':"
        f"fontfile='{FONT_PATH}':"
        f"bordercolor=black:borderw={borderw}:"
        f"x={x_offset}:"
        f"y={y_offset}-text_h/2:"
        f"fontsize={font_size}:fontcolor=white:"
        f"shadowx={shadowx}:shadowy={shadowy}:shadowcolor=black\""
    )

    command = [
        'ffmpeg',
        '-ss', str(start_time),
        '-i', input_file,
        '-t', str(duration),
        '-vf', drawtext_filter,
        '-c:v', 'libx264',
        '-b:v', BIT_RATE,
        '-r', str(FRAME_RATE),
        output_file,
        '-y'
    ]

    print_colored(f"{get_color(ColorsEnum.GREEN.value)}    Executing: " + " ".join(command) + RESET_COLOR,
                  "clip_and_timestamp_ffmpeg", 4)
    print()

    script_path = "./ffmpeg_command.sh"  # todo: windows compatibility
    with open(script_path, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(" ".join(command) + "\n")

    os.chmod(script_path, 0o755)

    return script_path


def clip_and_timestamp_ffmpeg(input_file, start_time, duration, output_file, prefix):  # per clip
    start_clipping_time = time.time()
    global FRAME_RATE
    print(prefix)

    script_path = build_clip_and_timestamp_script(input_file, start_time - CLIP_BUFFER_SECONDS,
                                                  CLIP_BUFFER_SECONDS * 2 + duration, output_file, prefix)

    print(f"Command written to {script_path}")
    print_colored(f"writing to {os.path.basename(output_file)} for {duration + 2 * CLIP_BUFFER_SECONDS} seconds",
                  "clip_and_timestamp_ffmpeg", -len(COLORS), 1)
    try:
        process = subprocess.Popen([script_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   universal_newlines=True)

        while True:
            time.sleep(0.1)
            line = process.stdout.readline()

            if not line:
                if process.poll() is not None:
                    break  # process finished
                continue  # nothing printed recently

            line = line.strip()
            if not (("fps=" in line) or ("bitrate=" in line)):
                continue  # irrelevant line

            frame_match = re.search(r'frame=\s*(\d+)', line)
            if frame_match:
                current_frame = float(int(frame_match.group(1)))
            else:
                print(f"wuha clip_and_timestamp_ffmpeg impossible path? \n{line}")
                continue

            fps_match = re.search(r'fps=\s*(\d+)', line)
            if fps_match:
                processing_fps = float(int(fps_match.group(1)))
                if processing_fps < 1:
                    processing_fps = 1
            else:
                print(f"wuhb clip_and_timestamp_ffmpeg impossible path? \n{line}")
                continue

            remaining = duration - (current_frame / FRAME_RATE)
            progress = min(round((duration - remaining) / duration * 100),
                           100)  # what's a lil 103% ever done to anyone, eh?

            # Use the UI handler to update progress
            update_loading_ui(min(progress / 100, 1))

            ETA = remaining * FRAME_RATE / processing_fps
            # progress_bar = ("|" * math.ceil(progress / 2)) + ("." * math.floor(50 - progress / 2))
            # print(
            #    f"{get_color(ColorsEnum.CYAN.value)}[{progress_bar}] {progress}% ETA: {round(ETA, 1)} seconds{RESET_COLOR}",
            #    end='\r', flush=True
            # )

            if math.ceil(progress) > 99:
                break  # process finished enough

    except Exception as e:
        print(e)

    end_clipping_time = time.time()
    global clipping_times
    if duration in clipping_times:
        clipping_times[duration].append(end_clipping_time - start_clipping_time)
    else:
        clipping_times[duration] = [end_clipping_time - start_clipping_time]


work_units_total = 0
work_units_completed = 0
active_start_time = None
last_work_unit_update = None

work_units_active_total = 0
work_units_active_completed = 0


def clip_video(timestamps, video_filename, prefix=""):
    ui = get_ui_handler()

    video_filepath = os.path.join(OUTPUT_DIR, video_filename)
    if not os.path.exists(video_filepath):
        print_err(f"Failed to clip {video_filepath} as it does not exist!")
        return False

    start_time_clipping = time.time()
    clip_files = []
    output_folder = os.path.join(OUTPUT_DIR, sanitize(video_filename[:-4])).lower()

    for start_time, duration in timestamps.items():
        unit_amount = duration + 2 * CLIP_BUFFER_SECONDS

        if not should_process_clip(start_time, prefix, output_folder):
            ui.increment_work_units(unit_amount)
            continue

        # Add to active work units
        ui.add_active_work_units(unit_amount)
        ui.set_active_start_time()

        filename = f"{prefix}_{start_time.replace(':', '..')}_timestamped.mp4".lower()
        output_file = os.path.join(output_folder, filename).replace(" ", "_")

        if os.path.exists(output_file):
            print_colored(f"Skipping {output_file} as it already exists.", "extract_clips_ffmpeg", 2)
            clip_files.append(output_file)

            ui.increment_work_units(unit_amount, active=True)
            continue

        clip_and_timestamp_ffmpeg(video_filepath, timestamp_to_sec(start_time), duration, output_file, prefix)
        clip_files.append(output_file)

        ui.increment_work_units(unit_amount, active=True)

    video_clipping_times.append((video_filename[:-4], time.time() - start_time_clipping))
    return clip_files


def clip_video_strategy(index, video_url, video_timestamps, prefix, video_filename):
    ui = get_ui_handler()

    raw_index = index
    effective_index = get_effective_index(TARGETS, raw_index)
    alias = get_alias_for_index(TARGETS, str(raw_index))

    # Use alias if available, otherwise use prefix + effective index
    if alias:
        display_name = alias
    else:
        display_name = f"{prefix}{effective_index}"

    if not should_process_clips(video_filename[:-4], video_timestamps, OUTPUT_DIR, display_name):
        print_colored(f"Skipping {video_filename} as its clips already exist.", "clip_video_thread", 2)

        total_units = sum(duration + 2 * CLIP_BUFFER_SECONDS for duration in video_timestamps.values())
        ui.increment_work_units(total_units)
        return False

    temp = clip_video(video_timestamps, video_filename, display_name)
    return temp


def format_timestamp(timestamp):  # unused
    reversed_timestamp = timestamp[::-1]
    grouped = [reversed_timestamp[i:i + 2][::-1] for i in range(0, len(reversed_timestamp), 2)]
    formatted_timestamp = ':'.join(grouped[::-1])
    return formatted_timestamp


if __name__ == "__main__":
    calculate_total_work_units(TARGETS)
    init_loading_ui()
    process_targets_with(clip_video_strategy)
    close_ui()

    print("Processing completed.")
    print()

    print(clipping_times)
    for duration, times in clipping_times.items():
        if times:  # Ensure the list isn't empty
            average_time = sum(times) / len(times)
            print(f"Duration {duration}s: Average Clipping Time = {average_time:.2f} seconds")
    
    import validate_durations
    validate_durations.main()

    input("\n\nPress enter to close")
    sys.exit(0)
