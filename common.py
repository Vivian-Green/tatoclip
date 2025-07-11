import argparse
import os
import subprocess
import re
import json
import time
from datetime import datetime
from enum import Enum
from pytube import Playlist
from typing import Protocol

from ytdlp_checker import ensure_ytdlp
from tatoclipLogging import LogModule

class VideoProcessingStrategy(Protocol):
    def __call__(self, index: int, url: str, timestamps: list, prefix: str, filename: str):
        ...

# Load Configuration
targets_version = 1
CONFIG_PATH = "config.json"
with open(CONFIG_PATH, 'r') as config_file:
    config = json.load(config_file)

# Constants and Global Variables
CACHE_PATH = config.get("CACHE_PATH", "cache.json")
BIT_RATE = config.get("BIT_RATE", "50000k")
OUTPUT_DIR = config.get("OUTPUT_DIR", "videos")
TARGETS = {}

def override_output_dir(): # todo: lmao??
    global OUTPUT_DIR, TARGETS
    meta = TARGETS[0]

    OUTPUT_DIR = meta.get("name", OUTPUT_DIR)

def update_targets_0_1(targets: dict, filepath: str) -> list:
    print("updating from version 0 to 1...")

    url, data = next(iter(targets.items()))
    meta = data[0]

    # ensure of: name, prefix
    meta_keys_list = {
        "prefix": "Part ",
        "name": "default",
        "version": 1,
        "url": url
    }

    for k, default in meta_keys_list.items():
        if k in meta:
            continue
        meta[k] = default    

    new_targets = [meta] + data[1:]
    
    targets = new_targets
    with open(filepath, "w") as f:
        json.dump(targets, f, indent=4)

    return targets

    print("updated from version 0 to 1!")


def load_targets():
    global TARGETS, targets_version
    do_update_meta = True

    with open("targets.json", "r") as f:
        TARGETS = json.load(f)

    this_version = -1
    if isinstance(TARGETS, list) and len(TARGETS) > 0:
        meta = TARGETS[0]
        if isinstance(meta, dict):
            this_version = meta.get("version", targets_version)
    else:
        if do_update_meta and isinstance(TARGETS, dict):
            print("couldn't get metadata version.. assuming v0")
            this_version = 0
        else:
            raise ValueError("couldn't get metadata version, and did not find a v0 dictionary?")

    if this_version < targets_version:
        if do_update_meta:
            print("old version detected, attempting update...")
            while this_version < targets_version:
                match this_version:
                    case 0:
                        v1_targets = update_targets_0_1(TARGETS, "targets.json")
                        TARGETS = v1_targets
                        this_version = 1
                        print("updated v0 targets file to v1")
                    case _:
                        ValueError(f"no update function to handle updating {this_version} to {targets_version}")

        else:
            raise ValueError(f"invalid version (expected {targets_version}, got {this_version})")
    elif this_version > targets_version:
        raise ValueError(f"invalid version (expected {targets_version}, got {this_version})")

    if not "list" in meta['url']:
        raise ValueError(f"Invalid url, expected playlist but got f{meta['url']}")

    override_output_dir()

load_targets()

THUMBNAIL_CACHE_PATH = config.get("THUMBNAIL_CACHE_PATH", "thumbnail_cache/")
DIR_PATH = os.path.dirname(os.path.realpath(__file__))

LOG_NAME = config.get("LOG_NAME", "log.txt")
logger = LogModule(LOG_NAME)

COLORS = config.get("COLORS", { # TODO: BETTER
    0: '\033[97m',  # white
    1: '\033[92m',  # green
    2: '\033[93m',  # yellow
    3: '\033[91m',  # red
    4: '\033[96m'   # cyan
})
RESET_COLOR = '\033[0m'

class ColorsEnum(Enum):
    WHITE = 0
    GREEN = 1
    YELLOW = 2
    RED = 3
    CYAN = 4

def get_color(color_enum):
    return COLORS.get(str(color_enum))

def print_err(text, label=""):
    print_colored(f"{get_color(ColorsEnum.RED.value)}{text}{RESET_COLOR}", label, -ColorsEnum.RED.value)

def print_colored(text, label="", print_type=0, indentation_level=0):
    global RESET_COLOR
    global COLORS
    label = (label + "                                        ")
    label = label[0:24]

    should_log = False
    if print_type < 0:
        print_type = 0-print_type
        should_log = True
    indent = '.' * (indentation_level * 4) + " "
    color = COLORS.get(str(print_type % len(COLORS)))
    now = datetime.now()
    current_min_and_sec = now.strftime("%H:%M:%S")

    built_string = f"[{color}{label} {current_min_and_sec}{RESET_COLOR}] {indent}{text}"
    print(built_string)

    if should_log:
        logger.log(label+text)

def timestamp_to_sec(timestamp):
    parts = list(map(int, timestamp.split(':')))
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h = 0
        m, s = parts
    else:
        try:
            return int(timestamp)
        except:
            raise ValueError("Invalid timestamp format")
    return h * 3600 + m * 60 + s

