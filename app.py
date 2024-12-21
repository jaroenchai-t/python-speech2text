 
 
import json
import os
from venv import logger
import streamlit as st
import tempfile
from pathlib import Path
from datetime import datetime
import uuid
from TranscriptWorker import TranscriptWorker
import portalocker
# File handling configurations
MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB
CHUNK_SIZE = 64 * 1024 * 1024  # 64MB chunks
# Initialize all session state variables
def init_session_state():
    if 'is_busy' not in st.session_state:
        st.session_state.is_busy = False
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    if 'user_id' not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())
    if 'start_time' not in st.session_state:
        st.session_state.start_time = None
    if 'estimated_time' not in st.session_state:
        st.session_state.estimated_time = None
 


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

def get_file_size_display(size_bytes):
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{round(size_bytes / (1024 * 1024 * 1024), 2)}GB"
    return f"{round(size_bytes / (1024 * 1024), 1)}MB"
class TempFileManager:
    
    def __init__(self):
        # Create a dedicated temp directory for our application
        self.temp_dir = Path(tempfile.gettempdir()) / 'video_processing'
        self.temp_dir.mkdir(exist_ok=True)
        logger.info(f"Temporary directory initialized at: {self.temp_dir}")
        print(f"Temporary directory initialized at: {self.temp_dir}")
    
    def generate_temp_path(self, original_filename):
        """Generate unique temporary file path"""
        unique_id = uuid.uuid4().hex
        extension = Path(original_filename).suffix
        return self.temp_dir / f"{unique_id}{extension}"

    def save_uploaded_file(self, uploaded_file):
        """Save uploaded file to temporary directory"""
        temp_path = self.generate_temp_path(uploaded_file.name)
        try:
            # Save file in chunks
            with open(temp_path, 'wb') as f:
                while True:
                    chunk = uploaded_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
            
            logger.info(f"File saved temporarily at: {temp_path}")
            print(f"File saved temporarily at: {temp_path}")
            return str(temp_path)
        except Exception as e:
            logger.error(f"Error saving file {uploaded_file.name}: {e}")
            self.cleanup_file(temp_path)
            raise

    def cleanup_file(self, file_path):
        """Safely delete a temporary file"""
        try:
            if file_path and Path(file_path).exists():
                Path(file_path).unlink()
                print(f"Cleaned up file: {file_path}")
        except Exception as e:
            print(f"Error cleaning up file {file_path}: {e}")

    def cleanup_directory(self):
        """Clean up all files in temporary directory"""
        try:
            for file_path in self.temp_dir.glob('*'):
                if file_path.is_file():
                    self.cleanup_file(file_path)
            print("Temporary directory cleaned")
        except Exception as e:
            print(f"Error cleaning directory: {e}")

    def generate_temp_filename(self, original_filename):
        """Generate a unique filename while preserving the extension"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = uuid.uuid4().hex[:8]
        extension = Path(original_filename).suffix
        return f"{timestamp}_{unique_id}{extension}"

def get_file_size_display(size_bytes):
    """Convert bytes to appropriate unit (MB or GB)"""
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{round(size_bytes / (1024 * 1024 * 1024), 2)}GB"
    return f"{round(size_bytes / (1024 * 1024), 1)}MB"

def create_config():
    config_dir = Path('.streamlit')
    config_dir.mkdir(exist_ok=True)
    
    config_file = config_dir / 'config.toml'
    config_content = """
[server]
maxUploadSize = 1000  # Size in MB
maxMessageSize = 1000

