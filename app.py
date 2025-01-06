 
 
from queue import Queue, Empty
import gc
import json
import os
import threading
from venv import logger
import streamlit as st
import tempfile
from pathlib import Path
from datetime import datetime
import time 
import uuid
from TranscriptWorker import TranscriptWorker
import portalocker
from streamlit.runtime.scriptrunner import get_script_run_ctx, add_script_run_ctx
import torch
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemLock, cls).__new__(cls)
            cls._instance._initialize()
            config=os.getenv("PYTORCH_CUDA_ALLOC_CONF")
            print(f"*********** PYTORCH_CUDA_ALLOC_CONF: {config} ******************")
        return cls._instance
    def _initialize(self):
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
def send_email(sender_email, app_password, receiver_email, subject, body):
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, app_password)
            text = message.as_string()
            server.sendmail(sender_email, receiver_email, text)
            return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

temp = TempFileManager()
transcript_worker = TranscriptWorker()

def long_running_process(progress_queue, temp_file_path, user_email):
    ctx = get_script_run_ctx()
    
    def _process():
        add_script_run_ctx(ctx)
        
        try:
            # Convert to audio
            print("Converting video to audio...")
            output_audio_path = transcript_worker.process_convert_to_audit(temp_file_path)
            print("Audio conversion complete!")
            
            # Diarization
            print("Performing diarization...")
            full_text, output_detection_path = transcript_worker.diarization(output_audio_path)
            chunk_output_dir = transcript_worker.splitAudio(output_audio_path, output_detection_path)
            print("Splitting audio into chunks...")
            
            chunk_dir = Path(chunk_output_dir)
            wav_files = sorted([f for f in chunk_dir.glob('*.wav')])
            total_files = len(wav_files)
            print(f"chunks:{wav_files}")
            current_transcript = []
            for idx, chunk_file in enumerate(wav_files, 1):
                try:
                    progress = idx / total_files
                    progress_queue.put(('progress', progress))
                    
                    print(f"Processing chunk {idx}/{total_files}: {chunk_file}")
                    raw_text = transcript_worker.transcribe(str(chunk_file))
                    clean_repat_text = transcript_worker.clean_repeated_words(raw_text)
                    text = transcript_worker.clean_thai_repeats(clean_repat_text)
                    
                    chunk_name = chunk_file.name.split("_")
                    speaker = f"{chunk_name[2]}_{chunk_name[3].split('.')[0]}"
                    chunk_text = f"{speaker}: {text}"
                    current_transcript.append(chunk_text)
                    print(f'Transcript:{chunk_text}')
                    
                except Exception as e:
                    progress_queue.put(('error', f"Error processing chunk {chunk_file.name}: {str(e)}"))
            
            final_transcript = "\n\n".join(current_transcript)
            progress_queue.put(('complete', final_transcript))
            
            try:
                send_email(
                    sender_email="noreply.jaroenchai@gmail.com",
                    app_password="ckex ochw zlji xyow",
                    receiver_email=user_email,
                    subject="Video Processing Complete",
                    body=f"Your video processing is complete.\n\nTranscript:\n\n{final_transcript}"
                )
            except Exception as e:
                progress_queue.put(('warning', f"Email sending failed: {str(e)}"))
                
        except Exception as e:
            progress_queue.put(('error', str(e)))

    return _process

system_lock = SystemLock();
# In your main function:
def main():
    init_session_state()
    create_config()
    
    st.title("Video Processing Pipeline")
    
    if 'system_lock' not in st.session_state:
        st.session_state.system_lock = system_lock

    try:
        status = st.session_state.system_lock.get_status()
    except Exception as e:
        st.error(f"Error getting system status: {str(e)}")
        return

    if status['is_busy']:
        st.sidebar.error("🔴 System Busy")
        st.sidebar.write(f"Started: {status['start_time']}")
        st.sidebar.write(f"Estimated time: {status['estimated_time']} minutes")
    else:
        st.sidebar.success("🟢 System Ready")
        email = st.text_input("Enter your email address", key="email_input")
        
        with st.form("upload_form"):
            uploaded_file = st.file_uploader("Choose a video file", type=['mp4', 'avi', 'mov'])
            submit_button = st.form_submit_button("Process Video")

            if submit_button and uploaded_file is not None:
                progress_placeholder = st.empty()
                progress_bar = st.progress(0)
                
                progress_queue = Queue()
                try:
                    temp_file_path = temp.save_uploaded_file(uploaded_file)
                    progress_placeholder.success("Video uploaded successfully!")
                    st.video(str(temp_file_path))

                    ctx = get_script_run_ctx()
                    process_func = long_running_process(progress_queue, temp_file_path, email)
                    thread = threading.Thread(target=process_func)
                    thread.daemon = True
                    add_script_run_ctx(ctx)
                    thread.start()

                    while thread.is_alive():
                        try:
                            msg_type, msg_data = progress_queue.get(timeout=1.0)
                            
                            if msg_type == 'progress':
                                progress_bar.progress(msg_data)
                            elif msg_type == 'error':
                                progress_placeholder.error(msg_data)
                                break
                            elif msg_type == 'warning':
                                progress_placeholder.warning(msg_data)
                            elif msg_type == 'complete':
                                progress_bar.progress(1.0)
                                progress_placeholder.success("Process Complete!")
                                st.text_area("Transcript", msg_data, height=300)
                                
                        except Empty:
                            continue
                        except Exception as e:
                            progress_placeholder.error(f"Error: {str(e)}")
                            break

                    thread.join(timeout=1.0)
                    
                except Exception as e:
                    progress_placeholder.error(f"Error: {str(e)}")
                finally:
                    system_lock.release()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        gc.collect()

if __name__ == "__main__":
    main()