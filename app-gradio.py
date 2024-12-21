import json
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
import uuid
import gradio as gr
from TranscriptWorker import TranscriptWorker
import portalocker

# File handling configurations
MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
CHUNK_SIZE = 64 * 1024 * 1024  # 64MB chunks

class SystemLock:
    def __init__(self):
        self.lock_file = Path(tempfile.gettempdir()) / 'system_lock.json'
        self.lock_handle = None
        if not self.lock_file.exists():
            self._write_lock_state({
                'is_busy': False,
                'current_user': None,
                'start_time': None,
                'estimated_time': None
            })

    def _acquire_lock(self, mode='r'):
        if self.lock_handle is not None:
            self.lock_handle.close()

        self.lock_handle = open(self.lock_file, mode)
        portalocker.lock(self.lock_handle, portalocker.LOCK_EX)

    def _release_lock(self):
        if self.lock_handle is not None:
            portalocker.unlock(self.lock_handle)
            self.lock_handle.close()
            self.lock_handle = None

    def _write_lock_state(self, state):
        try:
            self._acquire_lock('w')
            json.dump(state, self.lock_handle)
            self.lock_handle.flush()
            os.fsync(self.lock_handle.fileno())
        finally:
            self._release_lock()

    def _read_lock_state(self):
        default_state = {
            'is_busy': False,
            'current_user': None,
            'start_time': None,
            'estimated_time': None
        }

        if not self.lock_file.exists():
            return default_state

        try:
            self._acquire_lock('r')
            self.lock_handle.seek(0)
            return json.load(self.lock_handle)
        except json.JSONDecodeError:
            return default_state
        finally:
            self._release_lock()

    def is_busy(self):
        state = self._read_lock_state()
        return state['is_busy']

    def set_busy(self, user_id, estimated_time):
        state = {
            'is_busy': True,
            'current_user': user_id,
            'start_time': datetime.now().isoformat(),
            'estimated_time': estimated_time
        }
        self._write_lock_state(state)

    def release(self):
        state = {
            'is_busy': False,
            'current_user': None,
            'start_time': None,
            'estimated_time': None
        }
        self._write_lock_state(state)

    def get_status(self):
        return self._read_lock_state()

class TempFileManager:
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / 'video_processing'
        self.temp_dir.mkdir(exist_ok=True)

    def generate_temp_path(self, original_filename):
        unique_id = uuid.uuid4().hex
        extension = Path(original_filename).suffix
        return self.temp_dir / f"{unique_id}{extension}"

    def save_uploaded_file(self, uploaded_file):
        """Save uploaded file to temporary directory"""
        temp_path = self.generate_temp_path(uploaded_file)
        print(f"save_uploaded_file: {temp_path}")
        try:
            shutil.copyfile(uploaded_file.name, temp_path)
            return str(temp_path)
        except Exception as e:
            self.cleanup_file(temp_path)
            raise Exception(f"Error saving file: {e}")

    def cleanup_directory(self):
        for file_path in self.temp_dir.glob('*'):
            if file_path.is_file():
                file_path.unlink()
    def cleanup_file(self, file_path):
        """Safely delete a temporary file"""
        try:
            if file_path and Path(file_path).exists():
                Path(file_path).unlink()
                print(f"Cleaned up file: {file_path}")
        except Exception as e:
            print(f"Error cleaning up file {file_path}: {e}")

temp = TempFileManager()
system_lock = SystemLock()
transcript_worker = TranscriptWorker()


def process_video(uploaded_file):
    if system_lock.is_busy():
        status = system_lock.get_status()
        return (f"System is busy with another request. Please try again later.\n"
                f"Started: {status['start_time']}\n"
                f"Estimated time: {status['estimated_time']} minutes"), None, None

    try:
        system_lock.set_busy("user", estimated_time=5)  # Placeholder estimated time
        temp.cleanup_directory()
        print(f"Upload file: {uploaded_file}")
        temp_file_path = temp.save_uploaded_file(uploaded_file)  # Pass uploaded_file directly

        audio_path = transcript_worker.process_convert_to_audit(temp_file_path)
        diarization_results, detection_path = transcript_worker.diarization(audio_path)

        return "Processing complete!", audio_path, diarization_results
    except Exception as e:
        return f"Error: {str(e)}", None, None
    finally:
        system_lock.release()


def main():
    interface = gr.Interface(
        fn=process_video,
        inputs=[gr.File(label="Upload Video File")],
        outputs=[
            gr.Text(label="Status"),
            gr.Audio(label="Audio Output"),
            gr.Text(label="Diarization Results")
        ],
        title="Video Processing Pipeline",
        description="Upload a video file to process it into audio and perform diarization."
    )
    interface.launch()

if __name__ == "__main__":
    main()
