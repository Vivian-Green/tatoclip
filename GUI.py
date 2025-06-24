import os
import sys
import json
import subprocess
import time

import qdarkstyle
import requests
from PyQt5.QtWidgets import (QApplication, QMainWindow, QFileDialog, QWidget, QLabel, QPushButton, QLineEdit,
                             QVBoxLayout, QHBoxLayout, QFormLayout, QTextEdit, QMessageBox, QListWidget, QScrollArea, QListWidgetItem)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QMimeData, QEvent, pyqtSignal
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QIcon, QColor, QPalette
from pytube import YouTube

from common import fetch_title, get_playlist_links, get_playlist_links_untrusted, THUMBNAIL_CACHE_PATH, extract_video_id


# todo: clear existing video titles before adding new ones
# todo: change window title on loading file
# todo: Save prompt on close
# todo: Save should open Save As if no input file text

# todo: run with.. visible shell

# todo: build recovery file, caching changes every minute, only if changes were made, extension .tsrec
#           check for a .tsrec file matching <current_file>.json.tsrec, prompt user to load changes if it exists
#           delete recovery file on changes
#           a change should register when a new row is created

main_palette = None
app = None

class FetchThread(QThread):
    signal = pyqtSignal('PyQt_PyObject')

    def __init__(self, urls):
        super().__init__()
        self.urls = urls

    def run(self):
        for video_url in self.urls:
            try:
                video_title = fetch_title(video_url)
                self.signal.emit(video_title)
            except subprocess.CalledProcessError as e:
                print(f"Error fetching title for {video_url}: {e}")
                self.signal.emit(None)
            except Exception as e:
                print(f"Error fetching title for {video_url}: {str(e)}")
                self.signal.emit(None)

class RowWidget(QWidget):
    remove_signal = pyqtSignal(QWidget)

    def __init__(self):
        super().__init__()

        self.layout = QHBoxLayout()

        self.timestamp_edit = QLineEdit()
        self.timestamp_edit.setMaximumWidth(40)
        self.duration_edit = QLineEdit()
        self.duration_edit.setMaximumWidth(80)

        self.remove_button = QPushButton('-')
        self.remove_button.setMaximumWidth(20)
        self.add_button = QPushButton('+')
        self.add_button.setMaximumWidth(20)

        self.remove_button.clicked.connect(self.remove_row)
        self.add_button.clicked.connect(self.add_row)

        self.layout.addWidget(self.timestamp_edit)
        self.layout.addWidget(self.duration_edit)
        self.layout.addWidget(self.remove_button)
        self.layout.addWidget(self.add_button)

        #self.timestamp_edit.setStyleSheet("background-color: #353535; border-color: #454545; color: white;")
        #self.duration_edit.setStyleSheet("background-color: #353535; border-color: #454545; color: white;")

        self.setLayout(self.layout)

        self.timestamp_edit.installEventFilter(self)
        self.duration_edit.installEventFilter(self)

    def remove_row(self):
        self.remove_signal.emit(self)
        self.setParent(None)

    def add_row(self):
        self.parent().layout().addWidget(RowWidget())

    def get_data(self):
        timestamp = self.timestamp_edit.text()
        duration = self.duration_edit.text()
        return timestamp, duration

    def set_data(self, timestamp, duration):
        self.timestamp_edit.setText(timestamp)
        self.duration_edit.setText(duration)
        
    def eventFilter(self, source, event): 
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                self.focusPreviousField(source)
                return True
            elif event.key() == Qt.Key_Down or event.key() == Qt.Key_Return:
                self.focusNextField(source)
                return True
            elif event.key() == Qt.Key_Plus or event.key() == Qt.Key_Equal:  # Handle both numpad + and regular +
                self.add_row()
                return True
            elif event.key() == Qt.Key_Minus:  # Handle numpad -
                self.remove_row()
                return True
        return super().eventFilter(source, event)

    def focusNextField(self, source):
        if source == self.timestamp_edit or source == self.duration_edit:
            is_timestamp = source == self.timestamp_edit
            parent_layout = self.parent().layout()
            current_index = parent_layout.indexOf(self)
            next_index = current_index + 1

            if next_index < parent_layout.count():
                next_row = parent_layout.itemAt(next_index).widget()
                if isinstance(next_row, RowWidget):
                    if is_timestamp:
                        next_row.timestamp_edit.setFocus()
                    else:
                        next_row.duration_edit.setFocus()
            else:
                # Check if either field in the current row contain data, if they do, make a new thing
                if self.timestamp_edit.text() or self.duration_edit.text():
                    self.add_row()
                    next_row = parent_layout.itemAt(next_index).widget()
                    if isinstance(next_row, RowWidget):
                        next_row.timestamp_edit.setFocus()

    def focusPreviousField(self, source):
        if source == self.timestamp_edit or source == self.duration_edit:
            is_timestamp = source == self.timestamp_edit
            parent_layout = self.parent().layout()
            current_index = parent_layout.indexOf(self)
            previous_index = current_index - 1

            if previous_index >= 0:
                previous_row = parent_layout.itemAt(previous_index).widget()
                if isinstance(previous_row, RowWidget):
                    if is_timestamp:
                        previous_row.timestamp_edit.setFocus()
                    else:
                        previous_row.duration_edit.setFocus()