[browser]
serverTimeout = 300  # Timeout in seconds
    """
    
    with open(config_file, 'w') as f:
        f.write(config_content)

temp = TempFileManager()
transcript_worker = TranscriptWorker()
def main():
    init_session_state()
    st.title("Video Processing Pipeline")
    # Initialize system lock
    if 'system_lock' not in st.session_state:
        st.session_state.system_lock = SystemLock()

    # Generate unique user ID if not exists
    if 'user_id' not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())

    # Get current system status
    status = st.session_state.system_lock.get_status()
       # Display system status in sidebar
    if status['is_busy']:
        st.sidebar.error("🔴 System Busy")
        st.sidebar.write(f"Started: {status['start_time']}")
        st.sidebar.write(f"Estimated time: {status['estimated_time']} minutes")
    else:
        st.sidebar.success("🟢 System Ready")
    
    
    uploaded_file = st.file_uploader("Choose a video file", type=['mp4', 'avi', 'mov'])
    
    if uploaded_file:
        file_size = get_file_size_display(uploaded_file.size)
        st.info(f"Uploaded file size: {file_size}")
      # Check if system is busy
        if status['is_busy']:
            if status['current_user'] != st.session_state.user_id:
                st.warning("⚠️ System is currently processing another request. Please wait and try again later.")
                st.info(f"Estimated wait time: {status['estimated_time']} minutes")
                return
        
        if st.button("Process Video"):
            if not status['is_busy']:
                # Clean temp directory on startup
                temp.cleanup_directory()
                # Set system as busy
                estimated_time = len(uploaded_file.getvalue()) / (1024 * 1024 * 60)  # Rough estimate
                st.session_state.system_lock.set_busy(st.session_state.user_id, estimated_time)
                

                status_placeholder = st.empty()
                progress_text = st.empty()
                progress_bar = st.progress(0)
                transcript_container = st.empty()
                
                try:
                  
                    # Save file to temp directory
                    temp_file_path = temp.save_uploaded_file(uploaded_file)
                    status_placeholder.success("Video uploaded successfully!")
                    st.video(str(temp_file_path))

                    # Convert to audio
                    status_placeholder.info("Converting video to audio...")
                    output_audio_path = transcript_worker.process_convert_to_audit(temp_file_path)
                    if not output_audio_path:
                        raise Exception("Failed to convert video to audio")
                    
                    st.audio(output_audio_path)
                    status_placeholder.success("Audio conversion complete!")

                    # Diarization
                    status_placeholder.info("Performing diarization...")
                    full_text, output_detection_path = transcript_worker.diarization(output_audio_path)
                    st.write("### Diarization Results:")
                    st.write(full_text)

                    # Split audio
                    status_placeholder.info("Splitting audio into chunks...")
                    chunk_output_dir = transcript_worker.splitAudio(output_audio_path, output_detection_path)
                    
                    # Ensure chunk_output_dir is a string path
                    if not isinstance(chunk_output_dir, (str, Path)):
                        # If TranscriptWorker.splitAudio returns an object, it should have a path attribute
                        # Modify this according to your TranscriptWorker implementation
                        chunk_output_dir = str(chunk_output_dir.path if hasattr(chunk_output_dir, 'path') else chunk_output_dir)
                    
                    # Convert to Path object for reliable path handling
                    chunk_dir = Path(chunk_output_dir)
                    
                    # Get all WAV files in the chunk directory
                    wav_files = sorted([f for f in chunk_dir.glob('*.wav')])
                    total_files = len(wav_files)
                    
                    if total_files == 0:
                        raise Exception("No audio chunks found for processing")

                    status_placeholder.info("Processing audio chunks...")
                    current_transcript = []
                    
                    for idx, chunk_file in enumerate(wav_files, 1):
                        try:
                            # Update progress
                            progress = idx / total_files
                            progress_bar.progress(progress)
                            progress_text.text(f"Processing chunk {idx}/{total_files}")
                            
                            # Process chunk
                            print(f"Processing chunk {idx}/{total_files}: {chunk_file}")
                            raw_text = transcript_worker.transcribe(str(chunk_file))
                            print(f"Raw text: {raw_text}")
                            clean_repat_text = transcript_worker.clean_repeated_words(raw_text)
                            print(f"Cleaned text: {clean_repat_text}")
                            text = transcript_worker.clean_thai_repeats(clean_repat_text)
                            print(f"Final text: {text}")
                            
                            # Extract speaker info from filename
                            chunk_name = chunk_file.name.split("_")
                            speaker = f"{chunk_name[2]}_{chunk_name[3].split('.')[0]}"
                            
                            # Add to transcript
                            chunk_text = f"{speaker}: {text}"
                            current_transcript.append(chunk_text)
                            
                            # Update display
                            transcript_container.markdown("\n\n".join(current_transcript))
                            
                        except Exception as e:
                            st.error(f"Error processing chunk {chunk_file.name}: {str(e)}")
                    
                    # Final updates
                    progress_bar.progress(1.0)
                    progress_text.text("Processing complete!")
                    status_placeholder.success("All chunks processed successfully!")
                    
                    # Save final transcript
                    final_transcript = "\n\n".join(current_transcript)
                    st.download_button(
                        label="Download Transcript",
                        data=final_transcript,
                        file_name="transcript.txt",
                        mime="text/plain"
                    )

                except Exception as e:
                    st.session_state.system_lock.release()
                    status_placeholder.error(f"Error during processing: {str(e)}")
                    raise e  # Re-raise to see full traceback in terminal
                finally:
                    # Release system busy status
                    st.session_state.system_lock.release()
 

if __name__ == "__main__":
    main()