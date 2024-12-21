import gc
import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from pydub import AudioSegment

from lib.GPUManager import GPUManager


env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
HF_TOKEN = os.getenv('HUGGING_FACE_HUB_TOKEN')
HF_HOME = os.getenv('HF_HOME')
class WhisperOpenAI:
    def __init__(self):
        self.gpu_manager = GPUManager()
        self.device =   self.gpu_manager.device
        self.torch_dtype = self.gpu_manager.torch_dtype
        
        self.cache_dir =HF_HOME
        self._create_directories()
        
        model_id = "openai/whisper-large-v3-turbo"
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, 
            torch_dtype=self.torch_dtype, 
            low_cpu_mem_usage=True, 
            use_safetensors=True
        )
        model.to(self.device)
        processor = AutoProcessor.from_pretrained(model_id, cache_dir=self.cache_dir)
        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=self.torch_dtype,
            device=self.device,
        )
        self.gpu_manager.clear_gpu('WhisperOpenAI')


    def _create_directories(self):
        """Create necessary directories"""
        for dir_path in [self.cache_dir]:
            os.makedirs(dir_path, exist_ok=True)
            print(f"Directory ready: {dir_path}")

    def transcribe(self, audio_path: str):
        """
        Transcribe audio file with validation and splitting for files over 30 seconds.
        """
        if not os.path.exists(audio_path):
            print(f"Audio file not found at path: {audio_path}")
            return ""

        # Check file size
        file_size = os.path.getsize(audio_path)
        if file_size == 0:
            print(f"Audio file is empty (0 bytes): {audio_path}")
            return ""
            
        try:
            # Attempt to load audio to validate format
            audio = AudioSegment.from_file(audio_path)
        except Exception as e:
            raise ValueError(f"Invalid audio file format or corrupted file: {str(e)}")

        # Calculate duration in seconds
        duration_seconds = len(audio) / 1000
        
        with self.gpu_manager.gpu_session(memory_fraction=0.8, component_name="WhisperOpenAI"):
            # Process short audio files directly
            if duration_seconds <= 30:
                generate_kwargs = {"language": "thai"}
                result = self.pipe(audio_path, generate_kwargs=generate_kwargs)
                text = result["text"]
            else:
                # Split and process longer audio files
                segment_length = 30 * 1000  # 30 seconds in milliseconds
                full_text = []
                print("Over 30 Sec....")
                
                # Create temporary directory with error handling
                temp_dir = Path("temp_audio_segments")
                try:
                    temp_dir.mkdir(exist_ok=True)
                    
                    # Process audio segments
                    for i, start_time in enumerate(range(0, len(audio), segment_length)):
                        segment = audio[start_time:start_time + segment_length]
                        segment_path = temp_dir / f"segment_{i}.wav"
                        
                        try:
                            # Export segment with error handling
                            segment.export(segment_path, format="wav")
                            
                            # Validate segment file
                            if os.path.getsize(segment_path) == 0:
                                raise ValueError(f"Generated segment {i} is empty")
                                
                            # Transcribe segment
                            generate_kwargs = {"language": "thai"}
                            result = self.pipe(str(segment_path), generate_kwargs=generate_kwargs)
                            full_text.append(result["text"])
                            
                        finally:
                            # Clean up segment file
                            if segment_path.exists():
                                segment_path.unlink()
                    
                    # Combine transcribed segments
                    text = " ".join(full_text)
                    
                finally:
                    # Clean up temporary directory
                    if temp_dir.exists():
                        try:
                            temp_dir.rmdir()
                        except Exception as e:
                            print(f"Warning: Failed to remove temporary directory: {str(e)}")
            
            return text