def sec_to_timestamp(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    timestamp = ""
    if h > 0:
        timestamp = f"{h}:{m:02}:{s:02}"
    else:
        timestamp = f"{m}:{s:02}".lstrip('0')
    if timestamp[0] == ":":
        timestamp = timestamp[1:]

    if len(timestamp) < 3:
        return f"0:{timestamp}"
    return timestamp











cache_data = {}
cache_locked = False

# Function to load cache data from file
def load_cache():
    global cache_data
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r') as f:
            cache_data = json.load(f)
    #print(cache_data)

def dump_cache():
    global CACHE_PATH
    global cache_data
    with open(CACHE_PATH, 'w') as f:
        json.dump(cache_data, f, indent=4)

def video_title_is_cached(video_url):
    return extract_video_id(video_url) in cache_data

def playlist_links_are_cached(playlist_url):
    return playlist_url in cache_data

def autosave(interval):
    global last_save_time
    global cache_data
    global CACHE_PATH
    global cache_locked
    if time.time() - last_save_time > interval:
        if not cache_locked:
            try:
                cache_locked = True
                last_save_time = time.time()
                with open(CACHE_PATH, 'w') as f:
                    json.dump(cache_data, f, indent=4)
                cache_locked = False
            except:
                i = 0
                while cache_locked and i < 40:  # 2 seconds
                    time.sleep(0.05)
                    i += 1
                cache_locked = False
                autosave(-1)

# Load cache data when script starts
load_cache()
youtube_title_fetch_count = 0
last_save_time = time.time()


# Function to extract video ID from YouTube URL
def extract_video_id(video_url):
    return video_url.split('?v=')[-1]
   
def extract_playlist_id(playlist_url):
    return playlist_url.split('?list=')[-1]



youtube_playlist_links_fetch_count = 0
def get_playlist_links(playlist_url):
    global cache_data
    if playlist_url in cache_data:
        return cache_data[playlist_url]
        
    return get_playlist_links_untrusted(playlist_url)
    
def get_playlist_links_untrusted(playlist_url):
    global cache_data

    try:
        # Fetch the playlist and its links
        playlist = Playlist(playlist_url)
        new_links = list(playlist.video_urls)

        # Check if playlist URL is in cache
        if playlist_url in cache_data:
            # Compare lengths to decide if cache needs updating
            cached_links = cache_data[playlist_url]
            if len(new_links) != len(cached_links):
                print(f"Playlist length has changed for {playlist_url}. Updating cache.") # todo: diff
                cache_data[playlist_url] = new_links
                autosave(1)
        else:
            # Cache the new playlist links if not present
            cache_data[playlist_url] = new_links
            autosave(1)
            
        return new_links

    except Exception as e:
        # Handle potential errors (e.g., network issues, invalid URLs)
        print(f"Error fetching playlist links: {e}")
        return None


def should_process_clip(start_time, prefix, output_folder):
    if start_time == "name":
        return False
    if start_time == "prefix":
        return False
    if start_time == "aliases":
        return False

    filename = f"{prefix}_{start_time.replace(':', '..')}_timestamped.mp4"
    output_file = os.path.join(output_folder.lower(), filename.lower()).replace(" ", "_")

    if os.path.exists(output_file):
        return False

    return True


def should_process_clips(short_video_title, timestamps, input_dir, prefix):
    output_folder = os.path.join(input_dir, short_video_title)
    print(output_folder)
    os.makedirs(output_folder, exist_ok=True)

    for start_time, duration in timestamps.items():
        if not should_process_clip(start_time, prefix, output_folder):
            continue
        return True

















def sanitize(title):
    title = re.sub(r'[\\/*?:%#<>|]', '', title).strip().lower()
    title = title.replace("'", "").replace('"', "").replace(" ", "_").replace(".", "_")
    title = title.replace("__", "-").replace("_-_", "-")

    # bash compatibility tape
    bash_special_chars = [' ', '!', '(', ')', ';', '&', '|', '?', '=', '<', '>', '$', '^', '*', '~', '#', '{', '}', '[', ']', ':', '\\', '/']
    for char in bash_special_chars:
        title = title.replace(char, "_")

    title = title[-30:]
    title = re.sub('^[^a-zA-Z]*', '', title)

    return title


pytube_is_borked = False
def fetch_title(video_url, alt_title="err fetching title2", send_views_bool=False):
    # please please please don't use this for file names, just.. please. Not again.
    #                                   - viv at 1:30am on apparently mario day 2025
    global cache_data
    global youtube_title_fetch_count
    global last_save_time
    global cache_locked
    global pytube_is_borked

    video_id = extract_video_id(video_url)

    loops = 100
    while cache_locked and loops > 0:
        time.sleep(0.1)
        loops -= 1

    if video_id in cache_data and not send_views_bool:
        if type(cache_data[video_id]) == type("test"): # load bearing idiocy
            return cache_data[video_id]

    title = fetch_title_ytdlp(video_url)

    if not title or len(title) == 0:
        title = alt_title  # Use the alternative title if yt-dlp fails as well
    else:
        cache_data[video_id] = title

    youtube_title_fetch_count += 1
    autosave(1)

    return title

ytdlp_is_borked = False
def fetch_title_ytdlp(video_url):
    global ytdlp_is_borked

    print("Fetching title with yt-dlp... ", end="\r")
    try:
        assert not ytdlp_is_borked
        ensure_ytdlp()

        # Temporary download location to get video metadata
        temp_file = os.path.join(DIR_PATH, OUTPUT_DIR, 'temp_video.mp4')

        # Use yt-dlp to extract metadata and get the video title
        command = [
            'yt-dlp',
            '--quiet',
            '--extract-audio',
            '--get-title',
            '--output', temp_file,
            video_url
        ]

        result = subprocess.run(command, check=True, capture_output=True, text=True)
        title = result.stdout.strip()  # Extract the title from the command's output
        print(f"Fetched title with yt-dlp: {title}")
        return title

    except Exception as e:
        ytdlp_is_borked = True
        print_colored(f"Error fetching title with yt-dlp: {e}", "fetch_title_yt_dlp_fallback", 3)
        return None




_video_bounds_cache = {}
def get_mp4_bounds(video_path):
    # Return cached result if available
    if video_path in _video_bounds_cache:
        return _video_bounds_cache[video_path]

    #print(video_path)
    command = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'json',
        video_path
    ]

    #print(command)

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = json.loads(result.stdout)
    width = output['streams'][0]['width']
    height = output['streams'][0]['height']

    _video_bounds_cache[video_path] = [width, height]
    return [width, height]