class PlaylistBuilderGUI(QMainWindow):
    def __init__(self, initial_file=None):
        super().__init__()
        self.video_data = {}
        self.meta = {}
        self.current_video_title = None
        self.input_file_name = initial_file
        self.initUI()
        if self.input_file_name:
            self.load_from_json()

    def initUI(self):
        global main_palette
        self.setWindowTitle('tatoclip, playlist timestampifinator')
        self.setGeometry(100, 100, 600, 800)

        self.setAcceptDrops(True)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        form_layout = QFormLayout()

        self.playlist_url_edit = QLineEdit()
        self.playlist_url_edit.setPalette(main_palette)
        self.playlist_url_edit.setToolTip("link any video in a youtube playlist here, doesn't have to be a direct link to the playlist")
        form_layout.addRow(QLabel('Playlist URL:'), self.playlist_url_edit)

        # Create a horizontal layout for project name and prefix
        project_meta_layout = QHBoxLayout()

        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPalette(main_palette)
        self.project_name_edit.setToolTip("subfolder that contains the video files")
        project_meta_layout.addWidget(self.project_name_edit)

        # Add prefix field
        project_meta_layout.addWidget(QLabel('Prefix:'))
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPalette(main_palette)
        self.prefix_edit.setMaximumWidth(100)  # Limit width
        self.prefix_edit.setPlaceholderText("Part ")
        self.prefix_edit.setToolTip("Prefix for video titles (include trailing space if needed)")
        project_meta_layout.addWidget(self.prefix_edit)

        # Add the horizontal layout to the form layout
        form_layout.addRow(QLabel('Project Name:'), project_meta_layout)

        fetch_meta_button = QPushButton('Fetch Playlist Videos\' Metadatas')
        fetch_meta_button.clicked.connect(self.fetch_video_meta)
        fetch_meta_button.setToolTip("fetches titles and thumbnails from youtube - might take a bit")
        form_layout.addRow(fetch_meta_button)

        self.video_titles_list = QListWidget()
        self.video_titles_list.itemClicked.connect(self.handle_item_clicked)
        self.video_titles_list.setMinimumWidth(200)
        self.video_titles_list.setMaximumWidth(900)
        #self.video_titles_list.setStyleSheet("""
        #    QListWidget::item {
        #        height: 50px;  /* Adjust padding as necessary */
        #    }
        #""")

        main_layout.addLayout(form_layout)

        self.second_panel = QWidget()
        self.second_panel_layout = QVBoxLayout()
        self.second_panel.setLayout(self.second_panel_layout)
        self.video_titles_list.setMinimumWidth(300)
        self.video_titles_list.setMaximumWidth(300)
        self.second_panel.setMaximumWidth(250)

        self.scroll_area = QScrollArea()        
        self.scroll_area.setWidgetResizable(True)
        self.second_panel_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.second_panel)

        h_layout = QHBoxLayout()
        h_layout.addWidget(self.video_titles_list)
        h_layout.addWidget(self.scroll_area)

        main_layout.addLayout(h_layout)

        export_button = QPushButton('Save as')
        export_button.clicked.connect(self.export_to_json)

        save_button = QPushButton('Save')
        save_button.clicked.connect(self.save_to_json)

        run_button = QPushButton('Export to targets and run')
        run_button.clicked.connect(self.faafo)
        run_button.setToolTip("Saves to targets.json, and runs tatoclip.py. Expects files to already be in the project folder.")

        load_button = QPushButton('Load from JSON')
        load_button.clicked.connect(self.load_from_json)
        load_button.setToolTip("You can drag and drop any targets json onto this window for the same affect")

        fetch_meta_button.setStyleSheet("background-color: #353535; color: white;")
        export_button.setStyleSheet("background-color: #353535; color: white;")
        save_button.setStyleSheet("background-color: #353535; color: white;")
        run_button.setStyleSheet("background-color: #353535; color: white;")
        load_button.setStyleSheet("background-color: #353535; color: white;")


        h_layout2 = QHBoxLayout()
        h_layout2.addWidget(run_button)
        h_layout2.addWidget(export_button)
        h_layout2.addWidget(save_button)
        h_layout2.addWidget(load_button)
        form_layout.addRow(h_layout2)

        central_widget.setLayout(main_layout)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.json'):
                self.input_file_name = file_path
                self.load_from_json()
            event.accept()
        else:
            event.ignore()

    def load_from_json(self):
        if self.input_file_name and "json" in self.input_file_name:
            try:
                with open(self.input_file_name, 'r') as f:
                    loaded_data = json.load(f)

                playlist_url = list(loaded_data.keys())[0]
                self.playlist_url_edit.setText(playlist_url)
                self.fetch_video_meta()

                playlist_data = loaded_data.get(playlist_url)

                if playlist_data and len(playlist_data) > 0:
                    first_item = playlist_data[0]
                    print(first_item)
                    if isinstance(first_item, dict):
                        self.meta = first_item
                        self.prefix_edit.setText(self.meta["prefix"])
                        self.project_name_edit.setText(self.meta["name"])
                timestamps = playlist_data[1:]

                video_urls = get_playlist_links(playlist_url)

                for index, video_url in enumerate(video_urls):
                    title = fetch_title(video_url, "err fetching title", False)
                    if title and index < len(timestamps):
                        self.video_data[title] = timestamps[index]
                    #print(f"{title}: {views}")

                print(self.video_data)

            except Exception as e:
                print(f"Error loading from JSON: {str(e)}")
                self.show_message_box('Error', f'Error loading from JSON: {str(e)}')
        else:
            print("no/invalid input filename")

    def save_to_json(self):
        playlist_url = self.playlist_url_edit.text().strip()

        video_urls = get_playlist_links(playlist_url)

        output = [{"prefix": self.prefix_edit.text(), "name": self.project_name_edit.text()}]

        for video_url in video_urls:
            this_title = fetch_title(video_url)
            if this_title in self.video_data:
                output.append(self.video_data[this_title])

        wrapped = {playlist_url: output}

        if self.input_file_name:
            try:
                with open(self.input_file_name, 'w') as f:
                    json.dump(wrapped, f, indent=4)
                print(f"Data saved to {self.input_file_name}")
            except Exception as e:
                print(f"Error saving to JSON: {str(e)}")
                self.show_message_box('Error', f'Error saving to JSON: {str(e)}')

    def export_to_json(self):
        if self.current_video_title is not None:
            self.save_video_data(self.current_video_title)

        self.input_file_name = QFileDialog.getSaveFileName(self, 'Save File', '', 'JSON (*.json)')[0]

        if self.input_file_name:
            self.save_to_json()

    def handle_item_clicked(self, item):
        if self.current_video_title is not None:
            self.save_video_data(self.current_video_title)

        label = self.video_titles_list.itemWidget(item)
        video_title = label.text()
        self.current_video_title = video_title
        self.populate_second_panel(item)

    def populate_second_panel(self, item):
        try:
            while self.second_panel_layout.count():
                child = self.second_panel_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            label = self.video_titles_list.itemWidget(item)
            video_title = label.text()

            if video_title in self.video_data:
                print("populating2?")
                for timestamp, duration in self.video_data[video_title].items():
                    row = RowWidget()
                    row.setStyleSheet("background-color: #353535; color: white;")
                    row.remove_signal.connect(self.handle_row_remove)
                    row.set_data(timestamp, str(duration))
                    self.second_panel_layout.addWidget(row)
            else:
                print("populating2?")
                self.second_panel_layout.addWidget(RowWidget())
        except Exception as e:
            print(f"Error populating second panel: {e}")

    def handle_row_remove(self, removed_row):
        if self.current_video_title:
            timestamp, _ = removed_row.get_data()
            if self.current_video_title in self.video_data:
                if timestamp in self.video_data[self.current_video_title]:
                    del self.video_data[self.current_video_title][timestamp]
                    if not self.video_data[self.current_video_title]:
                        del self.video_data[self.current_video_title]

    def save_video_data(self, video_title):
        if video_title is not None:
            data = {}
            for i in range(self.second_panel_layout.count()):
                row_widget = self.second_panel_layout.itemAt(i).widget()
                if isinstance(row_widget, RowWidget):
                    timestamp, duration = row_widget.get_data()
                    if timestamp and duration:
                        if len(timestamp) > 0:
                            data[timestamp] = int(duration)

            if len(data) > 0:
                self.video_data[video_title] = data

    def fetch_thumbnail(self, video_id):
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/default.jpg"

        # Ensure the cache directory exists
        if not os.path.exists(THUMBNAIL_CACHE_PATH):
            os.makedirs(THUMBNAIL_CACHE_PATH)

        # Define the file path
        file_path = os.path.join(THUMBNAIL_CACHE_PATH, f"{video_id}.jpg")

        # Download and save the thumbnail
        response = requests.get(thumbnail_url)
        with open(file_path, 'wb') as file:
            file.write(response.content)

        return file_path

    def fetch_video_meta(self):
        playlist_url = self.playlist_url_edit.text().strip()

        if not playlist_url:
            self.show_message_box('Error', 'Please enter a valid playlist URL.')
            return

        current_item = self.video_titles_list.currentItem()
        if current_item is not None:
            self.save_video_data(current_item)

        # Get video URLs in the playlist
        video_urls = get_playlist_links_untrusted(playlist_url)

        for url in video_urls:
            self.update_video_titles_list(url)

    def update_video_titles_list(self, video_url):
        if video_url is not None:
            try:
                # Call the function to add the video title and thumbnail to the list
                self.add_video_to_list(video_url)

            except Exception as e:
                print(f"Error fetching title/thumbnail for {video_url}: {str(e)}")
                self.show_message_box('Error', f"Error fetching video data: {str(e)}")
        else:
            self.show_message_box('Error', 'Error fetching video data')

    def add_video_to_list(self, video_url):
        # Fetch the video title using the provided fetch_title function
        video_title = fetch_title(video_url)

        # Fetch the YouTube video object using pytube
        yt = YouTube(video_url)

        # Extract video ID
        video_id = extract_video_id(video_url)

        # Fetch the thumbnail file path
        thumbnail_path = self.fetch_thumbnail(video_id)

        # Create a new QListWidgetItem with the video title
        item = QListWidgetItem()

        # Create a QLabel for the video title and enable word wrap
        label = QLabel(video_title)
        label.setWordWrap(True)

        # Set the size hint for the item to control row height (adjusted for the scaled thumbnail size)
        item.setSizeHint(QSize(self.video_titles_list.sizeHint().width(), 100))

        # Fetch and set the thumbnail as an icon with scaling
        if thumbnail_path:
            try:
                pixmap = QPixmap(thumbnail_path)
                scaled_pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon = QIcon(scaled_pixmap)

                # Set the icon to the list item
                item.setIcon(icon)
            except Exception as e:
                print(f"Error loading thumbnail: {str(e)}")

        # Add the item to the QListWidget
        self.video_titles_list.addItem(item)

        # Set the QLabel as the widget for the QListWidgetItem
        self.video_titles_list.setItemWidget(item, label)

        # Optionally set a consistent icon size
        self.video_titles_list.setIconSize(QSize(100, 100))

    def show_message_box(self, title, message):
        msg_box = QMessageBox()
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()

    def faafo(self):
        if self.current_video_title is not None:
            self.save_video_data(self.current_video_title)

        self.input_file_name = "targets.json"
        self.save_to_json()

        try:
            self.close()
            cwd = os.path.dirname(os.path.abspath(__file__))
            subprocess.run(
                ["python3", "tatoclip.py"],
                check=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            #sys.exit(0)
        except Exception as e:
            print(f"Error starting tatoclip.py: {e}")


def set_default_palette(app):
    palette = QPalette()

    # Set the color for different roles
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))

    # Apply the palette to the application
    app.setPalette(palette)
    app.setStyleSheet("""
                QToolTip {
                    background-color: #333333;  /* Dark background */
                    color: #eeeeee;             /* Light text */
                    border: 1px solid #555555;  /* Subtle border */
                    padding: 4px;
                    border-radius: 3px;
                }
            """)
    return palette

def main():
    global main_palette
    global app
    app = QApplication(sys.argv)
    main_palette = set_default_palette(app)


    initial_file = None
    if len(sys.argv) > 1:
        initial_file = sys.argv[1]

    gui = PlaylistBuilderGUI(initial_file)
    gui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
