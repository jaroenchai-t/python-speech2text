 
 
import gc
import os
from pathlib import Path
import re

import torch
from lib.AudioDiarization import AudioDiarization
from lib.VideoToMp3 import VideoToMp3
from lib.Wisper_OpenAI import WhisperOpenAI
import tempfile

class TranscriptWorker:
    _instance = None
    _initialized = False
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TranscriptWorker, cls).__new__(cls)
        return cls._instance
    def __init__(self):
        if not TranscriptWorker._initialized:
            self.Diarization = AudioDiarization()
            self.VideoToMp3 = VideoToMp3()
            self.transcript = WhisperOpenAI()
            self.output_dir = Path(tempfile.gettempdir()) / 'video_processing'/'output'
            self.output_dir.mkdir(exist_ok=True)
                    # Set PyTorch memory management
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                # Try to enable memory efficient attention
                os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
            print("TranscriptWorker initialized")
        else:
            print("Using existing TranscriptWorker instance")

    def _clear_gpu_memory(self):
        """Clear GPU memory cache"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()
    def process_convert_to_audit(self,video_path):
            output_video = os.path.basename(video_path).split(".")[0]
            audio_folder=os.path.join(self.output_dir , output_video)
            os.makedirs(audio_folder, exist_ok=True)
            output_audio_path =os.path.join(audio_folder,f'{output_video}.wav')# r"D:\95 hobbie\AI\Python\Lab 8 Video to Audio\audio\output.mp3"
            # #State 1 Convert video to audio
            self.VideoToMp3.convert_video_to_audio(video_path,output_audio_path)
        
            return output_audio_path
    def diarization(self,output_audio_path):
        self._clear_gpu_memory()
        output_video_name = os.path.basename(output_audio_path).split(".")[0]
        audio_diarization=os.path.join(self.output_dir , output_video_name)
        os.makedirs(audio_diarization, exist_ok=True)
        output_detection_path =os.path.join(audio_diarization,'output.txt')
        print(f"output_detection_path: {output_detection_path}")
        full_text=self.Diarization.Diarization(output_audio_path,output_detection_path)
        return full_text,output_detection_path

    def splitAudio(self,output_audio_path,output_detection_path):
        output_video_name = os.path.basename(output_audio_path).split(".")[0]
        autio_out_shunk =os.path.join(self.output_dir , output_video_name,'chunk')
        os.makedirs(autio_out_shunk, exist_ok=True)
        self.Diarization.SplitAudio(output_audio_path,output_detection_path,autio_out_shunk)
        return autio_out_shunk
    def transcribe(self, audio_chunk_path: str):
        self._clear_gpu_memory()
        return self.transcript.transcribe(audio_chunk_path)

    def clean_repeated_words(self,text):
        # Split into words
        words = text.split()
        # Remove consecutive duplicates
        cleaned_words = [words[i] for i in range(len(words)) 
                        if i == 0 or words[i] != words[i-1]]
        return ' '.join(cleaned_words)
    
    def clean_thai_repeats(self,text):
        # Pattern to match repeated Thai words
        pattern = r'([\u0E00-\u0E7F]+?)\1+'
        return re.sub(pattern, r'\1', text)

    def list_wav_files(self,folder_path, extension='.wav'):
        wav_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith(extension)]
        
        return sorted(wav_files, key=lambda x: int(re.search(r'chunk_(\d+)_', x).group(1))) 
    
    def _cleanup_file(file_path):
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
                    self._cleanup_file(file_path)
            print("Temporary directory cleaned")
        except Exception as e:
            print(f"Error cleaning directory: {e}")
    @classmethod
    def get_instance(cls):
        """Alternative way to get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance