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

def build_clip_and_timestamp_script(input_file, start_time, duration, output_file, prefix, frame_rate, series_text=None):
    global TIMESTAMP_ARGS
    draw_type = TIMESTAMP_ARGS.get("draw_type", "updating").lower()

    resolution = get_mp4_bounds(input_file)[1]

    text = ""

    x_offset = TIMESTAMP_ARGS.get("x_offset", 0)
    y_offset = TIMESTAMP_ARGS.get("y_offset", 0)
    font_size = TIMESTAMP_ARGS.get("font_size", 0)
    borderw = TIMESTAMP_ARGS.get("borderw", 0)
    shadowx = TIMESTAMP_ARGS.get("shadowx", 0)
    shadowy = TIMESTAMP_ARGS.get("shadowy", 0)

    if resolution == 1080:
        print("1080p - No timestamp scaling")
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

    filters = []

    def escape_drawtext_string(s):
        s = s.replace('%', '%%')
        # shell -> Python -> FFmpeg backslash escaping (absurd)
        s = s.replace('\\', '\\\\\\\\')
        s = s.replace("'", "'\\''")
        s = s.replace("\"", "\\\"")
        return s

    if draw_type == DrawType.UPDATING.value:
        # Determine if the displayed time crosses the 1‑hour mark
        crosses_hour = (start_time < 3600) and (start_time + duration >= 3600)

        if crosses_hour:
            cross_t = 3600 - start_time

            # Format without hours
            strftime_no_hour = "%-M\\\\\\\\\\:%S"
            text_no_hour = f"{prefix}\\ %{{pts\\:gmtime\\:{start_time}\\:{strftime_no_hour}}}"

            # Format with hours
            strftime_hour = "%-H\\\\\\\\\\:%M\\\\\\\\\\:%S"
            text_hour = f"{prefix}\\ %{{pts\\:gmtime\\:{start_time}\\:{strftime_hour}}}"

            # Build the two timestamp filters with enable conditions
            filter_no_hour = (
                f"drawtext=\"text='{text_no_hour}':"
                f"fontfile='{FONT_PATH}':"
                f"bordercolor=black:borderw={borderw}:"
                f"x={x_offset}:"
                f"y={y_offset}-text_h/2:"
                f"fontsize={font_size}:fontcolor=white:"
                f"shadowx={shadowx}:shadowy={shadowy}:shadowcolor=black:"
                f"enable='lt(t,{cross_t})'\""
            )

            filter_hour = (
                f"drawtext=\"text='{text_hour}':"
                f"fontfile='{FONT_PATH}':"
                f"bordercolor=black:borderw={borderw}:"
                f"x={x_offset}:"
                f"y={y_offset}-text_h/2:"
                f"fontsize={font_size}:fontcolor=white:"
                f"shadowx={shadowx}:shadowy={shadowy}:shadowcolor=black:"
                f"enable='gte(t,{cross_t})'\""
            )

            # Add series filter (always visible) and then the two timestamp filters
            if series_text:
                filters.append(series_filter)
            filters.append(filter_no_hour)
            filters.append(filter_hour)

        else:
            # Original single‑filter logic
            show_hours = start_time + duration >= 3600
            strftime_expr = "%-M\\\\\\\\\\:%S"
            if show_hours:
                strftime_expr = "%-H\\\\\\\\\\:%M\\\\\\\\\\:%S"

            text = f"{prefix}\\ %{{pts\\:gmtime\\:{start_time}\\:{strftime_expr}}}"

            drawtext_filter = (
                f"drawtext=\"text='{text}':"
                f"fontfile='{FONT_PATH}':"
                f"bordercolor=black:borderw={borderw}:"
                f"x={x_offset}:"
                f"y={y_offset}-text_h/2:"
                f"fontsize={font_size}:fontcolor=white:"
                f"shadowx={shadowx}:shadowy={shadowy}:shadowcolor=black\""
            )

            if series_text:
                filters.append(series_filter)
            filters.append(drawtext_filter)
    elif draw_type == DrawType.STATIC.value:
        text = f"{prefix} {sec_to_timestamp(start_time + CLIP_BUFFER_SECONDS).replace(':', '\\:')}"
    else:
        print(f"unknown draw type {draw_type}")
        exit(1)

    if series_text:
        # todo: does this need further escaping?
        escaped_series_text = escape_drawtext_string(series_text)

        series_y_offset = math.floor(y_offset - (font_size * 1.4)) # series text goes 1.5 lines above timestamp... if this works?
        series_filter = (
            f"drawtext=\"text='{escaped_series_text}':"
            f"fontfile='{FONT_PATH}':"
            f"bordercolor=black:borderw={borderw}:"
            f"x={x_offset}:"
            f"y={series_y_offset}-text_h/2:"
            f"fontsize={math.floor(font_size*0.8)}:fontcolor=white:"
            f"shadowx={shadowx}:shadowy={shadowy}:shadowcolor=black\""
        )
        filters.append(series_filter)

    drawtext_filter = (
        f"drawtext=\"text='{text}':"
        f"fontfile='{FONT_PATH}':"
        f"bordercolor=black:borderw={borderw}:"
        f"x={x_offset}:"
        f"y={y_offset}-text_h/2:"
        f"fontsize={font_size}:fontcolor=white:"
        f"shadowx={shadowx}:shadowy={shadowy}:shadowcolor=black\""
    )
    filters.append(drawtext_filter)

    filter_chain = ",".join(filters)
    command = [
        'ffmpeg',
        '-ss', str(start_time),
        '-i', input_file,
        '-t', str(duration),
        '-vf', filter_chain,
        '-c:v', 'h264_nvenc',#'libx264' 'h264_nvenc'
        '-b:v', BIT_RATE,
        '-preset', 'p6',
        '-r', str(frame_rate),
        output_file,
        '-y'
    ]

    print_colored(f"{get_color(ColorsEnum.GREEN.value)}    Generated Command: " + " ".join(command) + RESET_COLOR,
                  "clip_and_timestamp_ffmpeg", 4)
    print()

    script_path = "./ffmpeg_command.sh"  # todo: windows compatibility
    with open(script_path, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(" ".join(command) + "\n")

    os.chmod(script_path, 0o755)

    return script_path


def get_video_frame_rate(file_path):
    """
    Retrieve the video's average frame rate using ffprobe.
    Returns a float (e.g., 29.97, 25.0, 60.0).
    """
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=r_frame_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        output = subprocess.check_output(cmd, universal_newlines=True).strip()
        # ffprobe returns a rational like "30000/1001" or "25/1"
        num, den = map(int, output.split('/'))
        return num / den
    except Exception as e:
        print_colored(f"Warning: Could not determine source frame rate for {file_path}, using {HIGH_RES_FRAME_RATE} fps as fallback.",
                      "get_video_frame_rate", 3)
        return HIGH_RES_FRAME_RATE  # fallback


def clip_and_timestamp_ffmpeg(input_file, start_time, duration, output_file, prefix, series_text=None):  # per clip
    start_clipping_time = time.time()
    print(prefix)

    # Determine output frame rate based on source resolution
    resolution = get_mp4_bounds(input_file)[1]
    if resolution >= HIGH_RES_THRESHOLD:
        frame_rate = HIGH_RES_FRAME_RATE
        print(f"Resolution {resolution}p >= {HIGH_RES_THRESHOLD}p: capping to ({frame_rate}fps)")
    else:
        frame_rate = get_video_frame_rate(input_file)
        print(f"Resolution {resolution}p < {HIGH_RES_THRESHOLD}p: using source frame rate ({frame_rate:.2f}fps)")

    script_path = build_clip_and_timestamp_script(input_file, start_time - CLIP_BUFFER_SECONDS, CLIP_BUFFER_SECONDS * 2 + duration,
                                                  output_file, prefix, frame_rate, series_text)

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
                continue

            fps_match = re.search(r'fps=\s*(\d+)', line)
            if fps_match:
                processing_fps = float(int(fps_match.group(1)))
                if processing_fps < 1:
                    processing_fps = 1
            else:
                continue

            remaining = duration - (current_frame / frame_rate)
            progress = min(round((duration - remaining) / duration * 100),
                           100)  # what's a lil 103% ever done to anyone, eh?

            # Use the UI handler to update progress
            update_loading_ui(min(progress / 100, 1))

            ETA = remaining * frame_rate / processing_fps
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


def clip_video(timestamps, video_filename, prefix="", series_text=None):
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

        clip_and_timestamp_ffmpeg(video_filepath, timestamp_to_sec(start_time), duration, output_file, prefix, series_text)
        clip_files.append(output_file)

        ui.increment_work_units(unit_amount, active=True)

    video_clipping_times.append((video_filename[:-4], time.time() - start_time_clipping))
    return clip_files


def clip_video_strategy(index, video_url, video_timestamps, prefix, video_filename):
    ui = get_ui_handler()

    raw_index = index
    effective_index = get_effective_index(TARGETS, raw_index)
    alias = get_alias_for_index(TARGETS, str(raw_index))

    metadata = TARGETS[0] if TARGETS else {}
    series_text = metadata.get("series", None)

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

    temp = clip_video(video_timestamps, video_filename, display_name, series_text)
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
