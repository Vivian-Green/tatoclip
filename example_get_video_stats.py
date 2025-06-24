

# example code for how one could process a playlist with the provided functions: fetching metadata with yt-dlp


from common import *
ensure_ytdlp()

def get_video_stats(video_url, video_filename):
    try:
        print_colored(f"fetching stats for: {video_url}", "processing video", 0, 3)

        # Use yt-dlp to get video metadata as JSON
        command = [
            'yt-dlp',
            '--skip-download',
            '--print', '%(title)s|||%(view_count)s',
            '--no-warnings',
            '--', video_url
        ]

        result = subprocess.run(command, check=True, capture_output=True, text=True)
        title, view_count = result.stdout.strip().split('|||')

        return {
            'title': title,
            'views': view_count,
            'example_filename': video_filename
        }

    except Exception as e:
        print_colored(f"Failed to get info for {video_url}: {str(e)}", "error", 1, 1)
        return None


def get_video_stats_strategy(index, video_url, video_timestamps, prefix, video_filename):
    return get_video_stats(video_url, video_filename)


if __name__ == "__main__":
    video_stats = process_targets_with(get_video_stats_strategy)

    # Print summary
    print("\n=== Video Statistics Summary ===")
    for stats in video_stats:
        if stats:
            print(f"\nTitle: {stats['title']}")
            print(f"Example filename: {stats['example_filename']}")
            print(f"Views: {stats['views']}")