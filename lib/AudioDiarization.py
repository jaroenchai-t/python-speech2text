import gc
from pyannote.audio import Pipeline
import os
import warnings
from pyannote.audio.pipelines.utils.hook import ProgressHook
from pydub import AudioSegment
from dotenv import load_dotenv

from lib.GPUManager import GPUManager

 

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)
  
#os.environ['SPEECHBRAIN_USE_LOCAL_STRATEGY'] = 'True'
HF_TOKEN = os.getenv('HUGGING_FACE_HUB_TOKEN')
HF_HOME = os.getenv('HF_HOME')
warnings.filterwarnings("ignore")
class AudioDiarization:
     def __init__(self):
        self.gpu_manager = GPUManager()
        self.device = self.gpu_manager.device
        self.compute_type = self.gpu_manager.torch_dtype
        self.cache_dir = HF_HOME
        self._create_directories()
        self.gpu_manager.clear_gpu('AudioDiarization')
        #with self.gpu_manager.gpu_session(memory_fraction=0.7, component_name="AudioDiarization"):
        #     self._init_diarization()
            
 
     def _create_directories(self):
        """Create necessary directories"""
        for dir_path in [self.cache_dir]:
            os.makedirs(dir_path, exist_ok=True)
            print(f"Directory ready: {dir_path}")
     def _init_diarization(self):
        """Initialize the diarization pipeline"""
        try:
          
                self.pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=HF_TOKEN,  # Replace with your token
                    cache_dir=self.cache_dir,
                   
                ).to(self.device)
                # Set the parameters
                self.pipeline.instantiate({
                    "segmentation": {
                        "min_duration_off": 1.0,
                    }
                })
                #print(self.pipeline.__doc__)  # Print docstring if available
                print("Diarization pipeline initialized successfully")
        except Exception as e:
            print(f"Error initializing diarization pipeline: {str(e)}")
            self.pipeline = None
     def Diarization(self, audio_path, output_path):
        """Perform speaker diarization on audio file"""
        try:
            #if not self.pipeline:
                #print("Diarization pipeline not initialized")
                #return None

            print(f"Starting diarization for {audio_path}")
            
            with self.gpu_manager.gpu_session(memory_fraction=0.6, component_name="AudioDiarization"):
                # Run diarization
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=HF_TOKEN,  # Replace with your token
                    cache_dir=self.cache_dir,
                   
                ).to(self.device)
                #print(pipeline.__doc__)
                # Set the parameters
                pipeline.instantiate({
                    "segmentation": {
                        "min_duration_off": 1.0,
                          
                    },
                
                })
    

                with ProgressHook() as hook:
                        diarization = pipeline(
                            audio_path, 
                            hook=hook,
                      
                        )
                
                # Write results
                full_line = ''
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("Speaker Diarization Results:\n\n")
                    for turn, _, speaker in diarization.itertracks(yield_label=True):
                        line = f"[{turn.start:.1f}s -> {turn.end:.1f}s] {speaker}\n"
                        full_line = full_line + line
                        f.write(line)
                
                print(f"Diarization completed. Results saved to {output_path}")
                return full_line
                
        except Exception as e:
            print(f"An error occurred during diarization: {str(e)}")
            return None
     def SplitAudio(self, audio_path, diarization_path, output_path):
       # Read diarization results
            audio = AudioSegment.from_file(audio_path)
            with open(diarization_path, 'r', encoding='utf-8') as f:
                diarization_lines = f.readlines()[2:]
            
                for i, line in enumerate(diarization_lines):
                    parts = line.strip().split()
                    start_time = float(parts[0][1:-1].replace("s", ""))
                    end_time = float(parts[2][:-1].replace("s", ""))
                    speaker = parts[3]
                    
                    start_ms = int(start_time * 1000)
                    end_ms = int(end_time * 1000)
                    
                    chunk = audio[start_ms:end_ms]
                     
                    
                    chunk_path = os.path.join(output_path, f"chunk_{i}_{speaker}.wav")
                    chunk.export(chunk_path, format="wav")
                    print(f"Chunk {i} ({speaker}) saved to {chunk_path}")
