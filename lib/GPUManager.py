from contextlib import contextmanager
import gc

import torch


class GPUManager:
    """Singleton class to manage GPU resources across different components"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GPUManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.is_gpu_in_use = False

    @contextmanager
    def gpu_session(self, memory_fraction=0.7, component_name=""):
        """Context manager for GPU memory management"""
        try:
            if torch.cuda.is_available():
                if self.is_gpu_in_use:
                    raise RuntimeError(f"GPU is already in use when {component_name} tried to acquire it")
                
                self.is_gpu_in_use = True
                torch.cuda.empty_cache()
                gc.collect()
                torch.cuda.set_per_process_memory_fraction(memory_fraction)
                print(f"{component_name} acquired GPU - Reserved Memory: {torch.cuda.memory_allocated()/1024**2:.2f}MB")
            yield
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.set_per_process_memory_fraction(1.0)
                gc.collect()
                torch.cuda.synchronize()
                self.is_gpu_in_use = False
                print(f"{component_name} released GPU - Current Memory: {torch.cuda.memory_allocated()/1024**2:.2f}MB")