def process_playlist(playlist_url, timestamps, process_fn, prefix="", start_index=1, end_index=None):
    print("Processing playlist...")
    start_time_playlist = time.time()
    end_index = end_index or len(timestamps)
    total_videos = end_index - start_index
    print(f"Total videos to process: {total_videos}")

    skipped = 0
    processed = 0
    results = []

    video_urls = get_playlist_links(playlist_url)

    for index in range(start_index, end_index):
        #print(video_urls)
        #print(index)
        try:
            video_url = video_urls[index - 1]
        except IndexError:
            print_colored(f"video {index} OOB in playlist url cache, checking for changes...", "process_playlist")
            video_urls = get_playlist_links_untrusted(playlist_url)
            try:
                video_url = video_urls[index - 1]
            except IndexError:
                print_err(f"video {index} OOB in playlist", "fetch_video_url_fallback")

        video_timestamps = timestamps[index]

        # Generic skipping logic
        if not video_timestamps or "prefix" in video_timestamps:
            skipped += 1
            continue

        video_filename = sanitize(f"{prefix}{index}") + ".mp4"

        result = process_fn(index, video_url, video_timestamps, prefix, video_filename)

        if result is None:
            skipped += 1
        else:
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)
            processed += 1

        # ETA estimation
        elapsed = time.time() - start_time_playlist
        avg_time = elapsed / (processed + skipped) if processed + skipped else 0
        remaining = total_videos - (processed + skipped)
        eta = time.strftime("%H:%M:%S", time.gmtime(avg_time * remaining))
        print(f"ETA: {eta}")

    print(f"Finished processing playlist. Processed {processed} videos, skipped {skipped}.")
    return results


def process_targets_with(strategy: VideoProcessingStrategy):
    """
    Execute playlist processing based on global TARGETS configuration.

    Args:
        strategy (callable): The specific video processing function to use
            (must match VideoProcessingStrategy signature: fn(index: int, url: str, timestamps: list, prefix: str, filename: str))

    Returns:
        list: All expected output files from processing
    """
    parser = argparse.ArgumentParser(description="Process video links from targets.json.")
    parser.add_argument("start_index", type=int, nargs="?", default=1,
                      help="Starting index for processing (1-based).")
    parser.add_argument("end_index", type=int, nargs="?",
                      help="Optional ending index for processing.")
    args = parser.parse_args()

    if not callable(strategy):
        raise TypeError("process_playlist_fn must be a callable function")

    expected_files = [] # todo: restructure
    
    # old:
    #{
    #"https://www.youtube.com/watch?v=rLw2ndAW9NE&list=PLenI3Kbdx0D19iGG1nElWVp0GpI-cUHMQ": [
    #    {
    #        "prefix": "Part ",...
    #    },
    #       {data},
    #       {data},...
    #   ]
    #}
    # new:
    # [
    #   {
    #       "prefix": "Part ",
    #       "version": 1,
    #       "name": "example",
    #       "url": "https://www.youtube.com...list=..."
    #   },
    #   {
    #       "0:00": 5,
    #       "1:23": 30,...
    #   },
    #   {data},
    #   {data},
    # ]
    #

    if not isinstance(TARGETS, list):
        raise ValueError(f"Invalid data format for targets. Expected list, got {type(TARGETS)}")

    meta = TARGETS[0]
    prefix = meta.get("prefix", "Part ")
    url = meta.get("url", "https...")


    if "list" in url:
        output_files = process_playlist(
            playlist_url=url,
            timestamps=TARGETS,
            process_fn=strategy,
            prefix=prefix,
            start_index=args.start_index,
            end_index=args.end_index
        )
        expected_files.extend(output_files)
    else:
        raise ValueError(f"Non-playlist url detected in targets.json metadata - url: {url}")

    return expected_files
