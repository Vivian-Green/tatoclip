import math
from common import *
from metadata_handler import get_effective_index, resolve_alias_to_effective_index, get_alias_for_index

# Constants and config

CLIP_BUFFER_SECONDS = 3 # todo: move to config, cont. in common.py
FRAME_RATE = 30  # Hardcoded frame rate # todo: move to config

timestamp_args = { # todo: move to config
    "x_offset": 15, # default: 15
    "y_offset": 1040, # default: 990
    "font_size": 20,
    "draw_type": "updating"
}

try:
    FONT_PATH = config["FONT_PATH"]
    if not os.path.exists(FONT_PATH):
        print_err(f"FONT_PATH {FONT_PATH} not found")
        exit(1)
except KeyError:
    print_err(f"FONT_PATH not defined in config.json")
    # todo: default safe font instead of exiting here. ffmpeg has one, but.. using it would require refactoring building the command iirc
    exit(1)

class DrawType(Enum):
    STATIC = "static"
    UPDATING = "updating"

video_downloading_times = []
video_clipping_times = []

clipping_times = {}

def build_clip_and_timestamp_script(input_file, start_time, duration, output_file, prefix):
    global timestamp_args

    x_offset = timestamp_args.get("x_offset", 0)
    y_offset = timestamp_args.get("y_offset", 0)
    font_size = timestamp_args.get("font_size", 0)
    draw_type = timestamp_args.get("draw_type", "updating")
    text = ""

    draw_type = draw_type.lower()
    if draw_type == DrawType.UPDATING.value: # todo: windows support. This pile of backslashes is proooobably only linux compatible
        strftime_expr = "%-M\\\\\\\\\\:%S"

        show_hours = start_time + duration >= 3600
        if show_hours:
            strftime_expr = "%-H\\\\\\\\\\:%M\\\\\\\\\\:%S"

        text = f"{prefix}\\ %{{pts\\:gmtime\\:{start_time}\\:{strftime_expr}}}"
    elif draw_type == DrawType.STATIC.value:
        text = f"{prefix} {sec_to_timestamp(start_time+CLIP_BUFFER_SECONDS).replace(':', '\\:')}"
    else:
        print("unknown draw type")
        exit(1)

    resolution = get_mp4_bounds(input_file)[1]
    if resolution == 1080:
        print("1080p")
    else:
        print("720p - SCALING")
        ratio = resolution/1080
        x_offset = int(math.ceil(x_offset * ratio))
        y_offset = int(math.ceil(y_offset * ratio))
        font_size = int(math.ceil(font_size * ratio))
        print(y_offset)
        print(font_size)

    drawtext_filter = (
        f"drawtext=\"text='{text}':"
        f"fontfile='{FONT_PATH}':"
        f"bordercolor=black:borderw=2:"
        f"x={x_offset}:"
        f"y={y_offset}:"
        f"fontsize={font_size}:fontcolor=white:"
        f"shadowx=3:shadowy=3:shadowcolor=black\""
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

    print_colored(f"{get_color(ColorsEnum.GREEN.value)}    Executing: " + " ".join(command) + RESET_COLOR, "clip_and_timestamp_ffmpeg", 4)
    print()

    script_path = "./ffmpeg_command.sh" # todo: windows compatibility
    with open(script_path, 'w') as f:
        f.write("#!/bin/bash\n")
        f.write(" ".join(command) + "\n")

    os.chmod(script_path, 0o755)

    return script_path

def clip_and_timestamp_ffmpeg(input_file, start_time, duration, output_file, prefix): # per clip
    start_clipping_time = time.time()
    global FRAME_RATE
    print(prefix)

    script_path = build_clip_and_timestamp_script(input_file, start_time - CLIP_BUFFER_SECONDS, CLIP_BUFFER_SECONDS * 2 + duration, output_file, prefix)

    print(f"Command written to {script_path}")
    print_colored(f"writing to {os.path.basename(output_file)} for {duration + 2*CLIP_BUFFER_SECONDS} seconds",
                  "clip_and_timestamp_ffmpeg", -len(COLORS), 1)
    try:
        process = subprocess.Popen([script_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

        while True:
            time.sleep(0.1)
            line = process.stdout.readline()

            if not line:
                if process.poll() is not None:
                    break # process finished
                continue # nothing printed recently

            line = line.strip()
            if not (("fps=" in line) or ("bitrate=" in line)):
                continue # irrelevant line

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
            progress = min(round((duration - remaining) / duration * 100), 100) # what's a lil 103% ever done to anyone, eh?
            update_loading_ui(min(progress/100, 1))
            ETA = remaining * FRAME_RATE / processing_fps
            #progress_bar = ("|" * math.ceil(progress / 2)) + ("." * math.floor(50 - progress / 2))
            #print(
            #    f"{get_color(ColorsEnum.CYAN.value)}[{progress_bar}] {progress}% ETA: {round(ETA, 1)} seconds{RESET_COLOR}",
            #    end='\r', flush=True
            #)

            if math.ceil(progress) > 99:
                break # process finished enough

    except Exception as e:
        print(e)
            
    end_clipping_time = time.time()
    global clipping_times
    if duration in clipping_times:
        clipping_times[duration].append(end_clipping_time - start_clipping_time)
    else:
        clipping_times[duration] = [end_clipping_time - start_clipping_time]

work_units_total = 0
work_units_active_total = 0
work_units_completed = 0
work_units_active_completed = 0
active_start_time = None
last_work_unit_update = None

def clip_video(timestamps, video_filename, prefix=""):
    global video_downloading_times, video_clipping_times
    global work_units_completed, work_units_active_total, work_units_active_completed, active_start_time, last_work_unit_update

    video_filepath = os.path.join(OUTPUT_DIR, video_filename)
    if not os.path.exists(video_filepath):
        print_err(f"Failed to clip {video_filepath} as it does not exist!")
        return False

    start_time_clipping = time.time()
    clip_files = []
    output_folder = os.path.join(OUTPUT_DIR, sanitize(video_filename[:-4])).lower()

    for start_time, duration in timestamps.items():
        update_loading_ui()
        unit_amount = duration + 2 * CLIP_BUFFER_SECONDS
        work_units_completed += unit_amount  # total units for progress bar
        last_work_unit_update = time.time()

        if not should_process_clip(start_time, prefix, output_folder):
            continue

        # Start timing active processing
        if active_start_time is None:
            active_start_time = time.time()

        work_units_active_total += unit_amount

        filename = f"{prefix}_{start_time.replace(':', '..')}_timestamped.mp4".lower()
        output_file = os.path.join(output_folder, filename).replace(" ", "_")

        if os.path.exists(output_file):
            print_colored(f"Skipping {output_file} as it already exists.", "extract_clips_ffmpeg", 2)
            clip_files.append(output_file)
            work_units_active_completed += unit_amount
            continue

        clip_and_timestamp_ffmpeg(video_filepath, timestamp_to_sec(start_time), duration, output_file, prefix)
        clip_files.append(output_file)

        # Increment active completed only for actually processed clips
        work_units_active_completed += unit_amount

    update_loading_ui()
    video_clipping_times.append((video_filename[:-4], time.time() - start_time_clipping))
    return clip_files


def clip_video_strategy(index, video_url, video_timestamps, prefix, video_filename):
    global work_units_completed, TARGETS

    raw_index = index
    effective_index = get_effective_index(TARGETS, raw_index)
    alias = get_alias_for_index(TARGETS, str(raw_index))

    print("YOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\n")
    print(alias)
    print("YOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\nYOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO\n\n\n")

    # Use alias if available, otherwise use prefix + effective index
    if alias:  # alias exists
        display_name = alias
    else:
        display_name = f"{prefix}{effective_index}"

    if not should_process_clips(video_filename[:-4], video_timestamps, OUTPUT_DIR, display_name):
        print_colored(f"Skipping {video_filename} as its clips already exist.", "clip_video_thread", 2)
        work_units_completed += sum(duration + 2 * CLIP_BUFFER_SECONDS for duration in video_timestamps.values())
        return False

    temp = clip_video(video_timestamps, video_filename, display_name)
    return temp






def format_timestamp(timestamp): # unused
    reversed_timestamp = timestamp[::-1]
    grouped = [reversed_timestamp[i:i + 2][::-1] for i in range(0, len(reversed_timestamp), 2)]
    formatted_timestamp = ':'.join(grouped[::-1])
    return formatted_timestamp


def calculate_total_work_units(targets, start_index=1, end_index=9999):
    """Calculate total work units for all videos to be processed"""
    global work_units_total
    
    end_index = min(end_index, len(targets))
    total_work_units = 0
    
    for index in range(start_index, end_index):
        video_timestamps = targets[index]
        if not video_timestamps or "prefix" in video_timestamps:
            continue
        
        total_work_units += sum(duration + 2 * CLIP_BUFFER_SECONDS for duration in video_timestamps.values())
    
    work_units_total = total_work_units
    return total_work_units



# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ UI SHIZ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ AI CODE VOMIT WARNING, I DIDN'T WANNA WRITE ANOTHER BASIC UI

# todo: sift through vomit, determine processing speed based only on work that wasn't already done 

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta

# Global variables for the GUI
loading_window = None
progress_bar = None
progress_bar2 = None
progress_label = None
time_label = None
speed_label = None

def init_loading_ui():
    """Initialize the GUI loading window"""
    global loading_window, progress_bar, progress_bar2, progress_label, time_label, speed_label, work_units_total, work_units_completed, start_time
    
    work_units_completed = 0
    start_time = datetime.now()
    
    # Create the loading window
    loading_window = tk.Tk()
    loading_window.title("Playlist Processing Progress")
    loading_window.geometry("400x150")
    loading_window.resizable(False, False)
    
    # Main frame
    main_frame = ttk.Frame(loading_window, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Progress bar
    progress_bar = ttk.Progressbar(
        main_frame, 
        orient=tk.HORIZONTAL, 
        length=300, 
        mode='determinate',
        maximum=work_units_total
    )
    progress_bar.pack(pady=3)

    progress_bar2 = ttk.Progressbar(
        main_frame, 
        orient=tk.HORIZONTAL, 
        length=300, 
        mode='determinate',
        maximum=1
    )
    progress_bar2.pack(pady=3)
    
    # Progress label (percentage)
    progress_label = ttk.Label(main_frame, text="0%")
    progress_label.pack()
    
    # Time remaining label
    time_label = ttk.Label(main_frame, text="Elapsed: 0:00:00 | Remaining: calculating...")
    time_label.pack(pady=3)
    
    # Processing speed label
    speed_label = ttk.Label(main_frame, text="Processing speed: 0 units/sec")
    speed_label.pack()
    
    # Make sure the window stays on top
    loading_window.attributes('-topmost', True)
    loading_window.update()
    
    # Start with an initial update
    update_loading_ui()

def update_loading_ui(bar_2_progress = 0.0): # todo: STOP UPDATING PROCESSING SPEED IN REAL TIME??? PROCESSING SPEED SHOULD BE UPDATED ONCE AFTER EACH CLIP.
    """Update the GUI loading bar with current progress"""
    global work_units_total, work_units_completed, start_time, loading_window
    global work_units_active_total, work_units_active_completed, active_start_time, last_work_unit_update
    global loading_window
    
    if work_units_total == 0 or not loading_window:
        return

    # Total progress for the main bar
    progress_total = min(work_units_completed / work_units_total, 1.0)
    percentage = progress_total * 100
    progress_bar['value'] = work_units_completed
    progress_bar2['value'] = bar_2_progress
    progress_label.config(text=f"{percentage:.1f}%")

    # --- Active processing speed ---
    if active_start_time and work_units_active_total > 0:
        now = time.time()
        if last_work_unit_update is None:
            last_work_unit_update = now
        active_elapsed = last_work_unit_update - active_start_time
        # units/sec based only on actively processed clips
        speed = work_units_active_completed / max(active_elapsed, 0.0001)
        # Estimated remaining time for entire workload, based on active speed
        remaining_seconds = (work_units_total - work_units_completed) / max(speed, 0.0001)
        remaining = timedelta(seconds=remaining_seconds)
        elapsed_td = timedelta(seconds=active_elapsed)

        time_str = f"Elapsed: {str(elapsed_td).split('.')[0]} | Remaining: {str(remaining).split('.')[0]}"

        last_work_unit_update = now
    else:
        speed = 0
        time_str = "Elapsed: 0:00:00 | Remaining: calculating..."

    # Update labels
    time_label.config(text=time_str)
    speed_label.config(text=f"Processing speed: {speed:.1f} units/sec")

    # Update the window
    loading_window.update()
    
    # Close the window if processing is complete
    if progress_total >= 1.0:
        loading_window.after(2000, loading_window.destroy)  # Close after 2 seconds   


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ /UI SHIZ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

if __name__ == "__main__":
    calculate_total_work_units(TARGETS)
    init_loading_ui()
    process_targets_with(clip_video_strategy)
    if loading_window and loading_window.winfo_exists():
            loading_window.destroy()

    print("Processing completed.")
    print()
    
    print(clipping_times)
    for duration, times in clipping_times.items():
        if times:  # Ensure the list isn't empty
            average_time = sum(times) / len(times)
            print(f"Duration {duration}s: Average Clipping Time = {average_time:.2f} seconds")
    
    input("\n\nPress enter to close")