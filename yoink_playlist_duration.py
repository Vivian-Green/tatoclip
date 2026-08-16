import sys
import json
from common import *
from metadata_handler import (
    get_effective_index,
    get_raw_index,
    resolve_alias_to_effective_index, get_alias_for_index
)

ensure_ytdlp()

def get_playlist_duration(playlist_url):    
    total_duration = 0
    video_count = 0
    
    print(f"fetching playlist info for: {playlist_url}...")
    
    try:
        # get playlist info with durations
        command = [
            'yt-dlp',
            '--flat-playlist',
            '--dump-json',
            '--playlist-end', '99999',  # all of them bitches
            playlist_url
        ]
        
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        # Parse each video's funny json dump
        videos = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    video_data = json.loads(line)
                    videos.append(video_data)
                except json.JSONDecodeError:
                    continue
        
        if not videos:
            print("no videos? :megamind:")
            return 0
        
        print(f"found {len(videos)} videos\n")
        
        for i, video in enumerate(videos, 1):
            # foreach, get duration
            duration = video.get('duration')
            title = video.get('title', f'Video {i}')
            
            if duration is None:
                print(f"  video {i}: '{title}' - couldn't find shit for duration. It's None. The duration is fucking None.'")
                continue
            
            total_duration += duration
            video_count += 1
            
            # formatting
            mins = duration // 60
            secs = duration % 60
            hours = mins // 60
            mins = mins % 60
            
            if hours > 0:
                duration_str = f"{hours}:{mins:02d}:{secs:02d}"
            else:
                duration_str = f"{mins}:{secs:02d}"
            
            print(f"  video {i}: {duration_str} - {title[:40]}")
        
    except subprocess.CalledProcessError as e:
        print(f"error fetching playlist: {e}")
        print(f"yt-dlp error: {e.stderr}")
        return 0
    except Exception as e:
        print(f"unexpected error: {e}")
        return 0
    
    print(f"\nprocessed {video_count} videos successfully")
    return total_duration

if __name__ == "__main__":    
    playlist_url = sys.argv[1]
    total_seconds = get_playlist_duration(playlist_url)
    
    if total_seconds > 0:
        # convert to hours:minutes:seconds
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        print(f"\n{'='*50}")
        print(f"total runtime: {hours:02d}:{minutes:02d}:{seconds:02d}")
        print(f"{'='*50}")
    else:
        print("\nno duration data available for this playlist.")
