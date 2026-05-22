# ui_handler.py
import time
from datetime import timedelta
import tkinter as tk
from tkinter import ttk
from typing import List, Optional
from enum import Enum

from common import TARGETS, CLIP_BUFFER_SECONDS, ColorsEnum, get_color, RESET_COLOR, print_colored, print_err

# todo: orange (second) highlight seems misaligned after first video? miiiight not be getting updated segment positions

class UIState:
    """Singleton class to manage UI state"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            # UI window and widgets
            self.loading_window = None
            self.time_label = None
            self.speed_label = None
            self.progress_bars = []
            self.progress_labels = []
            self.progress_value_labels = []

            # Progress tracking
            self.work_units_total = 0
            self.work_units_completed = 0
            self.work_units_active_total = 0
            self.work_units_active_completed = 0
            self.active_start_time = None
            self.last_work_unit_update = None
            self.start_time = None

            # Update throttling
            self.last_ui_update_time = 0
            self.ui_update_interval = 1  # seconds

            self.segment_positions = []  # List of lists for each progress bar
            self.progress_bar_segments = []  # For drawing segments
            self.active_segment_overlays = [None, None]  # one for bar 0 and bar 1
            self.full_bar_highlights = [None, None]

            self._initialized = True

    def reset(self):
        """Reset UI state for new processing session"""
        self.work_units_completed = 0
        self.work_units_active_total = 0
        self.work_units_active_completed = 0
        self.active_start_time = None
        self.last_work_unit_update = None
        self.start_time = None
        self.last_ui_update_time = 0
        for i in range(2):
            if self.full_bar_highlights[i]:
                self.full_bar_highlights[i].destroy()
                self.full_bar_highlights[i] = None


class UIHandler:
    """Main UI handler class"""

    def __init__(self):
        self.state = UIState()

    def init_loading_ui(self):
        """Initialize the GUI loading window with table layout"""
        self.state.reset()
        self.state.start_time = time.time()

        # Clear previous segments
        self.state.segment_positions = []
        self.state.progress_bar_segments = []

        # Create the loading window
        self.state.loading_window = tk.Tk()
        self.state.loading_window.title("Playlist Processing Progress")
        self.state.loading_window.geometry("1000x200")  # Increased height for segment visibility
        self.state.loading_window.resizable(False, False)

        # Main frame
        main_frame = ttk.Frame(self.state.loading_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create table-like structure for 3 rows
        for i in range(3):
            row_frame = ttk.Frame(main_frame)
            row_frame.pack(fill=tk.X, pady=2)

            # Label on the left
            label = ttk.Label(row_frame, text="", width=8, anchor="w")
            label.pack(side=tk.LEFT, padx=(0, 5))
            self.state.progress_labels.append(label)

            # Create a frame for the progress bar with markers
            progress_frame = ttk.Frame(row_frame)
            progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=2)

            # Progress bar in the middle
            progress_bar = ttk.Progressbar(
                progress_frame,
                orient=tk.HORIZONTAL,
                length=300,
                mode='determinate',
                maximum=1
            )

            progress_bar.pack(fill=tk.X, expand=True)
            self.state.progress_bars.append(progress_bar)

            # Store empty list for this progress bar's segments
            self.state.progress_bar_segments.append([])

            # Value/percentage on the right
            value_label = ttk.Label(row_frame, text="0%", width=15, anchor="e")
            value_label.pack(side=tk.RIGHT, padx=(5, 0))
            self.state.progress_value_labels.append(value_label)

        # Initialize segment positions for first two bars
        self.state.segment_positions = [[] for _ in range(2)]

        self._create_full_bar_highlight(1)
        self._create_full_bar_highlight(2)

        # Time remaining label
        self.state.time_label = ttk.Label(main_frame, text="Elapsed: 0:00:00 | Remaining: calculating...")
        self.state.time_label.pack(pady=(10, 3))

        # Processing speed label
        self.state.speed_label = ttk.Label(main_frame, text="Processing speed: 0 units/sec")
        self.state.speed_label.pack()

        # Make sure the window stays on top
        self.state.loading_window.attributes('-topmost', True)
        self.state.loading_window.update()

        # Start with an initial update
        self.update_loading_ui()

    def update_segment_markers(self, targets: Optional[List] = None):
        """Update segment markers for the first two progress bars"""
        if targets is None:
            targets = TARGETS

        if not targets or len(targets) < 1:
            return

        # Clear existing segment markers
        for i, segments in enumerate(self.state.progress_bar_segments):
            for segment in segments:
                segment.destroy()
            segments.clear()
            if i < len(self.state.segment_positions):
                self.state.segment_positions[i].clear()  # ADD THIS

        # First progress bar: markers between videos
        work_units_per_video = self.calculate_work_units_per_video(targets)
        if work_units_per_video:
            cumulative = 0
            for work_units in work_units_per_video[:-1]:  # All except last
                cumulative += work_units
                position = cumulative / self.state.work_units_total if self.state.work_units_total > 0 else 0
                self.state.segment_positions[0].append(position)

                # Create visual marker for the first bar
                self._create_segment_marker(0, position)

        # Second progress bar: markers between clips for current video
        video_info = self.get_video_progress()
        completed_videos = video_info[1]

        if completed_videos < len(targets) - 1:
            current_video = targets[completed_videos + 1]
            if current_video and "prefix" not in current_video:
                work_units_per_clip = [
                    duration + 2 * CLIP_BUFFER_SECONDS
                    for duration in current_video.values()
                ]

                if work_units_per_clip:
                    total_video_work_units = sum(work_units_per_clip)
                    if total_video_work_units > 0:
                        cumulative = 0
                        for work_units in work_units_per_clip[:-1]:  # All except last
                            cumulative += work_units
                            position = cumulative / total_video_work_units
                            self.state.segment_positions[1].append(position)

                            # Create visual marker for the second bar
                            self._create_segment_marker(1, position)

    def _create_segment_marker(self, bar_index: int, position: float):
        """Create a visual marker on a progress bar at the given position"""
        if not self.state.loading_window or not self.state.progress_bars:
            return

        progress_bar = self.state.progress_bars[bar_index]
        parent = progress_bar.master

        # Get progress bar dimensions
        progress_bar.update_idletasks()
        x1, y1, x2, y2 = progress_bar.winfo_rootx(), progress_bar.winfo_rooty(), \
            progress_bar.winfo_rootx() + progress_bar.winfo_width(), \
            progress_bar.winfo_rooty() + progress_bar.winfo_height()

        # Convert to parent coordinates
        x1_parent = progress_bar.winfo_x()
        width = progress_bar.winfo_width()

        # Calculate marker position
        marker_x = x1_parent + (position * width)

        # Create a thin vertical line as marker
        marker = tk.Frame(parent, width=1, height=progress_bar.winfo_height(),
                          bg='black', relief=tk.RAISED)
        marker.place(x=marker_x, y=0)

        self.state.progress_bar_segments[bar_index].append(marker)

    def _get_segment_ranges(self, bar_index: int):
        """
        Returns list of (start, end) normalized ranges for a bar
        """
        positions = self.state.segment_positions[bar_index]
        if not positions:
            return [(0.0, 1.0)]

        ranges = []
        last = 0.0
        for p in positions:
            ranges.append((last, p))
            last = p
        ranges.append((last, 1.0))
        return ranges

    def _get_active_segment_index(self, bar_index: int, progress: float):
        ranges = self._get_segment_ranges(bar_index)
        for i, (start, end) in enumerate(ranges):
            if start <= progress <= end:
                return i, (start, end)
        return None, None

    def _highlight_active_segment(self, bar_index: int, progress: float):
        """Highlight the currently active segment of a progress bar with a visual overlay."""
        pb = self.state.progress_bars[bar_index]
        parent = pb.master

        # Clean up old overlay
        old_overlay = self.state.active_segment_overlays[bar_index]
        if old_overlay:
            old_overlay.destroy()

        # Get active segment information
        seg_index, seg_range = self._get_active_segment_index(bar_index, progress)
        if seg_range is None:
            self.state.active_segment_overlays[bar_index] = None
            return

        # Calculate segment bounds
        start, end = seg_range
        segment_width = max(0.0, min(1.0, end - start))  # Ensure valid bounds

        # Get progress bar dimensions
        pb.update_idletasks()
        bar_width = pb.winfo_width()
        bar_height = pb.winfo_height()
        bar_x = pb.winfo_x()
        bar_y = pb.winfo_y()

        # Calculate overlay geometry
        segment_pixel_x = int(bar_x + start * bar_width)
        segment_pixel_width = max(
            4,  # Minimum width for visibility
            int(segment_width * bar_width)
        )

        if bar_index == 0:
            color = "#6a0dad"
        else:
            color = "#cc7a00"

        overlay = tk.Frame(
            parent,
            width=segment_pixel_width,
            height=2,
            bg=color,
            highlightthickness=0,
            relief="flat"
        )

        # Place overlay
        overlay.place(
            x=segment_pixel_x+1,
            y=bar_y + bar_height - 3 #- overlay_y_offset
        )

        self.state.active_segment_overlays[bar_index] = overlay

    def _create_full_bar_highlight(self, bar_index: int):
        """Create a full-width highlight at the top of a progress bar"""
        pb = self.state.progress_bars[bar_index]
        parent = pb.master

        # Clean up old highlight
        old_highlight = self.state.full_bar_highlights[bar_index-1]
        if old_highlight:
            old_highlight.destroy()

        # Get progress bar dimensions
        pb.update_idletasks()
        bar_width = pb.winfo_width()
        bar_height = pb.winfo_height()
        bar_x = pb.winfo_x()
        bar_y = pb.winfo_y()

        # Set color based on bar index
        color = "#6a0dad" if bar_index == 1 else "#cc7a00"

        # Create highlight frame (thinner than the active segment overlay)
        highlight = tk.Frame(
            parent,
            width=bar_width,
            height=3,  # Thin highlight at the top
            bg=color,
            highlightthickness=0,
            relief="flat"
        )

        # Place highlight at the top of the bar
        highlight.place(
            x=bar_x + 1,
            y=bar_y - 1  # Position slightly above the bar
        )

        self.state.full_bar_highlights[bar_index-1] = highlight

    def calculate_total_work_units(self, targets, start_index=1, end_index=9999):
        """Calculate total work units for progress tracking"""
        end_index = min(end_index, len(targets))
        total_work_units = 0

        for index in range(start_index, end_index):
            video_timestamps = targets[index]
            if not video_timestamps or "prefix" in video_timestamps:
                continue

            total_work_units += sum(
                duration + 2 * CLIP_BUFFER_SECONDS
                for duration in video_timestamps.values()
            )

        self.state.work_units_total = total_work_units
        if self.state.loading_window:
            self.update_segment_markers(targets)

        return total_work_units

    def calculate_work_units_per_video(self, targets, start_index=1, end_index=9999):
        """Calculate work units per video"""
        if not self.state.work_units_total or self.state.work_units_total < 1:
            self.calculate_total_work_units(targets, start_index, end_index)

        end_index = min(end_index, len(targets))
        work_units_per_video = []
        for index in range(start_index, end_index):
            video_timestamps = targets[index]
            if not video_timestamps or "prefix" in video_timestamps:
                continue
            work_units_per_video.append(
                sum(duration + 2 * CLIP_BUFFER_SECONDS for duration in video_timestamps.values())
            )
        return work_units_per_video

    def get_video_progress(self):
        """Get detailed progress information for current video and clip"""
        if not TARGETS or TARGETS == {} or len(TARGETS) < 1:
            print_err("TARGETS is empty!")
            return (0, 0, 0, 0, 0, 0, 0)

        work_units_per_video = self.calculate_work_units_per_video(TARGETS)
        videos_list = TARGETS[1:]
        work_units_from_completed_videos_cumulative = 0
        video_count = len(videos_list)

        # Find current video
        completed_videos = 0
        work_units_this_video = 0
        for index, work_units in enumerate(work_units_per_video):
            if work_units_from_completed_videos_cumulative + work_units > self.state.work_units_completed:
                completed_videos = index
                work_units_this_video = work_units
                break
            work_units_from_completed_videos_cumulative += work_units
        else:
            # All videos completed
            completed_videos = len(work_units_per_video)
            work_units_this_video = 0

        # Calculate work units completed in current video
        if completed_videos < len(work_units_per_video):
            completed_work_units_this_video = (
                    self.state.work_units_completed - work_units_from_completed_videos_cumulative
            )
        else:
            completed_work_units_this_video = 0

        # Get current clip
        current_clip = 0
        work_units_this_clip = 0
        clips_this_video = 0

        if completed_videos < len(TARGETS) - 1:  # -1 for metadata
            current_video = TARGETS[completed_videos + 1]  # +1 because TARGETS[0] is metadata

            if current_video and "prefix" not in current_video:
                # Calculate work units per clip
                work_units_per_clip = [
                    duration + 2 * CLIP_BUFFER_SECONDS
                    for duration in current_video.values()
                ]
                clips_this_video = len(work_units_per_clip)

                # Find current clip
                cumulative_clip_work_units = 0
                for clip_index, clip_work_units in enumerate(work_units_per_clip):
                    if cumulative_clip_work_units + clip_work_units > completed_work_units_this_video:
                        current_clip = clip_index
                        work_units_this_clip = clip_work_units
                        break
                    cumulative_clip_work_units += clip_work_units
                else:
                    # All clips in this video completed
                    current_clip = len(work_units_per_clip)
                    work_units_this_clip = 0

        return (
            video_count,
            completed_videos,
            work_units_this_video,
            completed_work_units_this_video,
            work_units_this_clip,
            current_clip,
            clips_this_video
        )

    def update_loading_ui(self, clip_progress=0.0):
        """Update the GUI loading bar with current progress"""
        # Throttle updates
        current_time = time.time()
        if current_time - self.state.last_ui_update_time < self.state.ui_update_interval:
            return
        self.state.last_ui_update_time = current_time

        if self.state.work_units_total == 0 or not self.state.loading_window:
            return

        # Get progress details
        (
            total_videos,
            completed_videos,
            work_units_this_video,
            completed_work_units_this_video,
            work_units_this_clip,
            current_clip,
            clips_this_video
        ) = self.get_video_progress()

        # Update segment markers when video changes
        if (hasattr(self.state, 'last_completed_videos') and
                self.state.last_completed_videos != completed_videos):
            self.update_segment_markers()
            self._create_full_bar_highlight(1)
            self._create_full_bar_highlight(2)
        self.state.last_completed_videos = completed_videos

        completed_work_units_this_clip = work_units_this_clip * clip_progress

        # Calculate progress values
        progress_total = min(self.state.work_units_completed / self.state.work_units_total, 1.0)
        video_progress_seconds = round(completed_work_units_this_video + completed_work_units_this_clip)
        video_progress_normalized = (
            video_progress_seconds / work_units_this_video
            if work_units_this_video > 0 else 0
        )

        # Update progress bars
        self.state.progress_bars[0]['value'] = progress_total
        self.state.progress_bars[1]['value'] = video_progress_normalized
        self.state.progress_bars[2]['value'] = clip_progress

        # Brighten active segments (first two bars only)
        self._highlight_active_segment(0, progress_total+0.00001)
        self._highlight_active_segment(1, video_progress_normalized)

        # Update labels in table format
        if TARGETS and len(TARGETS) > 0:
            prefix = TARGETS[0].get('prefix', 'Part ')
        else:
            prefix = 'Part '

        # Row 1: Overall completion
        self.state.progress_labels[0].config(text="Overall:")
        self.state.progress_value_labels[0].config(
            text=f"{completed_videos}/{total_videos} videos ({progress_total * 100:.0f}%)"
        )

        # Row 2: Current video progress
        self.state.progress_labels[1].config(text=f"{prefix}{completed_videos + 1}:")
        self.state.progress_value_labels[1].config(
            text=f"{video_progress_seconds}/{work_units_this_video}s ({video_progress_normalized * 100:.0f}%)"
        )

        # Row 3: Current clip progress
        self.state.progress_labels[2].config(text=f"Clip {current_clip + 1}/{clips_this_video}:")
        self.state.progress_value_labels[2].config(
            text=f"{round(completed_work_units_this_clip)}/{work_units_this_clip}s ({clip_progress * 100:.0f}%)"
        )

        # Update time and speed labels
        time_str, speed = self._calculate_time_and_speed(
            completed_work_units_this_clip,
            clip_progress
        )

        self.state.time_label.config(text=time_str)
        self.state.speed_label.config(text=f"Processing speed: {speed:.1f} units/sec")

        # Update window
        self.state.loading_window.update()

        # Close window if processing complete
        if progress_total >= 1.0:
            self.state.loading_window.after(2000, self.state.loading_window.destroy)

    def _calculate_time_and_speed(self, completed_work_units_this_clip, clip_progress):
        """Calculate time remaining and processing speed"""
        if (self.state.active_start_time and self.state.work_units_completed > 0 and
                self.state.last_work_unit_update is not None):
            now = time.time()
            active_elapsed = self.state.last_work_unit_update - self.state.active_start_time

            # Calculate speed based on active processing
            speed = (
                    (self.state.work_units_active_completed + completed_work_units_this_clip) /
                    max(active_elapsed, 0.0001)
            )

            # Calculate remaining time
            remaining_seconds = (
                    (self.state.work_units_total - self.state.work_units_completed) /
                    max(speed, 0.0001)
            )
            remaining = timedelta(seconds=remaining_seconds)
            elapsed_td = timedelta(seconds=active_elapsed)

            time_str = f"Elapsed: {str(elapsed_td).split('.')[0]} | Remaining: {str(remaining).split('.')[0]}"

            self.state.last_work_unit_update = now
            return time_str, speed

        return "Elapsed: 0:00:00 | Remaining: calculating...", 0

    def increment_work_units(self, amount, active=False):
        """Increment work unit counters"""
        self.state.work_units_completed += amount
        if active:
            self.state.work_units_active_completed += amount

    def set_active_start_time(self):
        """Set the start time for active processing"""
        if self.state.active_start_time is None:
            self.state.active_start_time = time.time()
            self.state.last_work_unit_update = self.state.active_start_time

    def add_active_work_units(self, amount):
        """Add work units to active total"""
        self.state.work_units_active_total += amount

    def close_ui(self):
        """Close the UI window"""
        if self.state.loading_window and self.state.loading_window.winfo_exists():
            self.state.loading_window.destroy()


# Global UI handler instance
_ui_handler = None


def get_ui_handler():
    """Get or create the global UI handler instance"""
    global _ui_handler
    if _ui_handler is None:
        _ui_handler = UIHandler()
    return _ui_handler


# Convenience functions for backward compatibility
def init_loading_ui():
    get_ui_handler().init_loading_ui()


def calculate_total_work_units(targets, start_index=1, end_index=9999):
    return get_ui_handler().calculate_total_work_units(targets, start_index, end_index)


def update_loading_ui(clip_progress=0.0):
    get_ui_handler().update_loading_ui(clip_progress)


def close_ui():
    get_ui_handler().close_ui()


if __name__ == "__main__":
    # Test the UI handler
    handler = UIHandler()
    handler.state.work_units_total = 100
    handler.init_loading_ui()
    handler.state.loading_window.mainloop()
