"""
Speech-to-text interface - abstraction layer for STT engines.
Currently supports Vosk, designed to be swappable.
"""

import logging

logger = logging.getLogger(__name__)


class STTInterface:
    """Base class for STT engines."""
    
    def __init__(self, config):
        self.config = config
    
    def start(self):
        """Initialize the STT engine."""
        raise NotImplementedError
    
    def process_audio(self, audio_data):
        """
        Process audio data and return partial results.
        Returns: dict with "partial" key or None
        """
        raise NotImplementedError
    
    def finish(self):
        """
        Finalize recognition and return final result.
        Returns: dict with "text" and "confidence" keys
        """
        raise NotImplementedError
    
    def stop(self):
        """Clean up resources."""
        raise NotImplementedError


class VoskSTT(STTInterface):
    """Vosk offline STT implementation."""
    
    def __init__(self, config):
        super().__init__(config)
        self.recognizer = None
        self.model = None
    
    def start(self):
        """Initialize Vosk model and recognizer."""
        try:
            from vosk import Model, KaldiRecognizer
            import json
            
            model_path = self.config.get("model_path", "models/vosk-en")
            sample_rate = self.config.get("sample_rate", 16000)
            
            logger.info(f"Loading Vosk model from {model_path}")
            self.model = Model(model_path)
            self.recognizer = KaldiRecognizer(self.model, sample_rate)
            logger.info("Vosk model loaded successfully")
            
        except ImportError:
            logger.error("Vosk not installed. Run: pip install vosk")
            raise
        except Exception as e:
            logger.error(f"Failed to load Vosk model: {e}")
            raise
    
    def process_audio(self, audio_data):
        """Process audio chunk."""
        if self.recognizer is None:
            return None
        
        if self.recognizer.AcceptWaveform(audio_data):
            result = json.loads(self.recognizer.Result())
            return result
        else:
            partial = json.loads(self.recognizer.PartialResult())
            return partial
    
    def finish(self):
        """Get final result."""
        if self.recognizer is None:
            return {"text": "", "confidence": 0.0}
        
        import json
        result = json.loads(self.recognizer.FinalResult())
        return {
            "text": result.get("text", ""),
            "confidence": 1.0  # Vosk doesn't provide confidence per utterance
        }
    
    def stop(self):
        """Clean up."""
        self.recognizer = None
        self.model = None


def create_stt_engine(config):
    """Factory function to create STT engine based on config."""
    engine_type = config.get("engine", "vosk")
    
    if engine_type == "vosk":
        return VoskSTT(config)
    else:
        raise ValueError(f"Unknown STT engine: {engine_type}")
