import os
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
 
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

class VideoToMp3:
    def __init__(self):
        pass

    def convert_video_to_audio(self, video_path, output_audio_path):
        """Convert a video file to audio file with optional mono and sample rate settings."""
        try:
            # Load and convert video
            video_clip = VideoFileClip(video_path)
            audio_clip = video_clip.audio
            
       
            audio_params = {
                   
                    "fps": 16000, # Set the desired sampling rate: 16000 Hz
                    # "fps": 8000, # Alternatively, set the sampling rate to 8000 Hz
                    "nchannels": 1, # Mono audio
                    "bitrate": "16k" # Set the desired bitrate
                }
                    
     
            
            audio_clip.write_audiofile(output_audio_path,fps=audio_params["fps"],nbytes=2,bitrate=audio_params["bitrate"])
            
            # Cleanup
            audio_clip.close()
            video_clip.close()

            audio = AudioSegment.from_file(output_audio_path)
            # ลดเสียงรบกวนด้วยการปรับ EQ
            audio = audio.low_pass_filter(3000)  # ลดเสียงรบกวนความถี่สูงกว่า 3000 Hz
            audio = audio.set_frame_rate(16000).set_channels(1)
            audio.export(output_audio_path, format="wav")
            

            
          
            print(f"Successfully converted")
          
        except Exception as e:
            print(f"An error occurred while converting {video_path}: {str(e)}")
            return None